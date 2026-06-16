# BOGBIN v39.0.0

BOGBIN is a verified storage and portable compute substrate for BogOS HyperGenesis.

BOGBIN still centers on one rule: bytes are accepted only after deterministic reconstruction and SHA-256 verification. v10 adds BogOS HyperGenesis: portable third-party proof bundles, deterministic capability-only BogCell apps, a signed self-build loop, verified time-travel state, and verifier-controlled AI proposals.

The post-v10 verifier-first expansion carries the same rule downward, outward, and upward: QEMU device events enter as claims, mesh nodes exchange signed claims, and swarm candidates remain proposals until a deterministic verifier admits one.

**v30 adds timer-preemptive verified scheduling:** Ring 3 processes are preempted when their quantum expires, saving the interrupted Ring 3 context and resuming other processes in round-robin fashion while preserving cooperative yields.

**v31 adds verified paging and scoped process isolation:** QEMU Ring 3 processes use distinct CR3 values, supervisor-only kernel mappings, private user code/data/stack mappings, and read-only executable pages. Kernel access, cross-process write, and code-write malicious apps fault and become blocked while valid processes continue preempting.

**v32 adds dynamic verified process loading:** structured `.bogapp` files are discovered from BogFS/initrd, manifest and code hashes are checked before PID allocation, and accepted apps enter the v31 isolated Ring 3 scheduler path.

**v32.1 audited that loader contract:** canonical bounds, offset, padding, capability, and trailing-byte failures are rejected before PID allocation, with stricter load/admission receipts.

**v33 adds Syscall ABI v2:** dynamically loaded isolated Ring 3 apps use bounded, receipt-visible syscalls. The kernel validates active-process user mappings before v2 copies, rejects unsafe pointers and unsupported calls, and preserves loading, isolation, and preemption.

**v33.1 audits Syscall ABI v2:** edge-length and page-boundary cases, invalid hash pointers, invalid syscall numbers, and dynamic legacy-call bypass attempts are receipt-proven without changing the v33.0.0 release claim.

**v34 adds verified IPC:** isolated dynamic Ring 3 processes exchange bounded messages through kernel-owned point-to-point queues. Sends and receives validate private mappings, hash payloads, enforce queue limits, preserve queued messages after rejected receives, and use no shared memory.

**v35 adds writable verified BogFS:** isolated dynamic Ring 3 apps use bounded file write/read/stat syscalls backed by a tiny kernel-owned in-memory table. Writes commit only after caller, pointer, path, permission, capacity, and receipt-hash checks succeed.

**v35.1 audits writable BogFS hardening:** exact length boundaries, repeated version transitions, failed-write read/stat preservation, alias and protected-path rejection, full-table behavior, cross-process pointers, and IPC queue preservation are receipt-proven without changing the v35.0.0 release claim.

**v36 adds a verified block device model:** BogKernel performs bounded
single-sector reads and writes against one QEMU legacy IDE/ATA PIO raw disk.
Sector SHA-256, protected-LBA policy, expected preimages, flush, and read-back
verification gate trusted block-state mutation. This is not a filesystem and
does not make BogFS persistent.

**v37 adds persistent verified BogFS:** a separate QEMU boot proof mounts,
verifies, updates, and remounts one fixed file on the v36 ATA PIO disk. An
alternate-root commit is admitted only after data, manifest, and superblock
write/read-back/hash checks. This is clean-reboot evidence for a tiny
non-POSIX filesystem, not production storage.

**v38 adds file lifecycle evidence:** a separate QEMU boot proof extends the
persistent format to eight deterministic records and flat `/data` create,
write, delete, list, stat, and read behavior. Each accepted mutation commits a
new verified alternate root; rejected operations retain the trusted root.

**v39 adds persistent disk-loaded apps:** BogKernel verifies a `.bogapp` v2
file from an immutable persistent BogFS root, allocates a PID only after file,
manifest, code, ABI, entrypoint, and capability checks pass, then maps and
executes the app through the isolated Ring 3 process path.

## Forward Roadmap

The v36-v40 ladder moves the current QEMU-only proof toward a tiny research OS
prototype: verified block sectors, persistent verified BogFS,
directories and file lifecycle, disk-loaded verified apps, and (as of the
locked v40 plan) the Genesis Workspace Root model.

**v40 Genesis Workspace Root:** hash-rooted persistent workspace model, materialized WorkspaceState, deterministic CreateDirectory/CreateFile/EditFile transitions, Python oracle golden vectors, and receipt-chain invariant tests. Kernel/BogFS persistence integration is the next phase and is not completed yet.

The previous "two-boot persistent shell demo" framing is deferred to v41+.
v40 does not include package manager, full .bogapp evolution, self-hosting,
rich TS graph engine, or shell comfort layer.

See [docs/roadmap_v36_to_v40_tiny_os.md](docs/roadmap_v36_to_v40_tiny_os.md) and the canonical plan [docs/v40_genesis_workspace_root.md](docs/v40_genesis_workspace_root.md).

## What Works

- `.bogasm` assembles to `.bogbin`.
- BOGVM executes deterministic fixed-point graph-state programs.
- `VERIFY_HASH` + `ACCEPT_DATA` gates data acceptance.
- Residual plans reconstruct exact bytes from deterministic bases plus patches.
- `.bogpk` stores compact binary-packed chunk recipes.
- BogFS can list, stat, and read files from verified archive recipes.
- Bog package store manages signed Ed25519 bundles and dependency-pinned installs.
- BogOS Lite workspaces keep archives, mounts, and receipts under `.bogos/`.
- `bog app run` enforces verified runtime policies and brokered capability-only I/O.
- BogOS Genesis provides a trusted session ledger with copy-on-write state and rollback.
- **v15 Verifier-First Expansion:** Integrates BogBoot (QEMU boot receipts), BogIRQ (device claims), BogMesh (claim resolution), and BogPilot Swarm (candidate tournaments) into a single vertical proof.
- **v16 Bootable BogKernel Spike:** Native i686/ELF32 Multiboot1 kernel boots in QEMU and emits deterministic serial markers verified by a host-side evaluator.
- **v17 Native Minimal BOGVM:** Minimal native Rust executor in BogKernel decodes and executes embedded bytecode (NOOP/HALT) and emits execution receipts.
- **v18 Native Verify/Accept:** Native Rust BOGVM executor in BogKernel supports `VERIFY_HASH`, `ACCEPT_DATA`, and `REJECT_DATA` with freestanding SHA-256 computation and dual-run verification.
- **v19 Native Verified App Bundle:** Native Rust BOGVM executor and kernel verification path in BogKernel supports static/embedded app bundles with native verification, gated execution, and serial receipt markers.
- **v27 Verified Process Model:** Explicit process records and deterministic CREATED, VERIFIED, RUNNING, EXITED, BLOCKED, REJECTED, and PANICKED transitions before scheduling or multitasking.
- **v28 Cooperative Verified Scheduler:** Explicit READY, SCHEDULED, and YIELDED transitions, FIFO round-robin selection, `sys_yield`, scheduler shell commands, and deterministic scheduler receipts.
- **v29 Saved User Contexts:** Per-process execution slots and saved x86 user registers allow cooperatively yielded Ring 3 apps to resume rather than restart.
- **v30 Timer-Preemptive Verified Scheduler:** Extends `ProcessState` with `PREEMPTED`, tracks quantum scheduler stats, preempts Ring 3 user processes via IRQ0 timer checks, outputs deterministic `BOGOS_PREEMPT` receipts, and extends scheduler receipts with selection reasons.
- **v31 Verified Paging:** Protects kernel mappings, private process mappings, and executable code pages from the tested Ring 3 malicious accesses while preserving v30 preemption.
- **v32 Dynamic Verified Loader:** Discovers structured apps from BogFS/initrd, rejects malformed or corrupted containers before execution, and admits verified code into private v31 address spaces.
- **v33 Syscall ABI v2:** Provides bounded exit, yield, console output, PID, process-info, hash-verification, and claim calls for dynamically loaded isolated Ring 3 apps.
- **v34 Verified IPC:** Provides bounded kernel-mediated point-to-point channels and receipt-visible send, receive, poll, rejection, and queue-preservation evidence.
- **v35 Writable Verified BogFS:** Provides bounded kernel-owned in-memory files, verified write/read/stat syscalls, hash-visible version transitions, and rejection non-mutation proofs.
- **v36 Verified Block Device Model:** Provides bounded QEMU ATA PIO single-sector reads/writes, sector SHA-256 verification, protected-LBA policy, read-back verification, and rejection non-mutation evidence without adding a filesystem.
- **v37 Persistent Verified BogFS:** Provides one fixed block-backed file, verified mount/root selection, alternate-root commits, corruption fallback/rejection, and clean two-boot persistence evidence while preserving v35 in-memory BogFS syscalls.
- **v38 File Lifecycle:** Provides bounded flat `/data` create, write, delete, list, stat, and read evidence with tombstones, protected prefixes, alternate-root commits, and two-boot persistence.
- **v39 Persistent Disk-Loaded Apps:** Provides immutable `/apps` fixtures, `.bogapp` v2 verification, post-verification PID allocation, private CR3/code mapping, scheduler admission, Ring 3 execution, exit evidence, and two-boot persistence.

**v40 Genesis Workspace Root (Phase D complete):** hash-rooted persistent workspace model, materialized WorkspaceState, deterministic CreateDirectory/CreateFile/EditFile transitions, Python oracle golden vectors, and receipt-chain invariant tests. Phase D integrates the GenesisRoot as a well-known object inside the existing v37/v38 persistent BogFS manifest with boot/mount validation and receipt-chain survival (QEMU image proof). Kernel remains narrow verifier/root-transition spine (not a file manager). See [docs/v40_genesis_workspace_root.md](docs/v40_genesis_workspace_root.md). The older persistent shell demo framing is deferred to v41+.


## Quickstart: Verify the v39.0.0 milestone locally

The shortest path to verify the v39.0.0 milestone locally:

```bash
python3 -m unittest discover -v
python3 scripts/evaluate_v26_ts_lang.py
python3 scripts/evaluate_v26_negative.py
python3 scripts/evaluate_v27_process_model.py
python3 scripts/evaluate_v28_scheduler.py
python3 scripts/evaluate_v29_context_switch.py
python3 scripts/evaluate_v30_preemptive_scheduler.py
python3 scripts/evaluate_v31_verified_paging.py
python3 scripts/evaluate_v32_dynamic_loader.py
python3 scripts/evaluate_v33_syscall_abi.py
python3 scripts/evaluate_v34_ipc.py
python3 scripts/evaluate_v35_writable_bogfs.py
python3 scripts/evaluate_v35_1_writable_bogfs_audit.py
python3 scripts/evaluate_v36_block_device.py
python3 scripts/evaluate_v37_persistent_bogfs.py
python3 scripts/evaluate_v38_file_lifecycle.py
python3 scripts/evaluate_v39_disk_loaded_apps.py
cd kernel && cargo test -p bogk-core
```


For detailed technical specs, see:
- [docs/v30_preemptive_scheduler.md](docs/v30_preemptive_scheduler.md)
- [docs/v31_verified_paging.md](docs/v31_verified_paging.md)
- [docs/v32_dynamic_verified_loader.md](docs/v32_dynamic_verified_loader.md)
- [docs/v33_syscall_abi_v2.md](docs/v33_syscall_abi_v2.md)
- [docs/v34_verified_ipc.md](docs/v34_verified_ipc.md)
- [docs/v35_writable_verified_bogfs.md](docs/v35_writable_verified_bogfs.md)
- [docs/v35_1_writable_bogfs_hardening_audit.md](docs/v35_1_writable_bogfs_hardening_audit.md)
- [docs/v36_block_device_plan.md](docs/v36_block_device_plan.md)
- [docs/v37_persistent_bogfs_plan.md](docs/v37_persistent_bogfs_plan.md)
- [docs/v38_file_lifecycle_plan.md](docs/v38_file_lifecycle_plan.md)
- [docs/v39_disk_loaded_apps_plan.md](docs/v39_disk_loaded_apps_plan.md)
- [docs/v40_genesis_workspace_root.md](docs/v40_genesis_workspace_root.md)
- [docs/roadmap_v36_to_v40_tiny_os.md](docs/roadmap_v36_to_v40_tiny_os.md)
- [docs/v29_context_switching.md](docs/v29_context_switching.md)
- [docs/v28_cooperative_scheduler.md](docs/v28_cooperative_scheduler.md)
- [docs/v27_process_model.md](docs/v27_process_model.md)
- [docs/v19_native_verified_app_bundle.md](docs/v19_native_verified_app_bundle.md)
- [docs/v18_native_verify_accept.md](docs/v18_native_verify_accept.md)
- [docs/v17_native_bogvm_minimal_exec.md](docs/v17_native_bogvm_minimal_exec.md)
- [docs/v16_bootable_bogkernel.md](docs/v16_bootable_bogkernel.md)
- [docs/v15_verifier_first_vertical.md](docs/v15_verifier_first_vertical.md)
- [docs/bogvm_bytecode_contract.md](docs/bogvm_bytecode_contract.md)

## Run the visible BogOS v20 demo

See [docs/v20_visible_demo_guide.md](docs/v20_visible_demo_guide.md) for the visible QEMU demo command, expected screen, and serial proof check.

## Releases Implemented

- v1.6: BOGPK clean binary-packed container. It enum-packs transform and basis IDs, derives offsets implicitly, delta-codes residual offsets, supports bitmask residuals, supports zero-residual runs, and preserves exact 5/5 real-file roundtrip.
- v1.7: BOGPK hardening. The parser rejects bad magic, non-minimal or unterminated varints, reserved flags, reserved transform/basis IDs, bad residual offsets, invalid bitmask offsets, impossible chunk counts, impossible residual totals, bad transform parameters, trailing bytes, and bad whole-payload hashes.
- v1.8: Transform tournament upgrade. Transform plans are scored by estimated packed container size, residual count, transform cost, basis cost, and decode cost. Bog chooses the cheapest verified reconstruction plan, not just the lowest residual density.
- v1.9: Real corpus smoke. The report harness roundtrips deterministic text, JSON, binary, PNG, and WAV fixtures through `.bogpk`.
- v2.0: Directory roundtrip. `archive` and `restore` commands store mixed folders as verified BOG archives and recover matching file/tree hashes.
- v2.5: BogFS prototype. `bogvm fs ls|stat|cat` exposes read-only file access backed by archive recipes.
- v3.0: Bog package store. `bogvm store package` and `bogvm store install` manage verified recipe bundles through receipts and an install index.
- v4.0: BogOS Lite. `bog init`, `bog archive`, `bog restore`, `bog fs mount/read`, `bog store install/verify`, `bog status`, and `bog receipt` let a user live inside a Bog-managed workspace. Corruption is rejected with a receipt explaining why.
- v4.1: BogOS Lite UX hardening. `bog demo`, `bog doctor`, `bog status --verbose`, `bog receipt latest`, `bog corrupt-test`, and `bog workspace tree` expose what Bog has, what it verified, what failed, and why.
- v4.5: Public demo pack. `bog demo pack` creates a fixture package, archives, restores, mounts/reads, installs, verifies, runs, corrupts, rejects, and emits a final report.
- v5.0: Verified app/package demo. Packages can declare app entrypoints in `bog_app.json`; `bog app run <app>` verifies the installed package before execution.
- v6.0: Verified app runtime policy. `bog app run <app>` now requires a policy manifest with app name, entrypoint, allowed files, expected hashes, permissions, environment, read/write policy, and receipt path. Runtime writes are checked after execution, package files must remain unchanged, and receipts explain policy failures.
- v7.0.0: BogK user-space kernel contract for verified workspace operations, schemas, trusted signatures, dependencies, and a signed-dependency proof demo.
- v8.0.0: BogK Capability Runtime. Bog-native apps use a brokered ABI for pre-access capability authorization, syscall receipt graphs, and deterministic replay.
- v9.0.0: BogOS Genesis: Verified Session OS. Trusted session boot, signed local registry, `bog.lock`, chained proof ledger, copy-on-write state, rollback, Genesis shell, and full-session replay.
- v10.0.0: BogOS HyperGenesis: Portable Self-Verifying Computer. BogNet proof bundles, BogCell, BogBuild, state-history proofs, and BogPilot.
- post-v10 reference track: BogMesh v11, BogPilot Swarm v12, BogBoot v13, BogIRQ v14, signed v15 vertical demo.
- **v17.0.0: Native Minimal BOGVM Execution.** Native Rust BOGVM executor in BogKernel with NOOP/HALT support and serial execution receipts.
- **v18.0.0: Native VERIFY_HASH and ACCEPT_DATA.** Implements native BOGVM hash verification, data acceptance, and data rejection on the bare metal with freestanding SHA-256 and serial receipts.
- **v19.0.0: Native Verified Embedded App Bundle.** Compiles static app bundles containing bytecode, manifest metadata, and expected SHA-256 hashes into the kernel image. Computes native hashes, rejects invalid bundles, executes accepted bundles, and emits deterministic serial receipt markers.
- **v20.0.0: BogOS QEMU Demo System.** First visible OS-like demo in QEMU with VGA Text UI status displays, shell command parser, PS/2 keyboard driver, auto-demo fallback, static pseudo-filesystem, kernel-controlled app output, security block screens, and serial receipt logs.
- **v27.0.0: Verified Process Model.** Adds monotonic process IDs, verified process transitions, process receipts, and `/system/processes` without adding scheduling or multitasking.
- **v28.0.0: Cooperative Verified Scheduler.** Adds deterministic explicit-step scheduling, cooperative yield, scheduler receipts, and `/system/scheduler` without preemption or saved CPU contexts.
- **v29.0.0: Saved User Contexts.** Saves and restores cooperative Ring 3 CPU state across yield using bounded per-process code/data and stack slots.
- **v30.0.0: Timer-Preemptive Verified Scheduler.** Preempts Ring 3 user processes on quantum expiration using IRQ0 interrupts, saves contexts, and logs deterministic preempt receipts.


## Core Commands

Workspace & Substrate:

```bash
bog init workspace
bog vertical demo
python3 scripts/evaluate_bogkernel_vm_exec.py
```

(See the full command list in prior release tags or `docs/`.)

## Current Boundaries

- BOGPK is a reconstruction blueprint, not proof authority.
- VM hash-gated acceptance remains proof authority for compiled `.bogbin` runs.
- Directory archives and package installs verify reconstructed bytes with SHA-256 and tree hashes.
- BogOS Lite is a user-space workspace manager, not a kernel, BIOS, driver stack, or OS boot target.
- The real-file report crosses the aggregate `.bogpk` compression threshold, but not every individual fixture is smaller than input.
- BogOS Lite is a user-space workspace manager.
- BogBoot (v15) and BogIRQ model QEMU/device-boundary behavior in user space.
- **v16-v39 BogKernel** is a narrow native proof: QEMU-only, not a full production OS, with timer-preemptive scheduling, scoped process isolation, a minimal dynamic verified loader, bounded syscall ABI v2, bounded kernel-mediated IPC, verified block storage, persistent file proofs, flat `/data` lifecycle, and an immutable persistent `.bogapp` v2 Ring 3 loading proof. It has no demand paging, swapping, ASLR, full ELF loader, shared memory, nested mutable directories, rename, production app support, or BIOS/physical hardware support.

- BogMesh is local-first signed claim transport and deterministic conflict policy; it is not Byzantine consensus or a public production network.


## Verification

```bash
python3 -m unittest discover -v
python3 scripts/evaluate_bogos_qemu_demo_system.py
python3 scripts/evaluate_real_file_roundtrip.py
python3 scripts/evaluate_bogos_lite_demo.py
python3 scripts/evaluate_bog_kernel_lite.py
python3 scripts/evaluate_genesis.py
python3 scripts/evaluate_hypergenesis.py
python3 scripts/evaluate_verifier_first_vertical.py
python3 scripts/evaluate_bogkernel_boot.py
python3 scripts/evaluate_bogkernel_vm_exec.py
python3 scripts/evaluate_bogkernel_verify_accept.py
python3 scripts/evaluate_bogkernel_app_bundle.py
python3 scripts/evaluate_v26_ts_lang.py
python3 scripts/evaluate_v26_negative.py
python3 scripts/evaluate_v27_process_model.py
python3 scripts/evaluate_v28_scheduler.py
python3 scripts/evaluate_v29_context_switch.py
python3 scripts/evaluate_v30_preemptive_scheduler.py
python3 scripts/evaluate_v31_verified_paging.py
python3 scripts/evaluate_v32_dynamic_loader.py
python3 scripts/evaluate_v33_syscall_abi.py
python3 scripts/evaluate_v34_ipc.py
python3 scripts/evaluate_v35_writable_bogfs.py
python3 scripts/evaluate_v35_1_writable_bogfs_audit.py
python3 scripts/evaluate_v36_block_device.py
python3 scripts/evaluate_v37_persistent_bogfs.py
python3 scripts/evaluate_v38_file_lifecycle.py
python3 scripts/evaluate_v39_disk_loaded_apps.py
cd kernel && cargo test -p bogk-core
```
