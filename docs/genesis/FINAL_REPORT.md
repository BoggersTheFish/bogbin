# Final Technical Report — Genesis first milestone

2026-10-27. Base `0189c47`, source implementation commit `a44e6b8`, feature branch `genesis/bkc-resource-transitions`. This is a bounded engineering advance toward the long-term programme, not completion of the operating system.

## What existed

The repository already contained a substantial Python verified-storage/VM/workspace system and a native Rust/x86 i686 research kernel. Native source implements boot, interrupts, paging, Ring 3 process paths, scheduling, custom syscalls, IPC, bounded in-memory files, ATA PIO and persistent filesystem fixtures. Their existence and their reproducibility are separate facts. [The audit](EXISTING_SYSTEM_AUDIT.md) classifies each layer and identifies failed checks and contradictory claims.

The default-tip Rust tests did not compile. The former v41 kernel printed fixed successful journal/rollback/root markers before validation. Journal serialization panicked, Genesis parsing swapped fields and its hashing buffer was undersized. Workspace rollback did not restore the requested snapshot. Those defects made a documentation-only extension unsafe.

## Implemented changes

- Restored native core test compilation without changing the existing historical tests.
- Corrected canonical GenesisRoot/JRNLv41 lengths, field order, strict versions/booleans/framing and hashing-buffer bounds; added independent Python byte/hash fixtures.
- Enforced chain anchor, sequence, root continuity, root-after agreement, rejected-transition non-mutation, rollback target membership and final Genesis/ledger agreement.
- Integrated bounded multi-sector content and journal validation with the existing native kernel. Removed both unconditional success blocks; success/final-root/rollback markers now derive from parsed storage. Genesis record presence selects read-only validation before parsing, including combined corruption/missing-journal cases. Tombstoned journals cannot validate.
- Made unsupported materialised workspace rollback fail with `SnapshotRequired`; no invented snapshot recovery.
- Added a no-std BKC exclusive-resource reference machine with opaque generation/domain-bound handles, checked allocation/transfer/release and optional checkpoints. It does not replace the physical allocator or enforce non-reused domain incarnations globally.
- Added an SMT generation-rule check with a wrapping negative control, a paired host microbenchmark and a bounded Linux observation script.
- Added a pinned-Rust/base-image build recipe and a regression runner using disposable source copies, bounded process groups and separate raw evidence. Old checked-in receipts are preserved.
- Added Architecture v0.1, audit, roadmap and benchmarking methodology with primary-source research and explicit novel-versus-established distinctions.

## Executed checks

| Check | Observed result |
|---|---|
| Original system Python, missing declared jsonschema dependency | 113 tests: 20 failures, 38 errors, two skips; retained as environment failure |
| Dependency-complete original Python suite | **113 tests, OK, two skips**, 605.548 s; skipped flagship demos are named in the raw log |
| Original default-tip Rust suite | Fails compilation: seven missing test macro errors |
| Same old core after imports only | 49 existing tests pass; six added bug regressions then fail as expected |
| Final native core | **64 passed**, including 32,768 five-step BKC histories, canonical Python fixtures and domain-reuse negative control |
| Stable v39 tag core | **40 passed** |
| i686 debug kernel | Builds; original and final build logs retained; numerous existing warnings remain |
| v16 boot | Passes on original and changed code |
| v36/v37/v38 storage | Pass on original and final focused run; one intermediate v37 failure retained and unresolved |
| v40 independent oracle | Matches existing fixtures, no drift; runner's initial wrong working-directory invocation was corrected and its failure retained |
| New journal QEMU evaluator | **21/21 passed**: valid three-entry chain, remount of the same image, 19 semantic/storage rejection cases; disk bytes unchanged |
| Generation SMT model | Checked-step/future counterexamples UNSAT; wrapping control SAT; normal and `-O` execution agree |
| Host BKC benchmark | Final-state equality holds for all paired samples |
| Linux seed benchmark | Runs normally and under `-O`, validates outputs; workload-removal bug found by review and corrected |

**Known failing/unavailable gates:** original v26/v26-negative/v27/v28/v29/v30 evaluators do not complete native application runs. Original v31/v32/v33/v34/v35/v35.1 are first blocked by core-test compilation; after its repair, they reach the same application-demo completion failure. v39 disk-app execution times out on both the stable v39 tag and default-tip/changed code. The cause is not established. Historical v40/v41 scripts first fail their wrong binary-path gate; v41 also has ineffective corruption/evidence checks. They remain historical, superseded by the new targeted journal evaluator, not represented as passing.

The expanded runner intentionally returns nonzero when these historical failures are included. Its first invocation also had an author-introduced working-directory error for the oracle command; the final focused run corrects it. Do not read a final focused green result as a green result for all historical milestones.

Two opt-in Python demos were skipped by the existing suite: `test_genesis_demo_cli_emits_final_receipt` and `test_hypergenesis_demo_cli`. They were not run separately. GPU/AI throughput, multicore stress, actual GUI latency, physical OS deployment, power-loss crash tests and formal refinement of Rust/assembly were not executed.

## Measurements

BKC/Linux host experiment, 64 resources, 21 recorded batch pairs: local transfer median **2.983 ns/operation**; adding an O(64) full checkpoint after every transfer median **16,115.341 ns/operation**. Equal final state was checked. These are tiny-hot-working-set batch averages and different evidence costs, not equal-durability kernels or OS speed comparisons.

The Linux seed run took about **0.97 s**. Median samples included 16 MiB SHA-256 **29.877 ms**, 64 MiB repeated libc copies **2.324 ms**, buffered 4 MiB write+fsync **10.988 ms**, tiny C compile/link **30.639 ms**, and 1 ms sleep overshoot **0.165 ms**. Runtime/cache/measurement limitations and raw distributions are in [BENCHMARKS.md](BENCHMARKS.md). No Linux-superiority result is established.

## Review and remaining limitations

A fresh reviewer independently executed core tests and adversarial QEMU/benchmark/domain probes. Four Important findings were addressed with targeted regressions or an explicit bounded-model precondition; details and the negative controls are in [review.md](evidence/review.md). No second independent review or complete security audit is claimed.

The current native TCB remains broad. Unsafe globals, interrupt-state discipline, allocator non-reclamation and the failed native execution gates prevent a production or isolation-assurance claim. Journal structure is not historical authorisation: a fully rehashed image can be self-consistent without being trustworthy. Root history is not materialised snapshot recovery. Generation arithmetic proofs do not verify source-to-binary refinement. Domain incarnations must never be reused while old handles survive; the model records rather than enforces that global obligation.

## Next milestone

**Restore and repeatedly verify native process/context-switch execution before extending scheduling or porting the runtime.** Pin the current toolchain, reduce to one exit/yield app, instrument stack/register/return invariants, compare against the stable tag, and resolve v26–v35.1/v39 completion failures. Then refine one actual page lifecycle through the BKC model with tested mapping revocation and resource cleanup. See [ROADMAP.md](ROADMAP.md).

## GitHub delivery

The feature branch is intended for a draft pull request against `master`, with the above failures disclosed. No default-branch modification or merge is authorised by this milestone. The final response provides the actual commit/PR status after publication is verified.
