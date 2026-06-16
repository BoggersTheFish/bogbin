# BOGBIN / BOGVM Release Notes

## v40 Phase D (implemented, current release remains v39.0.0): Persistent BogFS integration for Genesis Workspace Root

Adds the narrow persistence spine for the v40 model: the latest accepted GenesisRoot (containing the WorkspaceRoot pointer) is stored as a well-known object (record at /system/genesis_root) inside the existing v37/v38 BogFS manifest format. No new superblock or manifest region.

- Host oracle + image maker apply CreateDirectory/CreateFile/EditFile, serialize canonical GenesisRoot (GENROOTv1), patch manifest record + data lba + superblock (alternate root), recompute all hashes.
- Kernel (v38+ path) locates the well-known record during mount, loads+parses via bogk-core::parse_genesis_root, verifies content hash against manifest record, emits receipt-visible BOGOS_V40_GENESIS_BEGIN (genesis_hash, workspace_root_hash, ledger sentinel) with no mutation on error.
- Two-boot image proof: boot1 validates blank; "commit" produces written image; boot2/remount validates surviving final roots + last receipt pointer.
- Negative matrix (oracle + image corrupt + bad cap/old_root/path/content): all reject with no trusted root mutation; fallback closed.
- Replay from blank using oracle reconstructs identical final WorkspaceRoot / genesis.
- Evaluator: scripts/evaluate_v40_genesis_workspace_root.py emits full receipt (input/serial/evaluator hashes, old/new roots, accepted/rejected evidence, replay agreement, explicit qemu_only=true / production_os=false / posix=false / physical_hardware=false / kernel_verifier_spine_not_file_manager / shell_deferred_v41).
- v36-v39 behavior and most artifacts preserved (additive record in new images only; kernel prints v40 markers only when genesis record present).

This completes Phase D. Kernel/BogFS integration of the GenesisRoot is proven for the verifier-first receipt chain. v40 remains QEMU-only i686 research prototype. Shell/demo framing deferred to v41+.

## v41: Native Workspace Journal Receipts (undeniable multi-op history + rollback)

Implements the journal on top of v40 Phase D persistence:
- New pure model in bogk-core: WorkspaceJournalEntry (seq, prev_head, receipt, root_after), append_journal_entry, verify_journal_chain, create_rollback_journal_entry.
- Rollback op kind + handling in apply (root switch + journaled; objects content-addressed so history preserved via journal).
- ledger_root in GenesisRoot now used as journal head hash (previously sentinel).
- In kernel: native calls to journal fns during genesis proof path. Emits V41_JOURNAL_APPEND, V41_ROLLBACK, V41_JOURNAL_HISTORY (with head, undeniable_chain=true).
- Journal is append-only and hash-chained. Rollback appends a new entry referencing prior root; full prior history remains for inspection/audit.
- Undeniable: any tamper of an entry or head breaks the chain on verify/load (kernel would reject/fallback).
- Python oracle extended with equivalent journal serialize/append/verify/rollback for host proofs and vector agreement.
- The v40 evaluator infrastructure exercises the model; kernel binary now contains the native journal logic.
- All prior v40 guarantees + core tests preserved. New journal fns exercised via build + kernel proof emissions.

This makes the receipt chain first-class and undeniable in persistent storage before any UX.

Current release remains v39.0.0. Next continues v41 guarantees or v42 .bogapp.

## v39.0.0: Persistent Disk-Loaded Apps

Adds a standalone QEMU proof that loads a `.bogapp` v2 file from immutable
persistent BogFS. The canonical 160-byte custom header binds format and ABI
versions, total/code lengths, entrypoint, empty capability declaration, app
identity, code SHA-256, and manifest SHA-256. The filesystem root, manifest,
file lifecycle identity/version/hash, app manifest hash, and code hash are
receipt-bound before PID allocation.

The valid `/apps/hello.bogapp` fixture is copied into bounded staging only
after verification, privately mapped with read-only executable code and a
distinct CR3, scheduler-admitted, run in Ring 3, and exited through Syscall ABI
v2. Two independent boots prove the same persistent root and app hashes.
Malformed, corrupt, stale, unsupported, missing, and invalid-path cases receive
no PID, process record, scheduler admission, or execution record.

This remains an experimental QEMU-only i686 proof. It is not full ELF, does
not add dynamic libraries, package management, networking, launch arguments,
production app support, physical hardware support, or the v40 shell demo.

## v38.0.0: File Lifecycle

Adds a separate QEMU boot-time lifecycle proof over a v38 persistent BogFS
format. The bounded manifest contains at most eight deterministic file,
directory, or tombstone records, an append-only data pointer, monotonic
lifecycle IDs, and a record-table/listing hash. User mutation is restricted to
flat `/data`; `/system`, `/apps`, and `/receipts` remain protected.

Boot one creates `/data/new.txt`, writes verified content, and tombstones
`/data/delete.txt` as three distinct alternate-root commits. Boot two proves
the surviving file bytes/version/hash, deleted-file state, deterministic
listing, and final root survived. Rejected lifecycle operations retain the
trusted root, and corrupted active roots, tables, listings, or file data fall
back or reject closed.

This remains an experimental QEMU-only i686 proof. It does not add new Ring 3
filesystem syscalls, nested mutable directories, rename, POSIX behavior,
disk-loaded apps, production reliability, or physical hardware support.

## v37.0.0: Persistent Verified BogFS

Adds a separate boot-time persistent BogFS proof over the v36 QEMU legacy
IDE/ATA PIO device. The fixed layout contains alternate superblocks and
manifests plus append-only one-sector versions of `/data/persist.bin`. Mount
verifies superblock structure/checksum, root and manifest hashes, the fixed
file table, and committed file content before admitting a root.

The accepted commit writes and reads back data, the inactive manifest, and the
inactive superblock in that order, admitting generation 2 only after all
SHA-256 checks pass. The standalone evaluator proves a clean two-boot
persistence cycle and directly audits the resulting image. It also proves
rejected writes preserve the trusted root, corrupt active metadata or data
falls back to generation 1, and corruption of both roots rejects mount.

This remains a QEMU-only i686 research proof. It is not POSIX, does not add
directories, create/delete/rename, disk-loaded apps, journaling, crash/power
loss atomicity, physical-hardware support, or a production filesystem. The
v35 Ring 3 in-memory BogFS syscall behavior is preserved.

## v36.0.0: Verified Block Device Model

Adds a narrow kernel-internal QEMU legacy IDE/ATA PIO block-device proof.
BogKernel supports one fixed 4 MiB raw image, bounded LBA28 single-sector
reads and writes, 512-byte sector SHA-256 verification, protected-LBA policy,
expected preimage checks, flush, and post-write read-back verification.

The standalone QEMU evaluator builds a deterministic image, runs an attached
disk scenario and a separate no-device scenario, audits serial receipts, and
checks the post-QEMU image bytes directly. The negative matrix proves rejection
of absent device, out-of-range LBA, unsupported sector count, invalid buffer
length, corrupt sector hash, protected LBA, stale preimage, write hash
mismatch, and unsupported operations. Rejected operations do not mutate
trusted block state.

This is a QEMU-only i686 block-device proof, not a filesystem, disk driver
stack, physical-hardware claim, or production storage subsystem. BogFS remains
the v35 in-memory fixed-table service. Persistent/block-backed BogFS is
deferred to v37.

## Unreleased / v35.1 writable BogFS hardening audit

This audit leaves the current release at v35.0.0 and adds no persistence or new
syscall numbers. It proves explicit zero-length rejection, exact-maximum write
success, maximum-plus-one rejection, deterministic repeated-write versions,
and preservation of committed hash, version, stat, and read results after a
failed write.

The QEMU audit also proves exact-path identity: alias forms reject, protected
system paths reject for two isolated processes, cross-process pointers reject,
and full table/storage attempts mutate no trusted file state. A queued IPC
message retains its queue depth, ID, and hash across a failed BogFS operation.

## v35.0.0: Writable Verified BogFS

Adds bounded `bogfs_write`, `bogfs_read`, and `bogfs_stat` calls as Syscall ABI
v2 numbers `17..19`. Isolated dynamically loaded Ring 3 apps access a tiny
kernel-owned in-memory file table. Accepted writes copy from validated caller
memory into staging storage and commit only after exact path policy, permission,
capacity, and SHA-256 receipt checks succeed.

Each write emits PID, path, length, SHA-256, old version/hash, and new
version/hash. The QEMU negative matrix proves rejection of bad and
cross-process pointers, oversized writes, read-only and invalid paths, full
storage, and failed receipt-hash checks without trusted file-state mutation.
Reads and stats return only hash-verified committed contents. v31 isolation,
v32 loading, v33 Syscall ABI v2, and v34 IPC remain proven.

This is an experimental QEMU-only, in-memory milestone. It is not POSIX, has no
real disk persistence, and exposes only a fixed tiny file table.

## v34.0.0: Verified IPC / Message Passing

Adds bounded point-to-point IPC syscalls `13..16` to Syscall ABI v2. Isolated
dynamically loaded Ring 3 processes create channels, send payloads into
kernel-owned queues, receive into validated private writable pages, and poll
receipt-visible queue depth. Payload hashes and monotonic message IDs bind send
and receive evidence without direct shared memory.

The QEMU negative matrix proves rejection of kernel and cross-process send
pointers, oversized sends, full queues, read-only receive targets, too-small
receive buffers, unauthorized receives, and invalid channels. Rejected IPC
does not mutate trusted state, and rejected receives preserve the queued
message until a later valid receive. v30 preemption, v31 isolation, v32 dynamic
loading, and v33 Syscall ABI v2 remain proven.

This is an experimental QEMU-only milestone, not a production IPC subsystem.
Blocking waits, async wakeups, shared memory, networking, filesystem services,
threads/multicore, and physical hardware remain out of scope. The next target
is v35 writable verified BogFS.

## Unreleased / v33.1 syscall ABI hardening audit

This audit adds no major OS feature and leaves the current release at v33.0.0.
It adds receipt-visible syscall invariants, consistent ABI/mutation fields,
explicit dynamic-loader denial of legacy syscalls `1..5`, and stricter
claim-to-evidence evaluator checks.

The QEMU edge matrix proves zero/exact-maximum/over-maximum lengths, final-byte
user access, cross-page rejection, writable versus read-only output targets,
invalid expected-hash pointers, oversized claims, syscall `0`, syscall `255`,
overflow rejection, and legacy-call bypass rejection. v31 isolation, v32
loading, and v30 preemption remain preserved. The next target remains v34
verified IPC/message passing.

## v33.0.0: Syscall ABI v2

Adds a stable bounded `int 0x80` ABI v2 for dynamically loaded isolated Ring 3
apps. ABI v2 preserves the existing exit/yield numbers and adds
kernel-controlled console output, PID lookup, bounded process-info output,
SHA-256 verification, and claim admission.

The kernel validates each ABI v2 user range against the active process's
present/user/writable page-table entries before copying or hashing. QEMU
negative apps prove rejection of unknown calls, kernel pointers,
cross-process pointers, read-only code output pointers, oversized lengths, and
overflowing ranges without trusted-state mutation. v31 isolation, v32 dynamic
loading, and v30 preemption remain proven.

This is a QEMU-only experimental proof, not POSIX or a production OS. IPC,
networking, writable persistent storage, asynchronous I/O, threads/multicore,
and physical hardware remain out of scope. v34 verified IPC/message passing is
the next development target.

## Unreleased / v32.1 dynamic loader hardening audit

This audit adds no major OS feature and leaves the current release at v32.0.0.
It tightens the canonical `.bogapp` parser contract, adds precise
receipt-visible rejection reasons, strengthens load and process-admission
evidence, and proves rejected dynamic apps receive no PID or scheduler entry.

The QEMU negative matrix now covers bad magic, bad version, zero code length,
bad code offset, bad code length, entrypoint-at-end, unsupported nonempty
capabilities with valid hashes, trailing bytes, manifest-hash inconsistency,
and noncanonical text padding. The audit preserves v31 isolation and v30
preemption. It prepared the verified dynamic-process boundary used by v33
Syscall ABI v2.

## v32.0.0: Dynamic Verified Process Loading

Adds a deterministic kernel-loadable `.bogapp` container and `load` command.
The kernel discovers containers from mounted BogFS/initrd, validates manifest
metadata and code SHA-256 before PID allocation, and maps accepted code through
the audited v31 private-address-space path.

The QEMU evaluator proves a valid dynamic app runs in Ring 3, is timer
preempted, resumes, and exits. Hash-mismatched, malformed, invalid-entrypoint,
and missing apps are rejected before execution with deterministic `BOGOS_LOAD`
receipts. Accepted apps emit `BOGOS_PROCESS_ADMIT` evidence.

This remains a QEMU-only experimental proof, not a production OS or full ELF
loader. Demand paging, shared libraries, package-manager integration, writable
persistent filesystems, arbitrary entrypoints, nonempty capability admission,
and physical hardware remain out of scope.

## Unreleased / v31.1 isolation hardening audit

This audit adds no major paging feature. It adds receipt-visible mapping
invariant checks, stronger evaluator claim-to-evidence consistency assertions,
address-space hash stability coverage, a parallel SHA-256 verifier regression
test, and `artifacts/bogos_v31_release_audit_receipt.json`.

The audit preserves the v31.0.0 scoped QEMU isolation claim and keeps the
non-production boundary explicit. It prepared the isolation boundary used by
the subsequent v32 dynamic verified loader.

## v31.0.0: Verified Paging and Per-Process Address Spaces

Hardware paging phase 1 enables CR0.PG in QEMU using a nonzero global CR3 and a
full 32-bit identity-mapped page directory. It emits deterministic
`BOGOS_PAGING`, `BOGOS_ADDRSPACE`, and upgraded `BOGOS_PAGE_FAULT` receipt
formats, and preserves v30 timer-preemptive scheduling.

Phase 2 clones that map into distinct process-owned page directories, switches
CR3 before first Ring 3 entry and saved-context restore, and emits deterministic
`BOGOS_CR3_SWITCH` evidence while preserving v30 timer preemption.

Phase 2 process maps remained shared identity maps while proving CR3 switching.

Phase 3A replaces the low process mapping with 4 KiB page tables that are
supervisor-only by default and user-enable only each process's existing
code/data and stack slots. Malicious Ring 3 kernel-read and kernel-write apps
fault at `0x00100000`, become blocked, emit structured evidence, and valid
preemptive processes continue afterward.

Phase 3B page-aligns private process code and stack slots, exposes only
owner mappings to Ring 3, preserves explicit private writable runtime-data
pages, and makes executable app-content pages read-only. Cross-process-write
and code-write malicious apps fault, become blocked, and emit deterministic
evidence. Valid timer-preempted processes continue after all four malicious
faults.

The v31 process-isolation claim is scoped to the deterministic QEMU model. This
is not a production OS or full virtual-memory subsystem; demand paging,
swapping, ASLR, copy-on-write, and physical-hardware support remain out of
scope.

## v30.0.0: Timer-Preemptive Verified Scheduler

BOGBIN v30.0.0 upgrades the cooperative multitasking system to support timer-preemptive multitasking of Ring 3 processes, while preserving cooperative yields.

### Implementation
- Extends `ProcessState` and process table records with the `PREEMPTED` state.
- Tracks scheduler quantum statistics: `timer_ticks`, `quantum_ticks`, `preemption_count`, `current_pid`, and `last_preempted_pid`.
- Preempts Ring 3 user-mode processes upon quantum expiration (`SCHEDULER_QUANTUM = 2` ticks) inside the IRQ0 timer interrupt handler by checking `(cs & 3) == 3`.
- Saves the interrupted Ring 3 CPU context from the timer interrupt frame and transitions process state: `RUNNING` -> `PREEMPTED` -> `READY`.
- Emits deterministic `BOGOS_PREEMPT_BEGIN` / `BOGOS_PREEMPT_END` receipts.
- Extends scheduler selection receipts with the selection reason (`spawn`, `yield`, `preemption`, `exit`, or `block`).
- Exposes quantum statistics via `/system/scheduler`.
- Adds native CPU-burning assembly test apps (`preempt_a.s`, `preempt_b.s`) that yield deterministic interleaving in QEMU.

### Verification
- `python3 scripts/evaluate_v30_preemptive_scheduler.py`
- `python3 scripts/evaluate_v29_context_switch.py`
- `python3 scripts/evaluate_v28_scheduler.py`
- `python3 scripts/evaluate_v27_process_model.py`
- `cd kernel && cargo test -p bogk-core`

### Boundaries
- QEMU-only prototype.
- No priority scheduling; simple round-robin FIFO.
- No page-based memory isolation or paging.
- No IPC, networking, or writable persistent filesystem.
- No threads or multicore.

## v29.0.0: Saved User Contexts and Resumable Cooperative Multitasking

BOGBIN v29.0.0 upgrades cooperative yield from restart-on-selection behavior to resumable Ring 3 execution.

### Implementation
- Adds `SavedContext` and per-process execution-memory metadata to `ProcessRecord`.
- Saves EIP, ESP, EFLAGS, and general-purpose registers from the `int 0x80` frame on `sys_yield`.
- Gives each scheduler-owned process a bounded 64 KiB code/data slot and 4 KiB stack slot.
- Restores valid READY contexts through a dedicated `iretd` assembly path.
- Emits deterministic `BOGOS_CONTEXT_SAVE` and `BOGOS_CONTEXT_RESTORE` receipts.
- Extends TS-Lang successful-path bytecode so ordered output, yield, resumed output, and exit are preserved.

### Verification
- `python3 scripts/evaluate_v29_context_switch.py`
- `python3 scripts/evaluate_v28_scheduler.py`
- `python3 scripts/evaluate_v27_process_model.py`
- `python3 scripts/evaluate_v26_negative.py`
- `cd kernel && cargo test -p bogk-core`

### Boundaries
- Context switching remains cooperative and explicit-step only.
- Fixed slots separate process execution storage, but paging-based memory protection is not implemented.
- No timer preemption, IPC, networking, or real disk persistence.
- QEMU-only prototype.

## v28.0.0: Cooperative Verified Scheduler

BOGBIN v28.0.0 adds a deterministic cooperative scheduler on top of the v27 process model.

### Implementation
- Extends process lifecycle state with `READY`, `SCHEDULED`, and `YIELDED`.
- Adds a bounded FIFO round-robin scheduler with current PID, run queue, schedule-step counter, and last-selected PID.
- Adds `sys_yield` as syscall 7 and TS-Lang `yield();`.
- Adds `ps`, `spawn <app>`, `runq`, `sched step`, and `sched demo`.
- Adds `/system/scheduler` and deterministic `BOGOS_SCHED_BEGIN` / `BOGOS_SCHED_END` receipts.
- Excludes exited, blocked, rejected, and panicked processes from selection.

### Verification
- `python3 scripts/evaluate_v28_scheduler.py`
- `python3 scripts/evaluate_v27_process_model.py`
- `python3 scripts/evaluate_v26_negative.py`
- `cd kernel && cargo test -p bogk-core`

### Boundaries
- No preemptive scheduling.
- No saved Ring 3 CPU contexts; a yielded app restarts at its entrypoint when selected again.
- No threads, IPC, networking, or real multitasking.
- QEMU-only prototype.

## v27.0.0: Verified Process Model

BOGBIN v27.0.0 adds an explicit process model to the QEMU BogKernel before scheduling or multitasking.

### Implementation
- Adds `ProcessId`, `ProcessState`, `ProcessRecord`, `ProcessExitStatus`, and a bounded `ProcessTable` in `bogk-core`.
- Changes `run <app>` to create a process, verify the BogFS-loaded app, mark Ring 3 execution, and record exited, blocked, or rejected terminal state.
- Emits deterministic `BOGOS_PROCESS_BEGIN` / `BOGOS_PROCESS_END` receipts while preserving v26 app-run receipts and verification protections.
- Adds the deterministic `/system/processes` pseudo-file.

### Verification
- `python3 scripts/evaluate_v27_process_model.py`
- `python3 scripts/evaluate_v26_ts_lang.py`
- `python3 scripts/evaluate_v26_negative.py`
- `cd kernel && cargo test -p bogk-core`

### Boundaries
- No scheduler or multitasking.
- No real disk persistence.
- QEMU-only prototype.

## v26.0.0: TypeScript Sandboxed Ring 3 Execution Environment (v21 - v26)

BOGBIN v26.0.0 introduces true hardware-enforced Ring 3 sandboxing, a custom GDT/IDT/TSS kernel architecture, a locked software interrupt (`int 0x80`) syscall ABI, verified initrd `.bogfs` filesystem mounting, and a TypeScript compiler (`tsc.py`) that packages source code into a `.bogapp` containing compiled bytecode and a position-independent x86 runtime interpreter stub.

### Implementation
- **GDT/IDT/TSS Foundations (v21, v25):** Custom Global Descriptor Table (GDT) and Interrupt Descriptor Table (IDT) for 32-bit x86. Task State Segment (TSS) loader handles kernel stack switching. PIC remapping supports Timer (IRQ0) and Keyboard (IRQ1) interrupts.
- **Physical Memory & Heap Allocator (v22):** Physical frame allocator reads the Multiboot memory map. Thread-safe bump allocator (`GlobalAlloc`) maps physical frames for kernel heap allocation.
- **Initrd Filesystem (.bogfs) (v23):** Reads Multiboot boot modules to mount a read-only `.bogfs` archive. Cryptographically verifies SHA-256 hashes of all files against the manifest on boot.
- **Locked Syscall ABI (v24):** Exposes `int 0x80` software interrupt syscall vector with defined argument registers (`EBX`, `ECX`, `EDX`), return register (`EAX`), and error return conventions.
- **Ring 3 Sandboxing & CPU Traps (v25):** Hardware-enforced privilege separation. Traps page faults (Exception 14), GPFs (Exception 13), and invalid opcodes (Exception 6) in the kernel, writing structured security blocks and aborting violating apps safely.
- **TypeScript DSL Compiler (v26):** Host-side compiler (`tsc.py`) parses a subset of TS (verifications, reads, claims, receipts) to BOGVM bytecode and prepends a position-independent x86 interpreter stub.

### Verification
Validated with:
- `python3 scripts/evaluate_v21_interrupts.py` (Interrupts and timer ticks)
- `python3 scripts/evaluate_v22_memory.py` (Physical frame/heap allocation)
- `python3 scripts/evaluate_v23_initrd.py` (Verified initrd `.bogfs` mount)
- `python3 scripts/evaluate_v25_boundary.py` (Ring 3 sandbox boundary GPF trap)
- `python3 scripts/evaluate_v26_ts_lang.py` (TS compilation and execution)
- `python3 scripts/evaluate_v26_negative.py` (Malicious app, spoofing, and invalid ABI parameter tests)

## v20.0.0: BogOS QEMU Demo System

BOGBIN v20.0.0 introduces the first visible, OS-like demo system inside BogKernel running in QEMU.

This release adds VGA text-mode UI rendering, PS/2 keyboard polling driver with an auto-demo fallback, a shell command parser for system state query and execution, an embedded read-only pseudo-filesystem, loader-style app verification and execution, and detailed serial receipt logging.

### Implementation
- **VGA Text UI:** Standard text-mode memory at `0xb8000` is initialized and updated. Draws a status header displaying verification metrics, system state, and shell interactions.
- **PS/2 Keyboard Driver & Auto-Demo:** Polling-based PS/2 keyboard input allows users to type commands. If no keyboard activity is detected, the system executes an automated sequence of commands deterministically.
- **Embedded Pseudo-Filesystem:** Declares static metadata entries for `/system/status`, `/receipts/last`, `/apps/hello.bogapp`, and `/apps/bad-hello.bogapp`.
- **Verified App Loader & Output:** Gated loader structure checks SHA-256 hashes on execution, prints security block alerts on failure, and exposes kernel-controlled output events (`hello_from_verified_bogos_app`).
- **COM1 Receipt Logging:** Emits machine-checkable boot/demo and app execution receipts to the serial port.

### Verification
Validated with:
- `python3 -m unittest discover -v`
- `python3 scripts/evaluate_bogos_qemu_demo_system.py`
- `python3 scripts/evaluate_bogkernel_app_bundle.py`
- `python3 scripts/evaluate_bogkernel_verify_accept.py`
- `python3 scripts/evaluate_bogkernel_vm_exec.py`
- `python3 scripts/evaluate_bogkernel_boot.py`
- `cd kernel && cargo test -p bogk-core`

### Boundaries
This is a narrow QEMU demo system spike:
- QEMU only.
- Writable pseudo-files are simulated dynamically in-memory.
- No general storage/disk driver or real filesystem.
- No scheduler, multitasking, network stack, or physical hardware drivers.

## v19.0.0: Native Verified Embedded App Bundle

BOGBIN v19.0.0 introduces native verified embedded app bundle support within BogKernel.

This release defines the `AppBundle` structure in `bogk-core`, compiles static app bundles into the kernel image, verifies their bytecode hash natively using freestanding SHA-256, and executes accepted bundles.

### Implementation
- **AppBundle & Manifest Structures:** Adds `AppBundle` and `AppManifest` structures to compile static apps (bytecode, name, version, expected hash, metadata) directly into the kernel.
- **Native Bundle Verification:** Computes the SHA-256 hash of the app bytecode natively and asserts equality with the expected hash before execution.
- **Gated VM Execution:** If verification succeeds, the app bytecode executes. If it fails, execution is blocked and the status is marked as rejected.
- **Deterministic Receipt Markers:** Emits structured output for both the positive (accepted/executed) and negative (rejected/blocked) paths to COM1.

### Verification
Validated with:
- `python3 -m unittest discover -v`
- `python3 scripts/evaluate_bogkernel_vm_exec.py`
- `python3 scripts/evaluate_bogkernel_verify_accept.py`
- `python3 scripts/evaluate_bogkernel_app_bundle.py`
- `cd kernel && cargo test -p bogk-core`

### Boundaries
This is a narrow native app bundle proof:
- QEMU only.
- Static/embedded bundles compiled into the image.
- No general app loader, filesystem, scheduler, interrupts, BIOS, or physical drivers.
- Data and programs remain unaccepted and unexecuted until verified.

## v18.0.0: Native VERIFY_HASH and ACCEPT_DATA Proof


BOGBIN v18.0.0 introduces native hash verification and data acceptance within BogKernel.

This release adds a freestanding, allocation-free (`no_std`) SHA-256 implementation to `bogk-core` and extends the native BOGVM executor to support `VERIFY_HASH`, `ACCEPT_DATA`, and `REJECT_DATA` opcodes.

### Implementation
- **Freestanding SHA-256:** A zero-allocation SHA-256 implementation that computes hashes on the bare metal.
- **Verification Opcodes:** Implements `VERIFY_HASH (0x13)`, `ACCEPT_DATA (0x14)`, and `REJECT_DATA (0x17)`.
- **Dual Verification Runs:** The kernel performs both a positive verification run (correct expected hash) and a negative verification run (incorrect expected hash) on an embedded payload, emitting serial verification receipts.
- **SSE CPU Enablement:** The assembly entrypoint (`kernel_entry`) enables SSE/SSE2 coprocessor support on the CPU to safely run Rust code using vector-based compiler optimizations.

### Verification
Validated with:
- `python3 -m unittest discover -v`
- `python3 scripts/evaluate_bogkernel_vm_exec.py`
- `python3 scripts/evaluate_bogkernel_verify_accept.py`
- `cd kernel && cargo test -p bogk-core`

### Boundaries
This is a narrow native verification spike:
- QEMU only.
- No full OS (no scheduler, interrupts, filesystem, or bios).
- No physical hardware support.
- Existing Python/user-space BogOS stack remains the primary implementation.
- Data remains unaccepted until verified.

## v17.0.0: Native Minimal BOGVM Execution

BOGBIN v17.0.0 introduces the first native BOGVM execution path inside BogKernel.

This release adds a minimal native Rust executor that decodes and executes embedded bytecode (NOOP/HALT) and emits execution receipts over serial.

### Implementation
- **Instruction Decoder:** Decodes 8-byte big-endian instructions (`>BBHHH`).
- **Minimal Executor:** Supports `NOOP (0x00)` and `HALT (0x01)`.
- **Execution Receipt:** Emits instruction count, PC advancement, and status markers to COM1.
- **Embedded Program:** The kernel now executes a static NOOP + HALT program upon boot.

### Verification
Validated with:
- `python3 -m unittest discover -v`
- `python3 scripts/evaluate_verifier_first_vertical.py`
- `python3 scripts/evaluate_bogkernel_boot.py`
- `python3 scripts/evaluate_bogkernel_vm_exec.py`
- `cd kernel && cargo test -p bogk-core`

### Boundaries
This is a narrow native VM spike:
- QEMU only
- minimal NOOP/HALT executor only
- no full VM yet
- no `VERIFY_HASH` / `ACCEPT_DATA` yet
- no interrupts yet
- no filesystem yet
- no scheduler yet
- no physical hardware support yet
- Existing Python/user-space BogOS stack remains the primary implementation.

## v16.0.0: Bootable BogKernel QEMU Spike

BOGBIN v16.0.0 introduces the first native bootable BogKernel proof.

This release adds an i686/ELF32 Multiboot1 kernel that boots under x86 QEMU and emits deterministic serial receipt markers.

### Verification
Validated with:
- `python3 -m unittest discover -v`
- `python3 scripts/evaluate_verifier_first_vertical.py`
- `python3 scripts/evaluate_bogkernel_boot.py`

### Kernel artifact audit
The v16 host-side evaluator (`scripts/evaluate_bogkernel_boot.py`) verifies:
- ELF class: ELF32
- machine: Intel 80386 / i686
- entry point: 0x100150
- no dynamic interpreter
- no dynamic section
- no undefined symbols
- QEMU boot success
- serial markers from `BOGKERNEL_BOOT_BEGIN` to `BOGKERNEL_BOOT_END` on COM1

### Boundaries
This is a narrow native kernel spike:
- QEMU only
- not a full OS
- not physical hardware support
- not a BIOS
- not a real driver stack
- not interrupt admission yet
- not VM opcode execution yet
- Existing Python/user-space BogOS stack remains the primary reference implementation.

## v15.0.0: Verifier-First Vertical Expansion

- Adds BogMesh signed claims, peer trust, deterministic conflict pressure, quarantine, winner, convergence, and context-split receipts.
- Adds BogPilot Swarm budgeted candidate tournaments, deterministic best-path selection, Genesis-only admission, and replay verification.
- Adds BogBoot QEMU-reference device/memory manifests and signed boot receipts.
- Adds BogIRQ device-boundary claim gating with monotonic ticks, capabilities, quarantine, hardware state roots, and verification.
- Adds `bog vertical demo` and `scripts/evaluate_verifier_first_vertical.py` for the complete signed vertical proof.

### Boundary

BogBoot and BogIRQ model QEMU/device-boundary behavior in user space. They are not a physical bootloader, driver stack, pin-level verifier, or bare-metal kernel. BogMesh is a signed local-first reference transport, not Byzantine consensus.

## v10.0.0: BogOS HyperGenesis: Portable Self-Verifying Computer

v10 turns the local Genesis world into portable, third-party-verifiable, capability-only compute.

- Adds `bog hypergenesis demo`, the complete trusted-boot-through-portable-replay flagship proof.
- Adds BogNet `.bogproof` export, clean verification, and replay with no private key material.
- Adds BogCell, a deterministic app VM whose only I/O instructions are Bog-mediated capabilities.
- Adds BogBuild, a tiny `.bogsrc` compiler with signed source, compiler, bytecode, and capability evidence.
- Adds `bog ledger verify` over both receipt history and immutable state history.
- Adds `bog state diff`, `bog state checkout`, and `bog state prove-file`.
- Adds BogPilot, where planner proposals have no authority and every action is verified or blocked.
- Adds signed-directory registry mirroring through `bog registry sync --source`.
- Adds `scripts/evaluate_hypergenesis.py`, producing the final receipt and portable `.bogproof`.

### Boundary

- BogCell is intentionally small and deterministic; it is not a general native runtime.
- Native/Python BogK apps retain the v8/v9 host-syscall boundary.
- BogPilot is a local deterministic planner demonstration. Proof authority remains with Bog.

## v9.0.0: BogOS Genesis: Verified Session OS

v9 turns the verified workspace and BogK runtime into a complete local, user-space operating environment proof.

- `bog genesis demo` executes trusted boot, signed local registry sync, lockfile verification, signed dependency-pinned installs, brokered app runs, verified state changes, forbidden-access rejection, tamper rejection, rollback, and full-session replay.
- `bog boot` records the exact workspace, trust store, installed package index, kernel state, registry, lockfile, previous proof root, and writable state root being entered.
- Genesis receipts are Ed25519-signed and chained with `previous_hash` into an append-only local transparency ledger.
- The signed local registry describes exact package versions, dependencies, bundle/tree/receipt hashes, signing key IDs, and capability requirements.
- `bog.lock` pins the registry hash/signature, trusted key IDs, exact packages, dependencies, and hashes.
- Genesis writable BogFS stores immutable content-addressed objects and copy-on-write state manifests.
- `bog rollback <receipt>` restores a prior verified state root without deleting later objects.
- `bog shell` provides controlled `status`, `install`, `run`, `fs read`, `fs write`, `ledger`, `rollback`, and `replay session` commands.
- `bog replay-session [genesis_receipt.json]` verifies the receipt chain and deterministically replays all recorded state-root transitions.
- `scripts/evaluate_genesis.py` emits `artifacts/genesis_receipt.json`.

### Boundary

- BogOS Genesis is a verifier-first operating substrate in user space, not a bootable kernel or host syscall sandbox.
- The registry is local and signed. Remote transport and version-range solving remain future work.

## v8.0.0: BogK Capability Runtime

v8 moves Bog-native apps from observed post-run policy toward brokered pre-access capabilities.

- Adds the `bog_runtime` ABI: `bog_read`, `bog_write`, `bog_env`, `bog_dependency`, and `bog_receipt`.
- `BOGOS-app-manifest-8.0` adds explicit read/write/env/dependency capabilities.
- `bog kernel run --brokered <app>` verifies package, dependency, signature, and app policy state before starting a brokered process.
- BogK re-verifies the app package and authorizes each official I/O request before access, then emits ordered `BOGK-capability-syscall-receipt-8.0` nodes.
- Final `BOGK-brokered-process-receipt-8.0` receipts link package/dependency/policy verification, syscall evidence, process output hashes, and a final proof hash.
- `bog kernel replay <receipt.json>` re-verifies current package/tree/dependency/policy state, syscall order/evidence, brokered outputs, and the final proof hash.
- `scripts/evaluate_bogk_capability_runtime.py` emits the BogK Brokered Capability Proof, including allowed operations, pre-access blocks, tamper-before-start rejection, and replay.
- Current BogK state and operation receipts use `8.0` formats; existing `BOGK-state-7.0` workspaces migrate on open.

### Boundary

- Brokered Bog-native apps use BogK as their official I/O path.
- Brokered mode is not a host-kernel sandbox. Arbitrary direct native syscalls remain outside BogK's prevention boundary.
- Legacy app execution remains post-run checked.

## v7.0.0: BogK User-Space Kernel Contract

v7.0.0 adds BogK, a user-space kernel contract for verified workspace operations over BogOS Lite.

The final v7.0.0 release also adds:

- Draft 2020-12 schemas and runtime validation for archive manifests, decoded BOGPK metadata, package receipts, `bog_app.json`, common receipts, and BogK receipts.
- Ed25519-signed package receipts, workspace trust stores, and trusted-signature enforcement for install, verify, app run, doctor, and BogK operations.
- Explicit dependency metadata with transitive archive/tree/package/signature verification.
- `THREAT_MODEL.md`, which separates runtime policy from sandboxing and defines what counts as proof.
- `scripts/evaluate_signed_dependency_demo.py`, which emits one final proof receipt after a signed dependency/app install, BogK run, tamper rejection, and undeclared-write rejection.

The release version is `v7.0.0`. Existing BogK wire-format identifiers retain their `7.0` suffix for compatibility.

Proof:

- `bog kernel boot` creates `.bogos/kernel/state.json` with `BOGK-state-7.0`, plus kernel receipts, process records, mount records, and a JSONL syscall log.
- `bog kernel status` reports boot state, deterministic process records, visible apps/mounts, syscall count, and kernel receipt state.
- `bog kernel run <app>` delegates execution to the existing v6 verified app path and wraps the result in a deterministic `BOGK-process-receipt-7.0`.
- Tampered installed packages remain blocked before app execution.
- `bog kernel syscall read <mount> <path>` delegates to the existing verified BogFS-mounted read path and records a `BOGK-syscall-receipt-7.0`.
- `bog kernel syscall write <app> <path> <data>` only writes inside `.bogos/appdata/<app>/` when the app manifest write policy allows the path.
- Unknown apps, mounts, syscalls, unsafe paths, and undeclared writes are blocked with kernel receipts.
- `scripts/evaluate_bog_kernel_lite.py` emits `artifacts/bog_kernel_lite_report.json` and `artifacts/bog_kernel_lite_receipt.json`.

Boundary:

- BogK is a user-space kernel contract, not a real OS kernel, bootloader, bare-metal runtime, driver stack, or syscall-tracing sandbox.
- Trusted package signature/dependency verification and the v6 runtime policy remain proof authority.

## v6.0.0: Verified App Runtime Policy

v6.0 moves BogOS Lite from "is this package valid before I run it?" to "what is this app allowed to touch?"

Proof:

- `bog_app.json` app entries now define a runtime policy: app name, entrypoint, allowed files, expected hashes, permissions, environment variables, read policy, write policy, and receipt path.
- `bog app run app-name` verifies the installed package before execution, verifies manifest-declared file hashes, runs from `.bogos/appdata/<app>/`, and records a `BOGOS-app-runtime-policy-receipt-6.0` inside the app-run receipt.
- App subprocesses receive a controlled environment including `BOG_PACKAGE_DIR`, `BOG_APP_RUNTIME_DIR`, `BOG_APP_ALLOWED_FILES`, `BOG_APP_READ_POLICY`, `BOG_APP_WRITE_POLICY`, and `BOG_APP_RECEIPT_PATH`.
- Runtime writes are diffed after execution. Undeclared writes are blocked in the receipt.
- Installed package files are snapshotted before and after execution. Package mutation during app run is blocked.
- v5-style app manifests without policy fields are no longer enough for an accepted app run.

Boundary:

- This is a verified local runtime policy layer, not a kernel sandbox.
- Read policy is declared and file-hash verified, but Python subprocess execution is not syscall-traced.
- Network and subprocess permissions are not granted in v6.
- At v6.0.0, there was no remote trust, dependency solving, or signature verification.

## v5.0.0: Verified App/Package Demo

v5.0 moves the story from verified workspace to verified local software environment.

Proof:

- Packages may include `bog_app.json` with app entrypoints.
- `bog store install demo-app --name demo-app --version 1.0.0` installs a runnable app package into the verified store.
- `bog store verify demo-app-1.0.0` verifies installed package data and archive recipes.
- `bog app run demo-app` verifies the installed package before running its app command.
- If installed app files are corrupted, `bog app run demo-app` blocks before execution and records the verification failure.

Boundary:

- App execution is local subprocess execution after verification.
- This is not a sandbox, dependency solver, remote package ecosystem, or signature authority.

## v4.5.0: Public Demo Pack

v4.5 adds a one-command public proof loop.

Proof:

- `bog demo pack` creates a fixture app project inside the workspace.
- The demo archives, restores, mounts, reads through BogFS, installs into the package store, verifies, runs the app, corrupts installed data, rejects the corrupted package, and emits a final report.
- `scripts/evaluate_bogos_lite_demo.py` writes `artifacts/bogos_lite_demo_report.json` and `artifacts/bogos_lite_demo_receipt.json`.

Boundary:

- The demo pack is a deterministic local proof artifact.
- It is not a benchmark or remote trust workflow.

## v4.1.0: BogOS Lite UX Hardening

v4.1 makes the workspace inspectable.

Proof:

- `bog doctor` verifies workspace directories, archives, and installed packages.
- `bog status --verbose` reports archive, mount, package, app, receipt, and latest-receipt details.
- `bog receipt latest` is an explicit alias for the latest receipt.
- `bog corrupt-test package` mutates installed data and verifies that Bog rejects it.
- `bog workspace tree` prints workspace archives, mounts, packages, apps, receipts, and restored entries.

Boundary:

- UX hardening improves local observability; it does not add kernel, driver, or remote registry behavior.

## v4.0.0: BogOS Lite

v4.0 adds a user-level Bog-managed workspace. This is not a kernel, BIOS, bootloader, or driver milestone.

Proof:

- `bog init workspace` creates `.bogos/` workspace state, archive storage, receipt storage, and a local package store.
- `bog archive project/` stores a project as a verified Bog archive under the workspace.
- `bog restore archive` restores a workspace archive exactly and records a receipt.
- `bog fs mount archive name` verifies and records a read-only BogFS mount.
- `bog fs read mount path` reconstructs bytes from recipes and records a read receipt.
- `bog store install package` packages a source directory when needed, installs it into the workspace store, and records receipts.
- `bog store verify package` verifies installed package data and package archive recipes.
- `bog status` reports archives, mounts, packages, receipts, and the latest receipt.
- `bog receipt` prints the latest receipt.
- The killer-demo test archives a mixed project, restores it, installs it, reads it through BogFS, corrupts installed data, verifies again, and gets a blocked receipt explaining the hash mismatch.

Boundary:

- BogOS Lite is user-space workspace management.
- BogFS remains read-only.
- At v4.0.0, the package store was local and did not resolve dependencies, fetch remotes, or verify signatures.
- Rejection receipts explain local verification failure reasons; they are not legal/security attestations.

## v3.0.0: Bog Package Store

v3.0 adds local verified recipe bundles.

Proof:

- `python3 -m bogvm store package` builds a bundle from a source directory archive and writes a package receipt.
- `python3 -m bogvm store install` verifies the bundle receipt, restores the archive, checks the tree hash, and records the package in `index.json`.
- Install receipts include package key, archive tree hash, bundle hash, restored tree hash, and execution status.

Boundary:

- No dependency solver yet.
- No remote registry yet.
- No signature authority yet.
- Package installs are verified local recipe-bundle installs.

## v2.5.0: BogFS Prototype

v2.5 adds a read-only filesystem-style layer over BOG directory archives.

Proof:

- `BogFS.listdir()` enumerates archive entries.
- `BogFS.stat()` returns path, size, and SHA-256.
- `BogFS.read_bytes()` and `read_text()` reconstruct file bytes from `.bogpk` recipes and verify object hashes.
- CLI access is available through `python3 -m bogvm fs ls|stat|cat`.

Boundary:

- This is a userspace read API and CLI, not a kernel mount.
- Writes are not supported.

## v2.0.0: Directory Roundtrip

v2.0 adds the first proper folder milestone.

Proof:

- `python3 -m bogvm archive source archive_dir --receipt ...` stores each file as a verified `.bogpk` object and writes a deterministic manifest.
- `python3 -m bogvm restore archive_dir output_dir --receipt ...` reconstructs every file and verifies file hashes plus the whole tree hash.
- Tests cover a mixed folder containing a small website, Python file, image-like bytes, audio-like bytes, text, JSON, and binary data.

Boundary:

- Archive manifests and tree hashes verify directory reconstruction outside the VM.
- File object reconstruction still uses the existing BOGPK recipe path.

## v1.9.0: Real Corpus Smoke

v1.9 keeps the deterministic real-file smoke active on text, JSON, binary, PNG, and WAV fixtures.

Proof:

- `scripts/evaluate_real_file_roundtrip.py` emits a v2.0-format report and receipt.
- Every case packs to `.bogpk`, compiles to `.bogbin`, runs through BOGVM verification, unpacks, and matches SHA-256.

Boundary:

- This is a correctness smoke, not a benchmark suite.

## v1.8.0: Transform Tournament Upgrade

v1.8 changes transform selection from residual-density-only selection to cost-aware selection.

Proof:

- Candidate plans carry scoring metadata.
- Scoring includes estimated packed container size, residual count, transform cost, basis cost, and decode cost.
- Tie-breaking remains deterministic.

Boundary:

- Costs are deterministic estimates for choosing plans, not measured CPU timings.

## v1.7.0: BOGPK Hardening

v1.7 makes the binary parser defensive.

Proof:

- Rejects bad magic.
- Rejects non-minimal, oversized, and truncated varints.
- Rejects reserved flags, transform IDs, and basis IDs.
- Rejects residual offsets outside implied chunk length.
- Rejects impossible chunk counts and residual totals.
- Rejects invalid bitmask offsets and bad BWT transform params.
- Rejects trailing bytes and whole-payload hash mismatches.

Boundary:

- Optional per-chunk hash streams remain reserved in this implementation.

## v1.6.0: Binary-Packed BOGPK Container

v1.6 adds the first binary-packed `.bogpk` container path beside JSON `.bog`.

Proof:

- Transform and basis selections are packed into one descriptor byte.
- Chunk offsets are implicit from chunk index and selected chunk size.
- Residual patch offsets are delta-coded.
- Dense residual patches can use per-chunk bitmasks.
- Repeated zero-residual chunks can be encoded as zero-run records.
- `.bogpk` byte streams decode back into normal chunk plans and feed the existing compile/unpack paths.
- Sorting transforms `mtf`, `bwt`, and `bwt_mtf` are included in the transform tournament.

Report:

- JSON `.bog` mean container/input ratio: `38.548519`
- Current `.bogpk` mean container/input ratio: `0.960163`
- Aggregate `.bogpk` container size smaller than input: `true`
- All `.bogpk` containers smaller than input: `false`
- Exact roundtrip: 5/5

Boundary:

- The aggregate compression threshold is crossed, but per-file threshold is not crossed for every fixture.
- No entropy coding yet.
- VM proof authority remains hash-gated acceptance.

## v1.5.0-dev: Reversible Transform Tournament

v1.5 development executes the first reversible transform tournament and adds a bounded integer-only Fourier-style basis.

Proof:

- Candidate transforms are evaluated deterministically before basis selection: `identity`, `xor_previous`, `delta_previous`, `nibble_split`, `mtf`, `bwt`, and `bwt_mtf`.
- Each transformed chunk is optimized with the existing residual basis tournament.
- The compiled VM verifies transformed chunk bytes with `VERIFY_HASH` + `ACCEPT_DATA`.
- Container unpacking inverts the selected transform and verifies both original chunk SHA-256 and whole-payload SHA-256.
- `fourier8_u8` uses fixed 8-step integer sine/cosine lookup tables and integer arithmetic only.
- The report emits compression-threshold evidence instead of claiming victory.

Report:

- v1.2 mean residual density: `0.631188`
- v1.4 transform-free report density: `0.576098`
- Current transform-enabled mean residual density: `0.469867`
- Exact roundtrip: 5/5
- All `.bog` containers smaller than input: `false`

Boundary:

- Not a compression victory claim.
- Not a claim that `.bog` beats ZIP/PNG/WAV/etc.
- Fourier support is one bounded integer-only basis, not a full spectral compressor.
- TS-BIOS and bare-metal execution remain roadmap work.

## v1.4.0: Reversible Transform Framing and Verification Hardening

v1.4.0 frames the next storage path around reversible transform selection plus exact verification hardening. It updates the current execution path and real-file report without making a compression victory claim.

Proof:

- Verifier-rejected claim acceptance is repaired into deterministic rejected and quarantined claim state.
- Unverified or abstained claim acceptance remains blocked by `LAW_002`.
- Residual optimizer output is replay-checked before use: basis synthesis plus residual patches must reconstruct the target SHA-256 exactly.
- The real-file report now evaluates deterministic text, JSON, binary, valid PNG, and valid WAV payloads.
- The staged v0.2-v0.6 audit is documented against the BOGBIN-0.1 VM laws.
- No reversible transform tournament report/receipt artifact is generated in this release.

Report:

- v1.2 mean residual density: `0.631188`
- Current mean residual density: `0.576098`
- Residual density delta from v1.2: `-0.05509`
- Residual density improved from v1.2: `true`
- Exact roundtrip: 5/5

Verification:

~~~bash
python3 -m unittest discover -s tests
python3 scripts/evaluate_real_file_roundtrip.py
~~~

Boundary:

- Reversible transform selection is release framing and boundary-setting here; tournament implementation/reporting remains future work.
- Contradiction repair only applies after verifier result `rejected`.
- Unverified acceptance remains blocked.
- Valid PNG/WAV fixtures are deterministic small fixtures, not compression benchmarks.
- Exactness remains verified through BOGVM and SHA-256 checks.

## v1.3.0: Adaptive Chunk Tournament

v1.3.0 adds deterministic adaptive chunk-size selection.

Proof:

- Container packing can evaluate chunk sizes `16`, `32`, `64`, and `128`.
- Candidate plans are scored by total residual count, residual density, chunk count, then chunk size.
- `.bog` metadata records whether the tournament was enabled, candidate chunk sizes, selected chunk size, selected residual count, selected density, and per-candidate results.
- `python3 -m bogvm pack input.bin output.bog --auto-chunk --receipt ...` enables the tournament.
- Explicit `--chunk-size` behavior is preserved.
- Exact roundtrip remains 5/5 on the real-file report.

Report:

- v1.2 mean residual density: `0.631188`
- Current mean residual density: `0.555693`
- Residual density delta from v1.2: `-0.075495`
- Residual density improved from v1.2: `true`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 scripts/evaluate_real_file_roundtrip.py
~~~

Boundary:

- Adaptive deterministic chunk-size tournament only.
- Not a compression benchmark victory.
- Not a claim that `.bog` beats ZIP/PNG/WAV/etc.
- Not Fourier.
- Not hardware execution.
- Exactness remains verified through BOGVM and SHA-256 checks.

## v1.2.0: Dictionary + Delta Bases

v1.2.0 adds deterministic bases to reduce residual density on the real-file roundtrip report.

Proof:

- `zero_block` generates all-zero chunks.
- `delta_u8` generates arithmetic byte sequences with `byte[i] = (start_byte + i * delta) mod 256`.
- The optimizer searches delta values `0..255` deterministically and chooses the best start byte for each delta.
- `dictionary_u8` and `rle_u8` are deterministic one-byte base generators for this release; exactness still comes from residual patches and SHA-256 verification.
- Tie-breaking remains residual count, basis order, then coefficient tuple.
- Exact roundtrip remains 5/5 on the real-file report.

Report:

- Baseline mean residual density: `0.867574`
- Current mean residual density: `0.631188`
- Residual density delta: `-0.236386`
- Residual density improved: `true`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 scripts/evaluate_real_file_roundtrip.py
~~~

Boundary:

- Adds deterministic bases and residual-density comparison.
- Not a compression benchmark victory.
- Not a claim that `.bog` beats ZIP/PNG/WAV/etc.
- Not Fourier.
- Not hardware execution.
- Exactness remains verified through BOGVM and SHA-256 checks.

## v1.1.0: Basis Tournament + Real File Report

v1.1.0 adds a deterministic real-file evaluation/report harness.

Proof:

- `scripts/evaluate_real_file_roundtrip.py` builds deterministic fixture files for text, JSON, binary/noise-like, PNG-like, and WAV-like payloads.
- Each case is packed to `.bog`, compiled to `.bogbin`, verified through BOGVM, unpacked, and SHA-256 compared against the original.
- The report records basis counts, residual density, chunk counts, hashes, VM run status, and roundtrip pass/fail.
- Every accepted case must recover exact bytes.

Artifacts:

- `artifacts/real_file_roundtrip_report.json`
- `artifacts/real_file_roundtrip_receipt.json`
- `docs/real_file_roundtrip_report.md`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 scripts/evaluate_real_file_roundtrip.py
~~~

Boundary:

- Real-file roundtrip report only.
- Not a compression benchmark victory.
- Not a claim that `.bog` beats existing formats.
- Not Fourier.
- Not hardware execution.
- Exactness remains verified through BOGVM and SHA-256 checks.

## v1.0.0: Exact File Roundtrip

v1.0.0 adds exact deterministic file reconstruction.

Proof:

- `reconstruct_bog_container_bytes(container)` reconstructs every chunk from basis, start byte, length, and residual patches.
- Reconstruction verifies each `chunk_sha256`.
- Reconstructed chunks are concatenated in deterministic index order.
- The final byte stream is checked against `whole_sha256`.
- `python3 -m bogvm unpack` writes recovered bytes and an unpack receipt.
- A file can complete: `input.bin -> output.bog -> output.bogbin -> verified VM run -> recovered.bin`.

Artifacts:

- `examples/roundtrip_payload.bin`
- `artifacts/roundtrip_payload.bog`
- `artifacts/roundtrip_payload.bogasm`
- `artifacts/roundtrip_payload.bogbin`
- `artifacts/roundtrip_payload_pack_receipt.json`
- `artifacts/roundtrip_payload_run_receipt.json`
- `artifacts/roundtrip_payload_unpack_receipt.json`
- `artifacts/roundtrip_payload_recovered.bin`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm pack examples/roundtrip_payload.bin artifacts/roundtrip_payload.bog --chunk-size 64 --receipt artifacts/roundtrip_payload_pack_receipt.json
python3 -m bogvm compile artifacts/roundtrip_payload.bog artifacts/roundtrip_payload.bogbin --bogasm artifacts/roundtrip_payload.bogasm
python3 -m bogvm run artifacts/roundtrip_payload.bogbin --receipt artifacts/roundtrip_payload_run_receipt.json
python3 -m bogvm unpack artifacts/roundtrip_payload.bog artifacts/roundtrip_payload_recovered.bin --receipt artifacts/roundtrip_payload_unpack_receipt.json
sha256sum examples/roundtrip_payload.bin artifacts/roundtrip_payload_recovered.bin
~~~

Boundary:

- Exact deterministic file roundtrip.
- Not compression victory.
- Not Fourier.
- Not hardware execution.
- VM verification remains proof authority.

## v0.9.0: .bog Container Compiler

v0.9.0 adds a deterministic `.bog` container format and compiler.

Proof:

- `build_bog_container(data, chunk_size=64)` creates a deterministic `BOG-0.9` JSON-compatible container.
- The container stores chunk names, offsets, lengths, basis choices, start bytes, residuals, per-chunk SHA-256 hashes, total residual count, and whole-file SHA-256.
- `write_bog_container()` writes canonical JSON with sorted keys and stable separators.
- `read_bog_container()` validates required fields and schema constraints.
- `compile_bog_container_to_bogasm()` deterministically compiles container plans into ordinary `.bogasm`.
- `python3 -m bogvm compile` assembles that `.bogasm` into `.bogbin`.
- Running the compiled `.bogbin` verifies and accepts each chunk through VM `VERIFY_HASH` + `ACCEPT_DATA`.

Artifacts:

- `examples/container_payload.bin`
- `artifacts/container_payload.bog`
- `artifacts/container_payload.bogasm`
- `artifacts/container_payload.bogbin`
- `artifacts/container_payload_pack_receipt.json`
- `artifacts/container_payload_run_receipt.json`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm pack examples/container_payload.bin artifacts/container_payload.bog --chunk-size 64 --receipt artifacts/container_payload_pack_receipt.json
python3 -m bogvm compile artifacts/container_payload.bog artifacts/container_payload.bogbin --bogasm artifacts/container_payload.bogasm
python3 -m bogvm run artifacts/container_payload.bogbin --receipt artifacts/container_payload_run_receipt.json
~~~

Boundary:

- `.bog` container compiler only.
- `.bog` is a deterministic storage/manifest container.
- `.bog` is not proof authority.
- VM verification remains proof authority.
- Not compression victory.
- Not Fourier.
- Not hardware execution.

## v0.8.0: Chunked Auto Pack

v0.8.0 adds deterministic chunked automatic packing.

Proof:

- `optimize_chunked_residual_plan(data, chunk_size=64)` splits input bytes into sequential chunks.
- Each chunk is optimized independently with the existing residual optimizer and deterministic tie-breaking.
- `pack_chunked_bytes_to_bogasm()` emits one data block per chunk: `payload_chunk_0000`, `payload_chunk_0001`, and so on.
- Every chunk is synthesized, residual-patched, `VERIFY_HASH` checked, and `ACCEPT_DATA` accepted independently by the VM.
- `python3 -m bogvm pack` defaults to chunked mode when input length is greater than `--chunk-size`.
- `--single-block` preserves the v0.7 one-block `payload` behavior.
- The pack receipt includes deterministic `chunk_count`, `chunk_size`, `total_residual_count`, and `whole_sha256`.

Whole-payload boundary:

- v0.8 does not add a whole-payload VM opcode.
- The VM verifies chunks.
- The pack receipt records the whole input SHA-256 deterministically as `whole_sha256`.
- The verifier boundary remains authoritative for accepted chunk data through `VERIFY_HASH` + `ACCEPT_DATA`.

Artifacts:

- `examples/chunked_payload.bin`
- `artifacts/chunked_payload.bogasm`
- `artifacts/chunked_payload.bogbin`
- `artifacts/chunked_payload_receipt.json`
- `artifacts/chunked_payload_run_receipt.json`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm pack examples/chunked_payload.bin artifacts/chunked_payload.bogbin --chunk-size 64 --bogasm artifacts/chunked_payload.bogasm --receipt artifacts/chunked_payload_receipt.json
python3 -m bogvm run artifacts/chunked_payload.bogbin --receipt artifacts/chunked_payload_run_receipt.json
~~~

Boundary:

- Chunked deterministic auto-pack only.
- Not a `.bog` container compiler yet.
- Not compression victory.
- Not Fourier.
- Not hardware execution.

## v0.7.0: Automatic Residual Optimizer

v0.7.0 adds a deterministic automatic pack pipeline.

Public wording:

BOGBIN v0.7 adds automatic residual optimization: arbitrary bytes can be represented as deterministic generated base + exact residual patches, then verified by SHA-256 before acceptance.

Proof:

- `bogvm.bases.synthesize_basis()` is the shared deterministic basis implementation for `repeat_byte`, `ramp_u8`, `triangle_u8`, and `sine8_u8`.
- `bogvm.optimizer.optimize_residual_plan()` exhaustively tests every existing basis and every start byte `0..255`.
- The optimizer chooses by smallest residual count, then basis order, then lowest start byte.
- `bogvm.packer.pack_bytes_to_bogasm()` emits deterministic `.bogasm` with `STORE_RESIDUAL` patches, `VERIFY_HASH`, and `ACCEPT_DATA`.
- `python3 -m bogvm pack` reads bytes, emits `.bogasm`, assembles `.bogbin`, runs BOGVM, checks the receipt accepted `payload`, and writes the receipt.

Artifacts:

- `examples/auto_pack_payload.bin`
- `artifacts/auto_pack_payload.bogasm`
- `artifacts/auto_pack_payload.bogbin`
- `artifacts/auto_pack_payload_receipt.json`
- `artifacts/auto_pack_payload_run_receipt.json`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm pack examples/auto_pack_payload.bin artifacts/auto_pack_payload.bogbin --bogasm artifacts/auto_pack_payload.bogasm --receipt artifacts/auto_pack_payload_receipt.json
python3 -m bogvm run artifacts/auto_pack_payload.bogbin --receipt artifacts/auto_pack_payload_run_receipt.json
~~~

Boundary:

- Automatic residual optimization only.
- Not a compression victory claim.
- Not Fourier yet.
- Not a `.bog` container compiler yet.
- Not hardware/laptop execution yet.
- Exactness comes from `VERIFY_HASH` + `ACCEPT_DATA` gate.

## v0.1.1: Blocked Execution Receipts

v0.1.1 makes blocked VM-law failures auditable. Contradictory programs now emit blocked receipts instead of only tracebacking.

Proof:

- `examples/contradiction.bogasm` creates support and conflict pressure on the same claim.
- `INTERFERE` reports support pressure, conflict pressure, net pressure, and tension.
- `VERIFY` rejects the claim.
- `ACCEPT` is blocked because the claim is not verified.
- The CLI writes `artifacts/contradiction_receipt.json`.

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm assemble examples/contradiction.bogasm artifacts/contradiction.bogbin
python3 -m bogvm run artifacts/contradiction.bogbin --receipt artifacts/contradiction_receipt.json || echo "blocked receipt emitted"
~~~

Boundary:

- Blocked execution is not success.
- Blocked execution is still auditable.
- No `ACCEPT` without `VERIFY`.
- Candidate graph contamination remains zero.

## v0.1.0: Minimal Wave-State Binary VM

v0.1.0 creates the first minimal BOGVM.

Proof:

- `.bogasm` source assembles into `.bogbin`.
- BOGVM executes fixed-point sparse graph-state propagation.
- `examples/proof_chain.bogasm` verifies `A -> B -> C`, then accepts `claim_A_C`.
- The VM emits `artifacts/proof_chain_receipt.json`.

Boundary:

- This is a toy VM proof, not a full operating system.
- No Fourier/generative storage yet.
- No laptop port yet.
- No direct hardware execution yet.

## v0.2.0: Hash-Gated Generative Storage Opcodes

v0.2.0 adds the first deterministic generative storage surface to BOGVM.

Proof:

- `DECLARE_BASIS repeat_byte` declares a deterministic generator basis.
- `LOAD_COEFFICIENTS` stores generation parameters instead of raw output bytes.
- `SYNTHESIZE` reconstructs a generated data block.
- `VERIFY_HASH` checks the regenerated bytes against an expected SHA-256 hash.
- `ACCEPT_DATA` only accepts generated data after hash verification.
- Bad generated data/hash paths emit blocked receipts.

Artifacts:

- `examples/repeat_byte_storage.bogasm`
- `examples/repeat_byte_bad_hash.bogasm`
- `artifacts/repeat_byte_storage.bogbin`
- `artifacts/repeat_byte_storage_receipt.json`
- `artifacts/repeat_byte_bad_hash.bogbin`
- `artifacts/repeat_byte_bad_hash_receipt.json`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm assemble examples/repeat_byte_storage.bogasm artifacts/repeat_byte_storage.bogbin
python3 -m bogvm run artifacts/repeat_byte_storage.bogbin --receipt artifacts/repeat_byte_storage_receipt.json
python3 -m bogvm assemble examples/repeat_byte_bad_hash.bogasm artifacts/repeat_byte_bad_hash.bogbin
python3 -m bogvm run artifacts/repeat_byte_bad_hash.bogbin --receipt artifacts/repeat_byte_bad_hash_receipt.json || echo "bad hash correctly blocked"
~~~

Boundary:

- This is a deterministic toy generator, not a compression victory claim.
- Generated data is not accepted without hash verification.
- No Fourier/wave basis yet.
- No `.bog` container compiler yet.
- No laptop port yet.

## v0.3.0: Deterministic Integer Wave Basis

v0.3.0 adds the first position-dependent deterministic generator basis.

Proof:

- `DECLARE_BASIS ramp_u8` declares an integer wave-style basis.
- `LOAD_COEFFICIENTS` stores start byte and length.
- `SYNTHESIZE` reconstructs generated bytes using the rule:
  `byte[i] = (start + i) mod 256`
- `VERIFY_HASH` checks the reconstructed byte field.
- `ACCEPT_DATA` accepts only after hash verification.

Artifacts:

- `examples/ramp_u8_storage.bogasm`
- `artifacts/ramp_u8_storage.bogbin`
- `artifacts/ramp_u8_storage_receipt.json`

Verification:

    python3 -m unittest discover -s tests -p "test_*.py" -q
    python3 -m bogvm assemble examples/ramp_u8_storage.bogasm artifacts/ramp_u8_storage.bogbin
    python3 -m bogvm run artifacts/ramp_u8_storage.bogbin --receipt artifacts/ramp_u8_storage_receipt.json

Boundary:

- Integer deterministic basis only.
- No floating point.
- No Fourier basis yet.
- No compression victory claim.
- No `.bog` container compiler yet.
- No laptop port yet.

## v0.4.0: Triangle Integer Wave Basis

v0.4.0 adds the first periodic deterministic integer wave basis.

Proof:

- `DECLARE_BASIS triangle_u8` declares a periodic integer oscillator basis.
- `LOAD_COEFFICIENTS` stores start byte and length.
- `SYNTHESIZE` reconstructs bytes using a fixed integer triangle wave:
  `offsets = 0, 32, 64, 96, 128, 96, 64, 32`
  `byte[i] = (start + offsets[i mod 8]) mod 256`
- `VERIFY_HASH` gates the reconstructed byte field.
- `ACCEPT_DATA` accepts only after hash verification.
- Bad hash paths emit blocked receipts.

Artifacts:

- `examples/triangle_u8_storage.bogasm`
- `examples/triangle_u8_bad_hash.bogasm`
- `artifacts/triangle_u8_storage.bogbin`
- `artifacts/triangle_u8_storage_receipt.json`
- `artifacts/triangle_u8_bad_hash.bogbin`
- `artifacts/triangle_u8_bad_hash_receipt.json`

Verification:

    python3 -m unittest discover -s tests -p "test_*.py" -q
    python3 -m bogvm assemble examples/triangle_u8_storage.bogasm artifacts/triangle_u8_storage.bogbin
    python3 -m bogvm run artifacts/triangle_u8_storage.bogbin --receipt artifacts/triangle_u8_storage_receipt.json
    python3 -m bogvm assemble examples/triangle_u8_bad_hash.bogasm artifacts/triangle_u8_bad_hash.bogbin
    python3 -m bogvm run artifacts/triangle_u8_bad_hash.bogbin --receipt artifacts/triangle_u8_bad_hash_receipt.json || echo "triangle bad hash correctly blocked"

Boundary:

- Toy-scale integer oscillator only.
- No floating point.
- No sine/cosine lookup table yet.
- No Fourier basis yet.
- No compression victory claim.
- No `.bog` container compiler yet.
- No laptop port yet.

## v0.5.0: Fixed Integer Sine Lookup Basis

v0.5.0 adds the first sine-like deterministic lookup-table basis.

Proof:

- `DECLARE_BASIS sine8_u8` declares a fixed integer sine-like oscillator.
- `LOAD_COEFFICIENTS` stores start byte and length.
- `SYNTHESIZE` reconstructs bytes using a fixed 8-step integer sine lookup table:
  `offsets = 0, 90, 127, 90, 0, -90, -127, -90`
  `byte[i] = (start + offsets[i mod 8]) mod 256`
- `VERIFY_HASH` gates the reconstructed byte field.
- `ACCEPT_DATA` accepts only after hash verification.
- Bad hash paths emit blocked receipts.

Artifacts:

- `examples/sine8_u8_storage.bogasm`
- `examples/sine8_u8_bad_hash.bogasm`
- `artifacts/sine8_u8_storage.bogbin`
- `artifacts/sine8_u8_storage_receipt.json`
- `artifacts/sine8_u8_bad_hash.bogbin`
- `artifacts/sine8_u8_bad_hash_receipt.json`

Verification:

    python3 -m unittest discover -s tests -p "test_*.py" -q
    python3 -m bogvm assemble examples/sine8_u8_storage.bogasm artifacts/sine8_u8_storage.bogbin
    python3 -m bogvm run artifacts/sine8_u8_storage.bogbin --receipt artifacts/sine8_u8_storage_receipt.json
    python3 -m bogvm assemble examples/sine8_u8_bad_hash.bogasm artifacts/sine8_u8_bad_hash.bogbin
    python3 -m bogvm run artifacts/sine8_u8_bad_hash.bogbin --receipt artifacts/sine8_u8_bad_hash_receipt.json || echo "sine8 bad hash correctly blocked"

Boundary:

- Fixed integer lookup table only.
- No floating point.
- No runtime sine/cosine.
- No FFT yet.
- No Fourier basis yet.
- No compression victory claim.
- No `.bog` container compiler yet.
- No laptop port yet.

## v0.6.0: Residual Patching for Exact Reconstruction

v0.6.0 adds deterministic residual patching.

Proof:

- A generator can synthesize a base byte field.
- `STORE_RESIDUAL` stores deterministic byte corrections.
- `APPLY_RESIDUAL` applies corrections to the generated byte field.
- `VERIFY_HASH` gates the exact reconstructed bytes.
- `ACCEPT_DATA` accepts only after hash verification.
- Bad hash paths emit blocked receipts.

Artifacts:

- `examples/residual_patch_storage.bogasm`
- `examples/residual_patch_bad_hash.bogasm`
- `artifacts/residual_patch_storage.bogbin`
- `artifacts/residual_patch_storage_receipt.json`
- `artifacts/residual_patch_bad_hash.bogbin`
- `artifacts/residual_patch_bad_hash_receipt.json`

Verification:

    python3 -m unittest discover -s tests -p "test_*.py" -q
    python3 -m bogvm assemble examples/residual_patch_storage.bogasm artifacts/residual_patch_storage.bogbin
    python3 -m bogvm run artifacts/residual_patch_storage.bogbin --receipt artifacts/residual_patch_storage_receipt.json
    python3 -m bogvm assemble examples/residual_patch_bad_hash.bogasm artifacts/residual_patch_bad_hash.bogbin
    python3 -m bogvm run artifacts/residual_patch_bad_hash.bogbin --receipt artifacts/residual_patch_bad_hash_receipt.json || echo "residual bad hash correctly blocked"

Boundary:

- Deterministic byte residuals only.
- No automatic residual optimization yet.
- No compression victory claim.
- No Fourier basis yet.
- No `.bog` container compiler yet.
- No laptop port yet.
