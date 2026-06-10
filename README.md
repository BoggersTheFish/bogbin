# BOGBIN v19.0.0

BOGBIN is a verified storage and portable compute substrate for BogOS HyperGenesis.

BOGBIN still centers on one rule: bytes are accepted only after deterministic reconstruction and SHA-256 verification. v10 adds BogOS HyperGenesis: portable third-party proof bundles, deterministic capability-only BogCell apps, a signed self-build loop, verified time-travel state, and verifier-controlled AI proposals.

The post-v10 verifier-first expansion carries the same rule downward, outward, and upward: QEMU device events enter as claims, mesh nodes exchange signed claims, and swarm candidates remain proposals until a deterministic verifier admits one.

**v19 adds native verified embedded app bundle verification and execution:** the BogKernel boots in QEMU, finds a static/embedded app bundle (bytecode, name, version, manifest, and expected hash), verifies its bytecode hash on the bare metal, accepts or rejects it, executes it on acceptance, and emits deterministic serial receipt markers.


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


## Quickstart: Verify the v17 Proofs

The shortest path to verify the v19.0.0 milestone locally:

```bash
# 1. Run the native verified embedded app bundle proof
python3 scripts/evaluate_bogkernel_app_bundle.py

# 2. Run the native BOGVM verify/accept execution proof (requires cargo, qemu-system-i386, and readelf)
python3 scripts/evaluate_bogkernel_verify_accept.py

# 3. Run the native BOGVM minimal execution proof
python3 scripts/evaluate_bogkernel_vm_exec.py

# 4. Run the native BogKernel boot proof
python3 scripts/evaluate_bogkernel_boot.py

# 5. Run the vertical v15 expansion proof
python3 scripts/evaluate_verifier_first_vertical.py

# 6. Run the full unit test suite
python3 -m unittest discover -v
```


For detailed technical specs, see:
- [docs/v19_native_verified_app_bundle.md](docs/v19_native_verified_app_bundle.md)
- [docs/v18_native_verify_accept.md](docs/v18_native_verify_accept.md)
- [docs/v17_native_bogvm_minimal_exec.md](docs/v17_native_bogvm_minimal_exec.md)
- [docs/v16_bootable_bogkernel.md](docs/v16_bootable_bogkernel.md)
- [docs/v15_verifier_first_vertical.md](docs/v15_verifier_first_vertical.md)
- [docs/bogvm_bytecode_contract.md](docs/bogvm_bytecode_contract.md)


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
- **v16-v19 BogKernel** is a narrow native proof: QEMU-only, not a full OS, no scheduler, no filesystem, and no interrupt/BIOS support yet. Data is strictly not accepted until verified.

- BogMesh is local-first signed claim transport and deterministic conflict policy; it is not Byzantine consensus or a public production network.


## Verification

```bash
python3 -m unittest discover -v
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
```

