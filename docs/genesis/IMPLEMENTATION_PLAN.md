# Genesis first engineering milestone — 2026-10-27

Base: `0189c47` on `master`; branch `genesis/bkc-resource-transitions`.
The user explicitly requests independent implementation in this session, so routine design choices are delegated. Preserve i686; no physical deployment or privileged host changes.

## Design decision
Repair the existing journal trust boundary before extending it. Then add a deliberately small no-std BKC ownership machine in bogk-core; keep it separate from hardware allocation until refinement tests exist. A kernel rewrite or multicore port now would obscure the baseline. A documentation-only calculus would not test the design.

## Tasks
1. Recover history and reproduce Python, Rust and QEMU baselines in disposable copies. Keep command output and negative evidence. Build a user-invoked container recipe with fixed Rust version and limited resources.
2. Journal: write regressions for the 7-byte Python-compatible canonical tag, strict lengths/version/boolean, zero anchor, sequence and workspace continuity, rejected transitions, and root-after consistency. Observe failures, then repair serialization/validation. Replace unconditional kernel success markers with results from parsed storage. Generate targeted corruptions with refreshed outer checksums so journal rejection is actually exercised. Reject unknown snapshot rollback in the workspace model rather than pretending to restore data. Verify historical v30-v39 checks.
3. BKC: implement fixed-capacity resources with single ownership, generation-bound authority, allocate/transfer/release and atomic rejection. Tests cover stale/foreign handles, resource exhaustion, overflow and bounded exhaustive transition traces. No heap, hashing or persistent I/O on the transition path; optional canonical checkpoint hash. Caller identity and exclusive access are adapter obligations. Integration is shared no-std compilation, not replacement of physical allocation.
4. Benchmarks: measure identical BKC transitions with optional per-operation checkpointing, retaining samples and checking final-state equality. Add a bounded Linux baseline for CPU hashing, memory copying, temp-file sync/read, syscall wrapper and compilation plus wakeup overshoot; record environment and unsupported GPU/AI measurement explicitly. No emulator-versus-native speed claims.
5. Deliver audit, Architecture v0.1, roadmap, methodology and final report. Run full checks, obtain independent code review, commit, push feature branch and open PR. Preserve historical artifacts, failures and unavailable gates.

## Review focus
Fail-open evidence, semantically inconsistent but rehashed journals, ABA/generation reuse, rejection mutation, misleading timing comparisons. Each maps to journal/BKC tests or benchmark equality/metadata checks.

## Initial status (retained history)
Recovery completed. Live hardware metadata checked. Initial system-Python run failed for missing dependencies; dependency-complete run and container build underway. No claim of formal proof or Linux superiority.

## Completion ledger
- Task 1 complete: source/tag recovery, Python baseline and all listed native evaluator attempts recorded. Stable v39 core passes; native disk-app execution fails on both stable tag and current baseline.
- Task 2 complete: test-first journal/Genesis corrections and native adapter; QEMU semantic/storage negatives plus reviewer-discovered tombstone and combined malformed-record cases pass. Old rollback now explicitly requires a snapshot resolver.
- Task 3 complete: BKC reference model, five-step exhaustive trace tests, incarnation negative control, optional checkpoints and scoped SMT arithmetic result. No physical allocator integration claimed.
- Task 4 complete: paired benchmark and bounded Linux seed run; review exposed removable assert workloads, fixed and rerun under optimisation. No OS comparison claim.
- Task 5: code review and final supported-gate run complete; reports and evidence saved; publishing feature branch/PR is the remaining workflow step.

Final engineering source commit: a44e6b8. Decisions: preserve the i686 kernel; narrow integration to storage validation; keep the BKC constructor a trusted boundary with explicitly non-reused incarnations; preserve known historical runtime failures and intermediate failed experiments. No deferred minor review findings were reported.
