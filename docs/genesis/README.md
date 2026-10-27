# Project BogOS Genesis — first engineering milestone

This directory supersedes historical claims where the live reproduction disagrees. It does not change the declared historical release.

- [Existing System Audit](EXISTING_SYSTEM_AUDIT.md): source/history recovery, classification, reproduced behavior and gaps.
- [BogOS Genesis Architecture v0.1](ARCHITECTURE.md): executable BKC subset, mathematical rules, trusted boundaries and planned operational semantics.
- [Engineering Roadmap](ROADMAP.md): milestones and exit gates from i686 research to a usable independent OS.
- [Benchmarks](BENCHMARKS.md): methodology, commands, raw-sample interpretation and measured limitations.
- [Final Technical Report](FINAL_REPORT.md): implemented changes, pass/fail results and next step.
- [Implementation plan](IMPLEMENTATION_PLAN.md) and [independent review](evidence/review.md).

## Reproduce the supported gates

From the repository root, using an already authorised local Docker daemon:

```bash
docker build -t bogos-genesis-dev:1.85.1 -f Dockerfile.genesis .
mkdir -p .cargo-cache
docker run --rm --user "$(id -u):$(id -g)" --cpus=2 --memory=2g \
  -e CARGO_HOME=/work/.cargo-cache -v "$PWD:/work" \
  bogos-genesis-dev:1.85.1 python3 scripts/run_genesis_regressions.py
```

This copies the source to a temporary directory, tests the core, builds the i686 kernel, checks independent fixtures, runs v36/v37/v38 storage tests and the new journal evaluator. It retains logs/results under ignored `artifacts/genesis-regressions/` and destroys only its temporary source copy. It never attaches host disks or rewrites checked-in historical receipts.

Add `--historical` to execute the broader native application evaluators; those currently return failure and must not be described as passing. Add `--python` for the full Python suite (approximately ten minutes in the initial host run, timeout twenty minutes). The container pins Rust/base-image digest and top-level Python package versions; apt packages and transitive Python resolutions are not fully lockfile-reproducible. Exact observed versions are retained. This is a repeatable recipe, not a demonstrated bit-for-bit reproducible toolchain image.

Direct model and proof checks:

```bash
cd kernel
cargo test --locked -p bogk-core
python3 tools/gen_v40_workspace_vectors.py --check
cd ..
python3 kernel/tools/gen_genesis_canonical_vectors.py --check
python3 spec/genesis/check_generation.py
```

The last command needs `z3-solver==4.13.4.0`, available in the container or `requirements-genesis.txt`. It checks an arithmetic model, not compiled Rust. New QEMU evidence comes from `scripts/evaluate_genesis_journal.py`, not the superseded historical v41 script.

Physical deployment, destructive operations and privileged host configuration require a later explicit approval and recovery milestone.
