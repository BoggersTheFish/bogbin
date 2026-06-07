# BOGBIN v7.0

BOGBIN is a verified storage and workspace substrate for BogOS Lite.

BOGBIN still centers on one rule: bytes are accepted only after deterministic reconstruction and SHA-256 verification. The current codebase supports single-file `.bog` manifests, compact `.bogpk` binary recipes, mixed directory archives, read-only BogFS-style access to recipes, a verified package store, BogOS Lite workspace UX, verified app runtime policy, and BogK: a deterministic user-space kernel contract.

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
- Bog package store can package a directory, install the verified recipe bundle, and record install receipts.
- BogOS Lite workspaces keep archives, mounts, package-store state, and receipts under `.bogos/`.
- `bog doctor`, `bog status --verbose`, `bog receipt latest`, and `bog workspace tree` make workspace state inspectable.
- `bog corrupt-test` proves corruption rejection and records why.
- `bog demo pack` creates a public proof loop without requiring prior fixtures.
- `bog app run demo-app` verifies an installed package, enforces a v6 app manifest, runs with a controlled environment, checks runtime writes against policy, and records why a run was accepted or blocked.
- `bog kernel boot|status|run|syscall` provides a kernel-shaped workspace authority for deterministic process records, delegated verified app execution, mounted archive reads, policy-controlled appdata writes, syscall logs, and kernel receipts.

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
- v7.0: BogK user-space kernel contract. `bog kernel boot`, `bog kernel status`, `bog kernel run`, and `bog kernel syscall` add deterministic kernel state, process records, syscall receipts, mounted reads, and write-policy-controlled appdata writes while delegating proof authority to existing v6 and package verification paths.

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
bog kernel syscall read demo README.txt
bog kernel syscall write demo-app run.log "kernel write"
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

Real-file report:

```bash
python3 scripts/evaluate_real_file_roundtrip.py
python3 scripts/evaluate_bogos_lite_demo.py
python3 scripts/evaluate_bog_kernel_lite.py
```

## Current Boundaries

- BOGPK is a reconstruction blueprint, not proof authority.
- VM hash-gated acceptance remains proof authority for compiled `.bogbin` runs.
- Directory archives and package installs verify reconstructed bytes with SHA-256 and tree hashes.
- BogOS Lite is a user-space workspace, not a kernel, BIOS, driver stack, or OS boot target.
- The real-file report crosses the aggregate `.bogpk` compression threshold, but not every individual fixture is smaller than input.
- This is not a claim that Bog beats ZIP, PNG, WAV, or existing package managers.
- BogFS is a read-only prototype API/CLI, not a kernel mount implementation.
- The package store installs verified recipe bundles locally; it does not yet resolve dependencies or fetch remote registries.
- App execution is local subprocess execution after package verification and runtime policy checks. Bog controls the subprocess environment, verifies declared file hashes, isolates normal writes into `.bogos/appdata/<app>/`, and rejects undeclared runtime writes. It does not syscall-trace reads, provide kernel sandboxing, remote trust, dependency solving, or signature verification.
- BogK is a deterministic workspace-local kernel contract, not a real OS kernel, bootloader, bare-metal runtime, or syscall-tracing sandbox. Package verification and v6 runtime policy remain proof authority.

## Verification

```bash
python3 -m unittest discover -v
python3 scripts/evaluate_real_file_roundtrip.py
python3 scripts/evaluate_bogos_lite_demo.py
python3 scripts/evaluate_bog_kernel_lite.py
```
