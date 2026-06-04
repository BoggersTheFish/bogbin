# BogOS Lite

BogOS Lite is the v4.0 user-space workspace milestone.

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
bog receipt
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

## Boundary

- BogOS Lite uses the existing BOG archive, BogFS, and package-store layers.
- Verification is SHA-256 and tree-hash based.
- Receipt output explains local verification failures.
- BogOS Lite does not boot hardware, mount a kernel filesystem, manage drivers, fetch remote packages, solve dependencies, or verify signatures.
