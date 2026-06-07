# Bog v7.0.0 JSON Schemas

Bog publishes Draft 2020-12 schemas in `schemas/`:

- `archive-manifest.schema.json`: directory archive manifests.
- `bog-app.schema.json`: `bog_app.json` verified app manifests.
- `bogpk-metadata.schema.json`: decoded `.bog` / `.bogpk` reconstruction metadata.
- `package-receipt.schema.json`: signed package receipts and dependency metadata.
- `kernel-receipt.schema.json`: BogK operation receipts.
- `receipt.schema.json`: the common receipt envelope.

The archive, container, package, app, and BogK code paths validate these schemas before accepting the corresponding documents. Schema validation proves structural conformance only; hashes, signatures, dependencies, policy checks, and delegated receipts provide the remaining proof layers.
