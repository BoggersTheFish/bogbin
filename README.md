# BOGBIN v17.0.0

BOGBIN is a verified storage and portable compute substrate for BogOS HyperGenesis.

BOGBIN still centers on one rule: bytes are accepted only after deterministic reconstruction and SHA-256 verification. v10 adds BogOS HyperGenesis: portable third-party proof bundles, deterministic capability-only BogCell apps, a signed self-build loop, verified time-travel state, and verifier-controlled AI proposals.

The post-v10 verifier-first expansion carries the same rule downward, outward, and upward: QEMU device events enter as claims, mesh nodes exchange signed claims, and swarm candidates remain proposals until a deterministic verifier admits one.

**v17 adds the first native BOGVM execution path:** the BogKernel boots in QEMU, executes a minimal embedded NOOP + HALT program using a native Rust executor, and emits verifier-checkable serial receipt markers.

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

## Quickstart: Verify the v17 Proofs

The shortest path to verify the v17.0.0 milestone locally:

```bash
# 1. Run the native BOGVM execution proof (requires cargo, qemu-system-i386, and readelf)
python3 scripts/evaluate_bogkernel_vm_exec.py

# 2. Run the native BogKernel boot proof
python3 scripts/evaluate_bogkernel_boot.py

# 3. Run the vertical v15 expansion proof
python3 scripts/evaluate_verifier_first_vertical.py

# 4. Run the full unit test suite
python3 -m unittest discover -v
```

For detailed technical specs, see:
- [docs/v17_native_bogvm_minimal_exec.md](docs/v17_native_bogvm_minimal_exec.md)
- [docs/v16_bootable_bogkernel.md](docs/v16_bootable_bogkernel.md)
- [docs/bogvm_bytecode_contract.md](docs/bogvm_bytecode_contract.md)

## Releases Implemented

- **v17.0.0: Native Minimal BOGVM Execution.** Native Rust BOGVM executor in BogKernel with NOOP/HALT support and serial execution receipts.
- **v16.0.0: Bootable BogKernel QEMU Spike.** Native i686/ELF32 Multiboot1 kernel with UART serial receipt markers and automated ELF artifact audit.
- post-v10 reference track: BogMesh v11, BogPilot Swarm v12, BogBoot v13, BogIRQ v14, signed v15 vertical demo.
- v10.0.0: BogOS HyperGenesis: Portable Self-Verifying Computer. BogNet proof bundles, BogCell, BogBuild, state-history proofs, and BogPilot.
- v9.0.0: BogOS Genesis: Verified Session OS. Trusted session boot, signed local registry, `bog.lock`, chained proof ledger, copy-on-write state, rollback, Genesis shell, and full-session replay.
- v8.0.0: BogK Capability Runtime. Bog-native apps use a brokered ABI for pre-access capability authorization, syscall receipt graphs, and deterministic replay.
- v7.0.0: BogK user-space kernel contract for verified workspace operations, schemas, trusted signatures, dependencies, and a signed-dependency proof demo.
- v6.0.0: Verified app runtime policy. `bog app run <app>` now requires a policy manifest with app name, entrypoint, allowed files, expected hashes, permissions, environment, read/write policy, and receipt path. Runtime writes are checked after execution, package files must remain unchanged, and receipts explain policy failures.
- v5.0.0: Verified app/package demo. Packages can declare app entrypoints in `bog_app.json`; `bog app run <app>` verifies the installed package before execution.
- v4.5.0: Public demo pack. One-command proof loop: archive, restore, mount, read, install, verify, run, corrupt, reject, and report.
- v4.1.0: BogOS Lite UX hardening. `doctor`, verbose status, latest receipts, corruption tests, and workspace tree output.
- v4.0.0: BogOS Lite. User-level Bog-managed workspace with archives, mounts, and a local package store.
- v3.0.0: Bog Package Store. Local verified recipe bundles.
- v2.5.0: BogFS Prototype. Read-only filesystem-style layer over BOG directory archives.
- v2.0.0: Directory Roundtrip. Verified folder milestone with tree-hash verification.
- v1.9.0: Real Corpus Smoke. Deterministic real-file roundtrip on text, JSON, binary, PNG, and WAV.
- v1.8.0: Transform Tournament Upgrade. Cost-aware transform selection scoring container size, residual count, and complexity.
- v1.7.0: BOGPK Hardening. Defensive binary parser with strict magic, varint, and hash checks.
- v1.6.0: Binary-Packed BOGPK Container. It enum-packs transform and basis IDs, derives offsets implicitly, delta-codes residual offsets, supports bitmask residuals, supports zero-residual runs, and preserves exact 5/5 real-file roundtrip.

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
- BogBoot (v15) and BogIRQ model QEMU/device-boundary behavior in user space.
- **v16-v17 BogKernel** is a narrow native proof: QEMU-only, not a full OS, not physical hardware support, not a BIOS, not a real driver stack, and no interrupt admission yet.
- **v17 Native VM** only supports `NOOP` and `HALT`. No data verification (`VERIFY_HASH`) or graph state logic is implemented natively yet.
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
```
