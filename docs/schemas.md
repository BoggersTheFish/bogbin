# Bog v15.0.0 JSON Schemas

Bog publishes Draft 2020-12 schemas in `schemas/`:

- `archive-manifest.schema.json`: directory archive manifests.
- `bog-app.schema.json`: `bog_app.json` verified app manifests.
- `bogpk-metadata.schema.json`: decoded `.bog` / `.bogpk` reconstruction metadata.
- `package-receipt.schema.json`: signed package receipts and dependency metadata.
- `kernel-receipt.schema.json`: BogK operation receipts.
- `brokered-process-receipt.schema.json`: v8 brokered process proofs and ordered capability syscall nodes.
- `receipt.schema.json`: the common receipt envelope.
- `genesis-receipt.schema.json`: signed Genesis and HyperGenesis ledger entries.
- `bogcell-program.schema.json`: deterministic capability-only bytecode.
- `bogcell-app.schema.json`: signed-package BogCell app declarations.
- `bogbuild-receipt.schema.json`: signed source/compiler/bytecode build evidence.
- `bogproof-manifest.schema.json`: portable third-party proof bundles.

The archive, container, package, app, and BogK code paths validate these schemas before accepting the corresponding documents. Schema validation proves structural conformance only; hashes, signatures, dependencies, policy checks, and delegated receipts provide the remaining proof layers.
