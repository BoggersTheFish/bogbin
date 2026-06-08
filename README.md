# BOGBIN v10.0.0

BOGBIN is a verified storage and portable compute substrate for BogOS HyperGenesis.

BOGBIN still centers on one rule: bytes are accepted only after deterministic reconstruction and SHA-256 verification. v10 adds BogOS HyperGenesis: portable third-party proof bundles, deterministic capability-only BogCell apps, a signed self-build loop, verified time-travel state, and verifier-controlled AI proposals.

## What Works

- `.bogasm` assembles to `.bogbin`.
- BOGVM executes deterministic fixed-point graph-state programs.
- `VERIFY_HASH` + `ACCEPT_DATA` gates data acceptance.
- Residual plans reconstruct exact bytes from deterministic bases plus patches.
- `.bog` stores transparent JSON chunk recipes for audit/debug.
- `.bogpk` stores compact binary-packed chunk recipes.
- File roundtrip works as `input -> recipe -> VM verification -> recovered bytes`.
- Directory roundtrip works as `folder -> archive/store -> recovered folder`, with all file hashes and the tree hash checked.
- BogFS can list, stat, and read files from archive recipes without restoring the whole folder.
- Bog package store can sign a directory package with Ed25519, verify trusted signatures and dependencies, install the verified recipe bundle, and record install receipts.
- BogOS Lite workspaces keep archives, mounts, package-store state, and receipts under `.bogos/`.
- `bog doctor`, `bog status --verbose`, `bog receipt latest`, and `bog workspace tree` make workspace state inspectable.
- `bog corrupt-test` proves corruption rejection and records why.
- `bog demo pack` creates a public proof loop without requiring prior fixtures.
- `bog app run demo-app` verifies an installed package, enforces a v6 app manifest, runs with a controlled environment, checks runtime writes against policy, and records why a run was accepted or blocked.
- `bog kernel boot|status|run|syscall` provides a user-space kernel contract for verified workspace operations.
- `bog kernel run --brokered <app>` runs a Bog-native app against the `bog_runtime` capability ABI and emits a full syscall receipt graph.
- `bog kernel replay <receipt.json>` re-verifies package/tree/dependency/policy state, syscall order/evidence, brokered output files, and the final process proof hash.
- Draft 2020-12 JSON schemas validate app manifests, archive manifests, decoded BOGPK metadata, package receipts, common receipts, BogK receipts, and brokered process proofs.
- `bog genesis demo` boots a complete local mini environment, verifies a signed registry and lockfile, installs signed dependency-pinned apps, runs them through BogK, blocks forbidden access and tampered code, rolls state back, replays the session, and emits one final signed Genesis receipt.
- Genesis receipts form a signed append-only hash chain. Editing any prior receipt breaks ledger verification.
- Genesis BogFS state uses immutable content-addressed objects and copy-on-write tree manifests, so every accepted write has a recoverable prior root.
- `bog hypergenesis demo` proves the complete v10 portable self-verifying computer loop.
- `.bogproof` bundles carry public trust keys, signed ledger/registry/lock/package evidence, state roots/objects, and replay evidence for clean third-party verification.
- BogCell programs expose only `READ`, `WRITE`, `ENV`, `DEPENDENCY`, and `EXIT`; there is no subprocess, network, Python, or raw host-I/O instruction.
- BogBuild compiles a tiny `.bogsrc` language into deterministic BogCell bytecode and emits a signed source/compiler/bytecode/capability receipt.
- `bog ledger verify` verifies both the signed receipt chain and all historical state objects.
- `bog state diff|checkout|prove-file` exposes verified time-travel state.
- BogPilot proposes actions but receives no direct authority; every proposal is completed or blocked by Bog verification.

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

## Core Commands

BogOS Lite workspace:

```bash
bog init workspace
cd workspace
bog archive project/
bog restore project
bog fs mount project proj
bog fs read proj README.txt
bog store install project/ --name project --version 1.0.0
bog store verify project-1.0.0
bog status
bog receipt
bog doctor
bog status --verbose
bog receipt latest
bog workspace tree
bog corrupt-test project-1.0.0
bog demo pack
bog app run demo-app
bog kernel boot
bog kernel status
bog kernel run demo-app
bog kernel run --brokered capability-app
bog kernel replay .bogos/kernel/receipts/0002_run-brokered_capability-app.json
bog kernel syscall read demo README.txt
bog kernel syscall write demo-app run.log "kernel write"
bog genesis demo
bog boot
bog registry sync
bog install note-app-1.0.0
bog shell
bog rollback 12
bog replay-session .bogos/genesis/genesis_receipt.json
bog hypergenesis demo
bog build app.bogsrc --output build-output
bog package build-output --name built-app --version 1.0.0
bog install built-app-1.0.0
bog run-cell built-app
bog proof export receipt.json session.bogproof
bog proof verify session.bogproof
bog proof replay session.bogproof
bog ledger verify
bog state diff <root-a> <root-b>
bog state checkout <root>
bog state prove-file notes/today.txt
bog pilot "write a note and attempt forbidden access"
```

The same workspace CLI is available without the executable shim:

```bash
python3 -m bog init workspace
python3 -m bog --workspace workspace status
```

Single-file compact recipe:

```bash
python3 -m bogvm pack input.bin output.bogpk --auto-chunk --transform-tournament --receipt pack_receipt.json
python3 -m bogvm compile output.bogpk output.bogbin --bogasm output.bogasm
python3 -m bogvm run output.bogbin --receipt run_receipt.json
python3 -m bogvm unpack output.bogpk recovered.bin --receipt unpack_receipt.json
```

Directory archive:

```bash
python3 -m bogvm archive ./project ./project.bogarchive --receipt archive_receipt.json
python3 -m bogvm restore ./project.bogarchive ./project.recovered --receipt restore_receipt.json
```

BogFS read-only access:

```bash
python3 -m bogvm fs ls ./project.bogarchive
python3 -m bogvm fs stat ./project.bogarchive path/in/archive.txt
python3 -m bogvm fs cat ./project.bogarchive path/in/archive.txt
```

Package store:

```bash
python3 -m bogvm store init ./bog-store
python3 -m bogvm store package ./project ./bundle --name project --version 1.0.0 --receipt package_receipt.json
python3 -m bogvm store install ./bog-store ./bundle --receipt install_receipt.json
```

Signed low-level package flow:

```bash
python3 -m bogvm store keygen signing.key signing.pub
python3 -m bogvm store package ./project ./bundle --name project --version 1.0.0 --signing-key signing.key --receipt package_receipt.json
python3 -m bogvm store install ./bog-store ./bundle --trusted-key signing.pub --require-signature --receipt install_receipt.json
```

Real-file report:

```bash
python3 scripts/evaluate_real_file_roundtrip.py
python3 scripts/evaluate_bogos_lite_demo.py
python3 scripts/evaluate_bog_kernel_lite.py
python3 scripts/evaluate_signed_dependency_demo.py
python3 scripts/evaluate_bogk_capability_runtime.py
python3 scripts/evaluate_genesis.py
python3 scripts/evaluate_hypergenesis.py
```

## Current Boundaries

- BOGPK is a reconstruction blueprint, not proof authority.
- VM hash-gated acceptance remains proof authority for compiled `.bogbin` runs.
- Directory archives and package installs verify reconstructed bytes with SHA-256 and tree hashes.
- BogOS Lite is a user-space workspace, not a kernel, BIOS, driver stack, or OS boot target.
- The real-file report crosses the aggregate `.bogpk` compression threshold, but not every individual fixture is smaller than input.
- This is not a claim that Bog beats ZIP, PNG, WAV, or existing package managers.
- Archive-mounted BogFS remains read-only. Genesis adds a separate workspace-local copy-on-write BogFS state layer; neither is a kernel mount.
- The Genesis registry is signed and local. It does not fetch remote registries or solve version ranges; `bog.lock` pins exact package keys, hashes, dependencies, signatures, and trust keys.
- Brokered Bog-native apps use BogK as their official I/O path. Brokered reads/writes/env/dependencies are authorized before access and recorded as receipt nodes.
- Arbitrary native apps can still make direct host syscalls. Brokered mode is not a host-kernel sandbox and cannot prevent direct reads or all writes outside observable Bog paths. See `THREAT_MODEL.md`.
- BogCell closes that raw-I/O gap for BogCell programs by design, but it is intentionally a tiny deterministic VM rather than a general native runtime.
- BogPilot is a deterministic local proposal layer, not a claim of autonomous intelligence or trusted AI reasoning.

## Verification

```bash
python3 -m unittest discover -v
python3 scripts/evaluate_real_file_roundtrip.py
python3 scripts/evaluate_bogos_lite_demo.py
python3 scripts/evaluate_bog_kernel_lite.py
python3 scripts/evaluate_genesis.py
python3 scripts/evaluate_hypergenesis.py
```
