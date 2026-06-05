# BogOS Lite

BogOS Lite is the user-space workspace milestone that now spans v4.0 through v5.0.

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
    state.json
  restored/
```

- `archives/` stores workspace `.bogarchive` directories.
- `bundles/` stores package bundles created during install/package flows.
- `receipts/` stores action receipts in deterministic order.
- `store/` contains package-store indexes, package bundles, and installed package trees.
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

A package can expose app entrypoints through `bog_app.json`:

```json
{
  "format": "BOGOS-app-manifest-5.0",
  "apps": {
    "demo-app": {
      "command": ["python3", "app.py"]
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

## Boundary

- BogOS Lite uses the existing BOG archive, BogFS, and package-store layers.
- Verification is SHA-256 and tree-hash based.
- Receipt output explains local verification failures.
- App execution is local subprocess execution after verification.
- BogOS Lite does not boot hardware, mount a kernel filesystem, manage drivers, fetch remote packages, solve dependencies, sandbox apps, or verify signatures.
