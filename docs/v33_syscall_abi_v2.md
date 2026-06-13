# BogOS v33: Syscall ABI v2

## Why v33 Matters

BogOS v32 can dynamically verify and admit isolated Ring 3 processes. v33
gives those processes a bounded user/kernel call contract. The kernel treats
ABI v2 pointers as untrusted, validates them against the active process's
actual user page-table entries, copies bounded inputs into kernel storage, and
emits deterministic acceptance or rejection receipts.

This is a QEMU-only experimental ABI proof, not POSIX or a production OS ABI.

## Register ABI

Syscalls use `int 0x80`:

- `EAX`: syscall number on entry and signed result on return
- `EBX`: argument 0
- `ECX`: argument 1
- `EDX`: argument 2
- `ESI`: argument 3

Nonnegative values are successful results. Errors are:

- `-1`: invalid syscall
- `-2`: invalid pointer or inaccessible mapping
- `-3`: invalid or excessive length
- `-4`: permission/capability denied, reserved
- `-5`: unsupported, reserved
- `-6`: verification failed
- `-7`: output/spoofing blocked, reserved

## Supported ABI v2 Syscalls

| Number | Name | Contract |
| ---: | --- | --- |
| 6 | `sys_exit(code)` | Receipt-visible process transition to `EXITED`, including nonzero codes |
| 7 | `sys_yield()` | Saves context, requeues, and resumes through the v29/v30 scheduler |
| 8 | `sys_write_console(ptr, len)` | Reads at most 256 validated user bytes and emits kernel-controlled output evidence |
| 9 | `sys_getpid()` | Returns the active scheduled PID |
| 10 | `sys_process_info(ptr, len)` | Writes a 16-byte v2 record to validated writable user memory |
| 11 | `sys_verify_hash(ptr, len, expected_hash_ptr)` | Hashes at most 1024 validated bytes and compares a validated 32-byte expected hash |
| 12 | `sys_claim(ptr, len)` | Admits at most 256 validated bytes into a claim receipt only |

Numbers `1..5` remain compatibility-only calls for older v24-v32 proof apps.
They preserve historical raw-spawn behavior and timing, but are not available
to dynamically loaded processes. Dynamic-loader admission is explicit process
metadata; attempts to call `1..5` from those processes are rejected with `-1`
and `legacy_syscall_denied`. Unsupported numbers are rejected with `-1`.

## Pointer Validation

ABI v2 rejects zero-length ranges where a payload is required, addition
overflow, supervisor-only pages, unmapped pages, another process's private
pages, and non-writable pages for kernel-to-user output. Validation checks
every covered page in the currently scheduled process's page tables and also
requires the active CR3 and proven v31 isolation metadata to match that
process. Only after validation does the kernel copy or hash user bytes.

`sys_process_info` therefore accepts writable runtime-data or stack pages but
rejects read-only code. `sys_write_console`, `sys_verify_hash`, and
`sys_claim` accept readable user code/data/stack ranges but reject kernel,
cross-process, unmapped, overflowing, or excessive ranges.

Payload-bearing calls reject zero length. `sys_write_console` and `sys_claim`
accept at most 256 bytes; `sys_verify_hash` accepts at most 1024 bytes and
requires a separate readable 32-byte expected-hash range. `sys_process_info`
requires a caller-provided length from 16 through 1024 bytes and writes exactly
16 bytes. A range ending at the final byte of a user page is accepted; a range
crossing into an unmapped or supervisor page is rejected.

## Receipts And Negative Policy

Every ABI v2 outcome, including rejected dynamic legacy-call attempts, emits
`BOGOS_SYSCALL`. Historical raw-spawn compatibility calls `1..5` retain their
pre-v33 behavior and are outside this receipt claim. ABI v2 additionally emits:

- `BOGOS_USER_OUTPUT` for bounded kernel-controlled console output
- `BOGOS_VERIFY_HASH` for matching and mismatching verification attempts
- `BOGOS_CLAIM` for admitted or rejected claims

Rejected calls return deterministic errors and do not mutate trusted state.
Each syscall receipt includes `ABI_VERSION=2` and
`MUTATED_TRUSTED_STATE`. Rejected calls always report mutation as false.
Accepted `exit` and `yield` report true because they change process/scheduler
state; other accepted calls report false.

The v33 and v33.1 negative apps prove syscall `0`, syscall `255`, dynamic
legacy-call denial, kernel pointer, cross-process pointer, read-only code
output pointer, zero length, one-byte-over-maximum length, overflowing range,
invalid expected-hash pointer, oversized claim, and ranges crossing from a
user page into an unmapped/supervisor page. They also prove the exact maximum
write length, the final byte of a user page, and writable process-info output
are accepted. Policy rejections return to the caller; test apps then exit
normally. Hardware access violations remain page-fault-and-block events under
v31.

`BOGOS_SYSCALL_INVARIANTS` summarizes the audited pointer, CR3, length,
overflow, kernel, cross-process, code-write, and non-mutation guarantees.

## Boundaries

BogOS v33 remains QEMU-only, i686, experimental, and non-production. The ABI
does not provide IPC, networking, writable persistent filesystems, package
manager integration, POSIX compatibility, asynchronous I/O, threads,
multicore/SMP operation, or physical hardware support.
