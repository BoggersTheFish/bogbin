# BogOS Lite

BogOS Lite is the user-space workspace milestone that now spans v4.0 through v8.0.0.

It is not a kernel, BIOS, bootloader, or driver stack. It is a way to live inside a Bog-managed workspace where archives, restores, BogFS reads, package installs, verification, status, and receipts share one `.bogos/` state directory.

## Workspace Commands

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
bog status --verbose
bog doctor
bog receipt latest
bog workspace tree
bog corrupt-test project-1.0.0
bog demo pack
bog app run demo-app
```

Equivalent module form:

```bash
python3 -m bog init workspace
python3 -m bog --workspace workspace status
```

## Workspace Layout

```text
workspace/
  .bogos/
    archives/
    bundles/
    receipts/
    store/
    appdata/
    kernel/
    state.json
  restored/
```

- `archives/` stores workspace `.bogarchive` directories.
- `bundles/` stores package bundles created during install/package flows.
- `receipts/` stores action receipts in deterministic order.
- `store/` contains package-store indexes, package bundles, and installed package trees.
- `appdata/` contains per-app runtime working directories used by `bog app run`.
- `kernel/` contains BogK state, process records, mount records, syscall logs, and kernel receipts after `bog kernel boot`.
- `state.json` records archive names, mounts, packages, and the latest receipt path.

## Killer Demo

1. Take a small project folder.
2. Archive it into Bog.
3. Restore it exactly.
4. Install it into the Bog store.
5. Read it through BogFS.
6. Corrupt installed data.
7. Run `bog store verify package-name-version`.
8. Bog rejects it and `bog receipt` shows why.

The test `tests/test_bogos_lite.py` exercises this full sequence. The corruption path mutates an installed file and package verification returns a blocked receipt with `installed tree hash mismatch`.

## UX Hardening

- `bog doctor` checks workspace directories, archives, and installed packages.
- `bog status --verbose` shows archive, mount, package, app, receipt, and latest-receipt details.
- `bog receipt latest` makes latest receipt retrieval explicit.
- `bog corrupt-test` mutates installed data and expects verification rejection.
- `bog workspace tree` prints the managed workspace inventory.

## Public Demo Pack

```bash
bog demo pack
python3 scripts/evaluate_bogos_lite_demo.py
```

The public demo creates a fixture app package, archives it, restores it, mounts it, reads through BogFS, installs it into the package store, verifies it, runs the app, corrupts installed data, rejects it, and emits a final report.

Default report artifacts:

- `artifacts/bogos_lite_demo_report.json`
- `artifacts/bogos_lite_demo_receipt.json`

## Verified App Package

A package exposes app entrypoints and runtime policy through `bog_app.json`:

```json
{
  "format": "BOGOS-app-manifest-6.0",
  "apps": {
    "demo-app": {
      "name": "demo-app",
      "entrypoint": ["python3", "app.py"],
      "allowed_files": ["README.txt", "app.py"],
      "expected_hashes": {
        "README.txt": "<sha256>",
        "app.py": "<sha256>"
      },
      "permissions": {
        "network": false,
        "subprocess": false
      },
      "environment": {
        "DEMO_MODE": "public"
      },
      "read_policy": {
        "allow": ["README.txt", "app.py"]
      },
      "write_policy": {
        "mode": "allowed",
        "allow": ["run.log"]
      },
      "receipt_path": ".bogos/receipts"
    }
  }
}
```

Flow:

```bash
bog store install demo-app-src --name demo-app --version 1.0.0
bog store verify demo-app-1.0.0
bog app run demo-app
```

`bog app run` verifies the installed package before execution. If verification fails, the app is not run and the receipt records the failure reason.

## Runtime Policy

v6 app runs enforce the manifest before and after execution:

- The installed package must verify before the app starts.
- Manifest-declared `expected_hashes` must match files in the installed package.
- The entrypoint file must be inside `allowed_files`.
- The subprocess receives a controlled environment, including `BOG_PACKAGE_DIR`, `BOG_APP_RUNTIME_DIR`, `BOG_APP_ALLOWED_FILES`, `BOG_APP_READ_POLICY`, `BOG_APP_WRITE_POLICY`, and `BOG_APP_RECEIPT_PATH`.
- The app runs from `.bogos/appdata/<app>/`.
- Runtime writes are compared after execution. `write_policy.mode = "none"` rejects every write; `write_policy.mode = "allowed"` accepts only paths in `write_policy.allow`.
- Installed package files are snapshotted before and after execution. If the package tree changes during the run, the receipt is blocked.
- App-run receipts use `BOGOS-app-run-receipt-6.0` and include the nested `BOGOS-app-runtime-policy-receipt-6.0`.

## Boundary

- BogOS Lite uses the existing BOG archive, BogFS, and package-store layers.
- Verification is SHA-256 and tree-hash based.
- Receipt output explains local verification failures.
- App execution is local subprocess execution after package verification and runtime policy checks.
- Read policy is declared and file-hash verified, but reads are not syscall-traced.
- BogOS Lite does not boot hardware, mount a kernel filesystem, manage drivers, fetch remote packages, solve dependency versions, or provide kernel sandboxing.
- BogK adds a user-space kernel contract for verified workspace operations; see `docs/bog_kernel_lite.md` and `THREAT_MODEL.md`.
- v8 brokered apps use the Bog App ABI and explicit capability manifests; see `docs/bog_runtime.md`.

Brokered mode is selected explicitly with `bog kernel run --brokered <app>`. Existing `bog app run` and unbrokered `bog kernel run` behavior remains available for legacy manifests and remains post-run checked.
