# Existing System Audit — 2026-10-27

## Recovery and scope

Canonical source recovered from `https://github.com/BoggersTheFish/bogbin`. Default `master` was `0189c47` (2026-06-16); 80 commits were reachable from that tip. Work starts from that exact revision on `genesis/bkc-resource-transitions`. The annotated stable-release tag `v39.0.0` resolves to commit `8dace9a11e29411171cfb5581ca1b19b99494720`; the tag object itself is `c5827089...`. The label “stable” is a historical declaration, not a reproduced reliability result.

`origin/workstream/baremetal` contains two later June 17 commits including a Multiboot/video/GRUB workstream. It was inspected as history, not merged or deployed. No bootloader, firmware, partition or privileged host settings were changed. The connected issue search returned no open issues at audit time; the unresolved issues below come from source/tests, not an assumption that an empty tracker means no defects.

The audit covers repository layout and history, native core/kernel mechanisms, all Python test modules through execution, the v26–v41 evaluator boundaries, storage makers, threat model and release/status documents. It is not a complete line-by-line security audit of every Python parser or native instruction. Raw evidence is in [evidence](evidence/); commands and tool versions accompany the results.

## Substrate and architectural boundaries

| Layer | Source | Actual responsibility |
|---|---|---|
| Python BOGVM/BOGBIN | `bogvm/vm.py`, assembler/container/optimizer/bases | Deterministic graph/fixed-point VM and exact byte reconstruction/storage experiments on Linux |
| Python BogFS/BogOS Lite/BogK | `bogvm/archive.py`, `bogos.py`, `kernel.py`, `store.py` | User-space archives, package verification, policy checks and brokered I/O |
| Python Genesis/HyperGenesis | `genesis.py`, `hypergenesis.py`, `bogcell.py` | Signed session ledger, COW state, replay, restricted VM and portable proof/reference workflows |
| Native core | `kernel/bogk-core/src/lib.rs` | No-std VM subset, hashes, process/scheduler metadata and v40/v41 workspace models |
| Native kernel | `kernel/bogk-kernel/src/main.rs` | i686 Multiboot entry/assembly, interrupt/syscall paths, paging, process slots, IPC, bounded in-memory and ATA-backed filesystem demonstrations |
| Host evaluators | `scripts/evaluate_*.py`, image makers | Assemble fixtures, build/boot QEMU, parse serial evidence and check expected cases |

Before this branch the native files were approximately 3,790 and 6,640 lines respectively. The core has no runtime crate dependencies; serde_json is a test dependency. The kernel depends on the core and uses `alloc`. Most native subsystems share one kernel address space, mutable globals and a large source file. This is a real independently developed research kernel, not a Linux distribution, but also not a production desktop operating system.

The Python runtime and native kernel must not be conflated. The Python threat model explicitly says it is not a syscall sandbox. Brokered calls can reject unauthorised official I/O without preventing arbitrary native host syscalls. BogCell's instruction set has a narrower I/O boundary. Native Ring 3 isolation is a separate implementation with separate proof obligations.

## Reproduced evidence and classification

### 1. Implemented and independently reproducible within tested scope

- Dependency-complete Python suite: **113 tests, OK, two opt-in demos skipped**, 605.548 seconds on this machine. This exercises storage/container reconstruction, archives, signing/policies, brokered capabilities, Genesis state/replay and VM/reference workflows. It establishes the tested Python behavior, not native-kernel feature equivalence or general host isolation.
- Default-tip kernel builds with Rust 1.85.1 for `i686-unknown-linux-musl`; QEMU v16 boot evaluator passes and audits ELF32/i386, freestanding linkage and serial boot markers.
- The v36 block, v37 persistent single-file and v38 lifecycle evaluators pass on the original default tip. These exercise bounded QEMU ATA PIO, checked sectors, alternate roots and clean reboot survival, respectively.
- The stable v39 tag's host core suite passes **40 tests**. Its end-to-end disk-app evaluator also times out under the same toolchain (`stable-v39-app.log`); a host model pass does not establish Ring 3 execution.

### 2. Implemented but not independently confirmed end to end here

- Native Ring 3 entry/return, per-process mappings, context save/restore, quantum preemption, dynamic loading, ABI v2, IPC and bounded writable syscall paths exist in source, examples and evaluator logic. Historical artifacts claim success. In this environment the v26–v30 runtime evaluators did not complete; after the test-build repair, v31–v35.1 reach the same application-demo failure. These features cannot be promoted to independently reproduced results in this session.
- v39 persistent `.bogapp` parsing/admission has native code and fixture checks, but the end-to-end QEMU evaluator times out before completion. Root cause of the user execution failure is not established. Investigate the low-level return/context/stack path before adding scheduling features.
- v40 workspace transitions have meaningful independent-oracle vector coverage once test compilation is repaired. Some additional named invariant tests are placeholders. Materialised object/path metadata is not equivalent to recoverable file content storage.
- One expanded regression run saw v37 fail “boot one did not commit exactly one root”; the original run and final targeted run pass. The earlier failed result remains in `initial-regressions.json` and its log. Its cause is unresolved; the final pass does not establish absence of flakiness.

### 3. Prototypes and reference models

- TS/BOGVM wave-state operations, basis/residual reconstruction and optimizer tournaments are executable research, not evidence that a wave model outperforms conventional computation. Exact roundtrip success and compression/performance advantage are different claims.
- Python BogBoot/BogIRQ/BogMesh/BogPilot workflows are reference-model evidence; their capability/event/claim processing does not implement native interrupt handling, a production distributed network or a general AI scheduler.
- v40 capability checking accepts a public fixed sentinel hash. That is a model guard, not a principal-bound native capability policy engine.
- v41 root-history rollback did not resolve or restore a previous materialised workspace. The old `apply_workspace_operation` rollback ignored its target and returned a newly shaped root over current tables. This branch now rejects that unsupported action with `SnapshotRequired`.

### 4. Proposed or absent systems

No production-grade SMP, demand paging/reclaim, swapping, ASLR, general executable loader, durable mutable application workspace, comprehensive capability delegation/revocation, crash-verified filesystem, network stack, modern GPU driver, graphical desktop/application environment or self-hosting development system was established. The current drivers are narrow serial/VGA/PS2/legacy ATA research paths. The isolated BKC resource model added in this branch does not implement these missing mechanisms.

### 5. Obsolete, contradictory or misleading documentation/evidence

- README calls the project v39 while describing v40 Phase D both as incomplete and complete in different places.
- `kernel/README.md` still describes full bytecode execution as future work despite a native opcode subset, and says boot/execution evidence is “signed/deterministic”; native serial markers are not cryptographic signatures.
- v40 documentation claims completed model invariants while tests 9/10 include a root-change placeholder and a self-equality assertion. They remain historical tests; this branch adds behavioral regressions instead of counting those assertions as proof.
- v40/v41 evaluators expect `kernel/target/debug/bogk-kernel`, whereas the documented working build produces `kernel/target/i686-unknown-linux-musl/debug/bogk-kernel`. Their original invocations fail at that path gate. Even with a correct path, v41's “missing_journal” XOR-by-zero case is a no-op and other corruptions target approximate image offsets. It must not be used as the new evidence authority; the replacement evaluator uses targeted, rehashed cases.
- Most seriously, `0189c47` unconditionally emits v41 success/final-root/rollback markers both in early boot and in the v38 path, before real journal validation. “Kernel-emitted” did not mean “kernel-verified.” The new evaluator fails on that baseline and both unconditional blocks are removed here.
- Checked-in receipts and serial files remain historical artifacts. They were not refreshed to make the branch look green. The new runner uses disposable source copies and separate evidence directories.

## Native defects found and addressed

1. Seven-byte `JRNLv41` copied into an eight-byte destination: panic in serialization, incompatible parser length.
2. GenesisRoot serializes 277 bytes but computes its hash with a 256-byte scratch buffer: panic. The parser also swaps kernel-receipt and workspace fields and accepts trailing bytes/unknown versions.
3. Journal parsing accepted noncanonical booleans and trailing bytes; chain validation did not enforce zero anchor, sequence, root continuity, root-after consistency or rejected-transition non-mutation.
4. Genesis record type 4 was rejected by generic v38 mounting, while the journal spans sectors beyond the ordinary-file bound. Bounded, path-specific content validation was missing.
5. Fixed success markers made storage evidence fail open. Corrected mode selection must also reject malformed Genesis when the journal is absent and prevent legacy mutation fallthrough.
6. Review found a tombstone-type bypass in the new adapter; the final adapter requires a live journal file and its QEMU regression passes.
7. No-std test-module macros prevented the original default-tip core suite from compiling. Adding imports exposed and permitted reproduction of the above bugs.

The native code still emits many compiler warnings, notably references to mutable statics. The bump allocator unconditionally executes `cli`/`sti` and does not restore prior interrupt state; deallocation records counters without reclaiming memory. These are serious audit targets before SMP or long-running use. This branch does not claim to fix those broader issues.

The historical `sha256` deliberately retains nonstandard full-block behavior for compatibility; `sha256_standard` exists for standards-compliant block hashing. New BKC checkpoints use the latter. Genesis/journal canonical lengths are not full blocks and are cross-checked against Python SHA-256 fixtures. Do not expand use of the historical hash function or silently change old roots without a versioned migration.

## Reference platform and operational limits

Live normal-user access and both connected machine services are available. BoggersOS reports machine/storage metadata; BoggersRemote reports authenticated normal-user authority. The local shell already runs on BoggersThePC, so benchmarking does not require a second remote process.

Confirmed: i7-7700K, 4 cores/8 logical CPUs; 33,601,761,280 bytes visible RAM; Z270 GAMING PRO CARBON (MS-7A63); Linux Mint 22.3; kernel `7.0.0-38-generic`; Radeon RX480 with 8192 MB via GLX and sysfs; GTX1050Ti with 4096 MiB via nvidia-smi. PCI and driver metadata are saved. DDR4 is consistent with the reported platform, but privileged DIMM/SPD decoding was not performed; do not call its exact speed/timings verified.

Native builds run in a bounded user-invoked Docker environment. No host toolchain or privileged settings were installed. QEMU uses disposable ordinary files, no host disk passthrough, no GUI interaction and no KVM access. The Linux baseline is deliberately short, single-process/small workload, and leaves caches/governors/desktop services alone. GPU/AI throughput and actual desktop input latency are not measured.

## Readiness assessment

BogOS is a substantial research substrate with reproducible host verification and a narrow boot/storage baseline. Its strongest immediate advance is restoring honest, executable evidence at a previously misleading trust boundary. It is not ready for physical installation, untrusted general-purpose workloads or a desktop performance comparison with Linux. The next gate is reproducible native application/context-switch execution, followed by mapping/resource-lifetime refinement and crash-fault testing.
