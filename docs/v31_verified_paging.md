# BogOS v31: Verified Paging and Per-Process Address Spaces

## Status

BogOS v31.0.0 completes the scoped QEMU paging proof. Phase 1 enabled real x86
hardware paging, phase 2 added per-process CR3 switching, phase 3A protected
kernel mappings, and phase 3B proved private user mappings and tested process
isolation while preserving v30 preemption.

## Phase 1: Global Hardware Paging

Phase 1 creates a page-aligned x86 page directory, enables CR4 Page Size
Extensions, loads its physical address into CR3, and enables CR0.PG during
kernel boot. The directory uses 1024 4 MiB entries to identity-map the complete
32-bit address space. This conservatively preserves all existing kernel,
Multiboot/initrd, heap, VGA, stack, serial-I/O, and fixed Ring 3 execution-slot
addresses used by the QEMU demo.

The map is deliberately global and user-accessible. Marking the kernel portion
supervisor-only would break current Ring 3 code and stack slots until mappings
are split precisely. Receipts therefore truthfully state:

- `PAGING_ENABLED=true`
- `KERNEL_CR3=<nonzero global CR3>`
- `KERNEL_SUPERVISOR_ONLY=false`
- `PER_PROCESS_CR3=false`
- `PROCESS_ISOLATION_ENFORCED=false`
- `ISOLATION_STATUS=kernel_paging_enabled`

The per-process address-space model and hashes remain useful metadata, but every
process referenced the same global CR3 during phase 1.

## Phase 2: Per-Process CR3 Switching

Phase 2 gives every admitted scheduler process ownership of a distinct,
page-aligned page directory and nonzero CR3 value. During phase 2, each
directory was an exact clone of the phase-1 global 4 GiB identity map. The scheduler loads the
selected process CR3 immediately before first Ring 3 entry or saved-context
restore and emits a deterministic `BOGOS_CR3_SWITCH` receipt.

Syscalls, IRQ0 preemption, and exceptions return to kernel code while the
selected process directory remains active. This is safe for phase 2 because all
process directories share identical complete kernel identity mappings. A
separate global-kernel CR3 restore is unnecessary until mappings become private
or supervisor-only.

Phase 2 proves real address-space ownership and scheduler CR3 switching while
preserving v29 context restoration and v30 timer preemption. By itself it did
not prove memory isolation; phases 3A and 3B subsequently introduced and proved
supervisor-only kernel mappings, private user mappings, and all four negative
tests.

## Phase 3B: Private User Mappings and Process Isolation

Phase 3B page-aligns each process's physical code and stack slots and grants
Ring 3 access only to the owning process's pages. Executable app-content pages
are user-accessible and read-only. The existing v29 runtime contract is
preserved with explicit private writable data pages at offsets `+0x7000` and
`+0x8000`; stacks remain private and writable.

Each process also owns one deterministic private test page in the
`0x00800000` virtual region. The cross-process malicious app writes PID 1's
private virtual page and receives a not-present user write fault because that
mapping is absent from the attacker's page directory. The code-write malicious
app writes its own read-only executable page and receives a user protection
fault. Both become `BLOCKED`, and valid timer-preempted processes run afterward.

The evaluator therefore proves `PRIVATE_USER_MAPPINGS=true`,
`CROSS_PROCESS_WRITE_BLOCKED=true`, `WRITABLE_CODE_BLOCKED=true`, and
`PROCESS_ISOLATION_ENFORCED=true` for the scoped v31 QEMU model.
Ring 3 writes to read-only PTEs fault without requiring `CR0.WP`; supervisor
write-protection policy remains outside this user-isolation proof.

This remains a small deterministic QEMU-only proof, not a production virtual
memory subsystem. Demand paging, swapping, ASLR, shared-memory policy,
copy-on-write, multiprocessor TLB shootdown, and physical hardware remain out
of scope.

## v31.1 Isolation Hardening Audit

The v31.1 audit adds no new paging feature. Each spawned process emits a
`BOGOS_MAPPING_INVARIANTS` receipt after the kernel checks CR3/page-structure
alignment, owner-only user PTEs, read-only code, writable runtime data/stack,
private-test-page ownership, supervisor-only kernel structures, and absence of
an unexpected low-memory user identity map.

The evaluator ties each final claim to exact malicious evidence:

- `/apps/v31_bad_kernel_read.bogapp`: user read protection violation;
- `/apps/v31_bad_kernel_write.bogapp`: user write protection violation;
- `/apps/v31_bad_cross_process_write.bogapp`: not-present peer-page write;
- `/apps/v31_bad_code_write.bogapp`: own-code write protection violation.

It also verifies aligned distinct CR3 values, distinct code/stack frame slots,
receipt consistency, valid-process continuation, and stable address-space
hashes. `artifacts/bogos_v31_release_audit_receipt.json` records the audit.

## Phase 3A: Supervisor-Only Kernel Mappings

Phase 3A replaces the low 4 MiB process mapping with a dedicated 4 KiB page
table. Pages are supervisor-only by default; only the selected process's
existing 64 KiB code/data slot and 4 KiB stack slot are marked user-accessible.
Higher identity-mapped PDEs remain available to Ring 0 but have their user bit
cleared in process directories.

The kernel-read and kernel-write negative apps execute in Ring 3 and access the
known kernel address `0x00100000`. Both now cause user-mode protection faults,
transition to `BLOCKED`, and emit CR2/error-code evidence. The kernel continues
and the valid preemptive apps still produce `A1`, `B1`, `A2`, `B2`.

This proved `KERNEL_PROTECTION_ENFORCED=true` for the tested QEMU boundary.
Phase 3B subsequently added and proved cross-process and code-write protection.

## v30 Baseline

BogOS v30 is a narrow QEMU-only native proof. It runs verified Ring 3 processes,
saves user contexts, preempts them through IRQ0, and resumes them with
deterministic process, scheduler, context, and preemption receipts. Process code
and stacks occupy bounded physical slots, but paging is disabled and those slots
are not isolated by page permissions.

## What v31 Adds

v31 adds an `AddressSpaceId` and `AddressSpaceMetadata` to each
process record. Metadata tracks intended user code and stack mappings, kernel
mapping policy, CR3/page-directory identity, a deterministic address-space
hash, verification status, and fault count.

Final v31 address-space receipts state:

- `CR3=<distinct nonzero per-process CR3>`
- `KERNEL_SUPERVISOR_ONLY=true`
- `PAGING_ENABLED=true`
- `PER_PROCESS_CR3=true`
- `PAGE_DIRECTORY_KIND=per_process_isolated`
- `PRIVATE_USER_MAPPINGS=true`
- `PROCESS_ISOLATION_ENFORCED=true`
- `ISOLATION_STATUS=verified`

Earlier phase receipts retain their truthful incomplete-isolation values.

## Final Page-Directory and Page-Table Design

Each process owns one page-aligned page directory identified by a non-zero,
page-aligned CR3 value. Page tables describe:

- read/execute user code pages;
- read/write, non-executable-by-policy user stack pages;
- shared kernel pages marked supervisor-only;
- no mappings for another process's private code or stack pages.

The current kernel is 32-bit x86 without PAE. v31 therefore uses
4 KiB pages and conventional 1024-entry page directories/page tables. Demand
paging, copy-on-write, swapping, and page replacement are outside this
milestone.

## Kernel Mapping Policy

Process directories map kernel memory with the user/supervisor bit cleared.
User code cannot read or write the tested kernel address. The global boot
directory remains a broad identity map, while scheduled Ring 3 execution uses
the protected process directory.

## User Mapping Policy

Each accepted process receives owner-only user mappings for code, writable
runtime data, stack, and its deterministic private test page. Code is
user-readable/executable and not writable. Runtime data and stack are
user-readable/writable. Another process's private test page is absent.

## CR3 Switching Plan

The minimal native integration point is `execute_scheduled_process`, after a
READY process is selected and before entering or restoring Ring 3. That path
already owns process selection, saved context, and transition receipts.

v31 allocates bounded page directories, stores nonzero page-aligned CR3 values,
loads CR3 before first entry and every context restore, and emits
receipt-visible transitions. Shared supervisor-only kernel mappings keep
syscalls, IRQs, exceptions, and context restoration executable under each CR3.

## Page Fault Behavior

The existing IDT routes vector 14 to `common_exception_handler`. The v31
scaffold adds a structured `BOGOS_PAGE_FAULT` receipt for scheduled Ring 3
faults, reads CR2 as the fault address, increments the process fault count,
marks its address-space status faulted, and blocks the process. Other READY
processes remain scheduler-eligible.

The final handler proves and blocks kernel read/write, cross-process write, and
own-code write malicious processes.

## Receipts

Complete scoped hardware-isolation evidence uses:

```text
BOGOS_ADDRSPACE_BEGIN
PID=<pid>
CR3=<hex>
USER_CODE_BASE=<hex>
USER_CODE_PAGES=<n>
USER_STACK_BASE=<hex>
USER_STACK_PAGES=<n>
KERNEL_SUPERVISOR_ONLY=true
APP_HASH=<sha256>
ADDRSPACE_HASH=<sha256>
ISOLATION_STATUS=verified
BOGOS_ADDRSPACE_END
```

Phase-2 receipts include additional `ADDRESS_SPACE_ID`, kernel mapping,
`PAGING_ENABLED`, `PER_PROCESS_CR3`, `PROCESS_ISOLATION_ENFORCED`, and
`FAULT_COUNT` fields, and use truthful incomplete-isolation values.

```text
BOGOS_PAGE_FAULT_BEGIN
PID=<pid>
FAULT_ADDR=<hex>
ERROR_CODE=<hex>
FAULT_REASON=<reason>
ACCESS=<read/write/execute/unknown>
MODE=<user/kernel/unknown>
PROCESS_STATE=<BLOCKED/PANICKED/UNKNOWN>
BOGOS_PAGE_FAULT_END
```

The final v31 evaluator and v31.1 release-audit receipts include the QEMU serial
log hash and address-space evidence.

## Security Boundaries

- Metadata hashes prove deterministic metadata. Receipt-visible mapping
  invariant checks and malicious QEMU tests provide page-table evidence.
- Ring 3 privilege separation exists from v25, but flat segments do not isolate
  process memory.
- Kernel mappings and paging structures are supervisor-only in scheduled
  process directories. User code is read-only; runtime data and stack are
  private writable mappings.
- BogOS remains a verifier-first experimental substrate, not a production OS.

## QEMU-Only Limitations

The native kernel remains QEMU-only, i686/ELF32-only, single-core, and uses a
small deterministic demo scheduler. There is no demand paging, swapping,
overcommit, ASLR, execute-disable/NX policy, full userspace ABI change,
physical-hardware support, or production-grade memory manager.

## Acceptance Criteria

v31.0.0 may be claimed complete only when the evaluator proves all of the
following in QEMU:

- every valid process receives a non-zero, page-aligned, hardware-verified CR3
  and address-space receipt;
- two valid processes still preempt and interleave after CR3 switching;
- kernel read, kernel write, cross-process write, and code-write attempts cause
  page faults;
- each malicious process becomes `BLOCKED` with fault evidence;
- unaffected valid processes continue running;
- kernel mappings are supervisor-only and private user mappings are absent from
  other address spaces;
- the final receipt includes the serial log SHA-256 and address-space evidence;
- all v30 and earlier required checks still pass.

`scripts/evaluate_v31_verified_paging.py` proves global hardware paging,
distinct process CR3 values, scheduler CR3 switching, supervisor-only kernel
protection, private user mappings, all four malicious fault cases, blocking,
valid-process continuation, and preserved v30 preemption.
