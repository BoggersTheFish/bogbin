# Evidence provenance

`manifest.json` records SHA-256 values for the retained files (excluding itself). Raw output is intentionally not whitespace-normalised; serial CRLF, terminal progress bytes, warnings, failures and trailing blank lines are evidence, not source-format defects.

- `baseline-evaluators/` and `baseline-evaluators.json`: original default-tip native attempts.
- `expanded-regressions/` and `initial-regressions.json`: earlier changed-tree run, including the oracle invocation error and v37 intermediate failure. These are not the final supported-gate result.
- `final-core-storage-results.json`, `final-core.log`, `final-kernel.log`, `final-vectors.log`: final focused checks from a clean disposable copy.
- `final-journal-results.json` and `final-journal-serial/`: 21 final journal cases and their raw kernel output.
- `stable-v39-*`: tagged release comparison.
- `*-red*`, review controls and `qemu-readonly-drive-unsupported.json`: retained negative evidence; the readonly IDE configuration failed to start QEMU and is not a kernel test result.
- `bkc-benchmark.json`, Linux JSON and SMT JSON: separate scoped experiments. Version/source/scope limitations are in the report and methodology.

Some older command logs include temporary source paths which no longer exist. The input revisions, retained commands and build recipe are the reproduction interface. Old checked-in `artifacts/` receipts elsewhere in the repository were not regenerated as proof of this branch.
