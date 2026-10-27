# BogOS Genesis Architecture v0.1

2026-10-27. Status: proposed system architecture with a small implemented reference machine and a repaired native storage-validation boundary. This is not a proof of a complete OS, a replacement of the existing kernel, or evidence of superiority over Linux.

## Foundation and intended kernel

BogKernel is the authority that admits resource-state transitions and installs their hardware consequences. Its core obligation is that execution cannot acquire ownership or authority that the transition rules did not grant. It must also expose progress, timing, durability and external-effect boundaries honestly. Normal application computation need not be verified, hashed or journaled instruction by instruction.

The substrate is a graph of principals, resource objects, capability edges, mappings, runnable contexts, message queues, persistent roots and effect obligations. Current tensions are concrete: ownership versus sharing; revocation versus cached mappings; recovery versus irreversible output; global verification versus local fast paths. TS vocabulary is useful for identifying these constraints. It contributes no additional correctness assumption.

Use a capability-oriented hybrid as an incremental direction. Keep the existing Rust/i686 kernel and move policy into safe modules behind explicit hardware interfaces. Introduce process-isolated services only where the mechanism and failure domain justify the IPC cost. Do not declare a microkernel merely because interfaces are small. The current native implementation is a monolithic research kernel.

### Alternatives and why this direction

| Architecture | Useful property | Cost or unresolved problem for BogOS |
|---|---|---|
| Monolithic | Direct calls, mature locality, simple initial integration | Wide authority and shared failure domain; current unsafe globals prevent a small security TCB claim |
| Microkernel | Explicit IPC and hardware-enforced component separation | Scheduling/IPC/restart protocols and shared-memory lifetimes require engineering; moving a driver does not isolate DMA |
| Exokernel | Applications choose resource policy and avoid imposed abstractions | Secure multiplexing still required; library OSes multiply compatibility and debugging work |
| Library OS | Workload specialisation and reusable personality layers | Not an authority boundary by itself; poor default for arbitrary mutually hostile desktop apps |
| Capability OS | Explicit grants, attenuation and revocation | Capability derivation, quotas, namespace discovery and revocation costs must be designed |
| Component/framekernel | Compiler-enforced local interfaces, fewer state dependencies | Safe APIs must be sound under hostile callers; language safety is narrower than functional/security correctness |
| Hybrid (chosen) | Test each separation without discarding existing code | Requires a precise boundary map to avoid becoming an undocumented monolith |

These alternatives are not new discoveries. The [exokernel work](https://pdos.csail.mit.edu/papers/exo-sosp97/exo-sosp97.html) separates protection from application policy. [Theseus](https://www.usenix.org/conference/osdi20/presentation/boos) studies component boundaries and state spill. [Asterinas](https://www.usenix.org/system/files/atc25-peng-yuke.pdf) confines unsafe mechanisms to a framework to reduce the memory-safety TCB. These are useful precedents, not proof that BogOS has their properties.

## BKC transition semantics

The long-term state has components `Σ = (D, R, M, P, C, Q, J, E)`:

- `D`: domain incarnations and trusted identity bindings.
- `R`: owned resources and monotonic generations.
- `M`: mappings, permissions and outstanding resource references.
- `P`: execution contexts and lifecycle states.
- `C`: capability derivation graph and rights.
- `Q`: run queues, wait queues and IPC endpoints.
- `J`: persistent checkpoints and transition history.
- `E`: external-effect frontier and acknowledgements.

This tuple is a specification vocabulary, not eight new implementation frameworks. A typed operation has a precondition, a bounded state update, and explicit effects:

`admit(Σ, authenticated_principal, operation, observed_event) = Reject(reason, Σ)`

or

`admit(...) = Accept(Σ', hardware_obligations, optional_durable_record)`.

Reject must preserve admitted state. Hardware obligations do not disappear because a pure model accepted an operation. Installing mappings, invalidating TLB entries, ordering DMA and flushing storage require operational semantics and completion/failure handling.

### Implemented BKC subset

`kernel/bogk-core/src/bkc.rs` implements only `D` and a fixed `R` with opaque authority handles. No physical frames, process scheduler, map rights, quotas, derivation tree or persistence are managed by this module.

For resource `i`, `R[i] = (owner, generation)`. Owner zero means free. A handle is `a = (domain, i, owner, generation)`. Validity requires a resource in range, matching domain, matching owner and generation, and a nonzero authenticated caller equal to that owner.

| Operation | Preconditions | State change |
|---|---|---|
| Allocate(owner) | owner nonzero; reusable free slot exists; generation below `2^64−1` | lowest reusable free slot becomes `(owner, generation+1)`; return its handle |
| Transfer(caller, a, target) | valid handle; target nonzero; generation below maximum | same resource becomes `(target, generation+1)`; return replacement handle |
| Release(caller, a) | valid handle; generation below maximum | same resource becomes `(0, generation+1)` |
| Any rejection | precondition fails | no slot changes |

Each slot has one owner. The number free plus the number owned equals fixed capacity. Copying a handle does not duplicate a slot. Transfer/release invalidate earlier handles even when ownership later returns to the original principal. Generation exhaustion rejects instead of wrapping, trading availability for stale-handle safety.

**Trusted constructor obligation:** a domain identifies an incarnation and must never be reused while any previous handle can survive. `ResourceState::new` does not enforce this global rule. The test suite contains a negative control showing resurrection when that precondition is violated, and rejection when a different incarnation is used. Caller identity and exclusive access are also adapter obligations. Safe Rust opacity is not a cryptographic credential and must not become a user-supplied syscall token unchecked.

The state is deliberately neither Clone nor deserializable. An application rollback must never rewind authority generations, restore an old live capability table or duplicate a domain. Reconstructing a persistent resource state will require a monotonic incarnation protocol, not merely loading a prior hash.

### Evidence and proof boundary

The Rust tests cover invalid principals/handles, foreign domains, reuse, stale handles, transfer, resource exhaustion, checked generation overflow and 32,768 five-step traces. The trace search is bounded testing, not exhaustive verification of arbitrary histories.

`spec/genesis/check_generation.py` asks Z3 whether a checked unsigned 64-bit increment can equal any earlier generation, including after subsequent non-wrapping increments. Both counterexample queries are UNSAT. A wrapping control is SAT at maximum→zero. This is a machine-checked arithmetic model result. It is not a refinement proof of the Rust source, compiler, binary, caller authentication, synchronisation or hardware. A useful next formal step is a Verus proof against the actual transition methods. [Verus](https://verus-lang.github.io/verus/guide/) performs static specification checking; proof effort need not add runtime verification work.

## What can and cannot be derived

| Mechanism | Derivable rule or invariant | Additional operational semantics |
|---|---|---|
| Allocation | Unique ownership, conservation, quota admission | Physical inventory, reserved memory, zeroing, fragmentation and reclaim |
| Address spaces | A mapping requires frame authority and compatible rights | Page-table formats, aliasing, NX, TLB shootdown, accessed/dirty bits |
| Process creation | Atomically admit context, address-space and execution budget | Register/stack ABI, privilege return, FPU/SIMD state, faults |
| Capabilities | No authority amplification; lineage and revocation | Identity binding, table lookup, epoch persistence, side channels |
| IPC | Bounded queues and transferable authority without duplication | Copy faults, cancellation, wakeups, memory ordering and zero-copy pinning |
| Scheduling | Runnable eligibility and budget conservation | Fairness, deadlines, interrupts, multicore ordering and time measurement |
| Storage | Validated root/chain transitions, defined commit points | Write ordering, torn sectors, volatile caches, barriers and crash recovery |
| Rollback | Restore resolved immutable content/state snapshots | External effects and authority epochs cannot be rewound |
| Devices | Access requires MMIO/port/interrupt/DMA authority | Actual device protocols, reset, IOMMU and bus-master containment |
| Adaptation | Proposed policy must obey resource/security guards | Objective quality, convergence, overhead, stability and adversarial workloads |

Do not seek universal confluence. Independent operations on disjoint resources can commute under stated assumptions; two competing transfers cannot. Determinism means identical initial state and ordered input/event trace produce identical admitted results. Real interrupt arrival and device completion are inputs, not facts derived from the calculus. The [Verse Calculus](https://simon.peytonjones.org/verse-calculus/) motivates a small-step semantic method; its functional-logic rewriting is not a ready-made model of hardware or kernel effects.

## Trusted computing base and interfaces

The intended minimum **authority TCB** includes the resource/capability validator, identity binding, mapping installer/revoker, execution-state switch, interrupt entry, IPC ownership transfer and durable commit validator. Boot code, compiler/linker, CPU/MMU and relevant firmware/hardware remain assumptions unless independently verified. A memory-safety TCB and an authority/information-flow TCB are different sets.

The current TCB is much larger: essentially the native kernel, unsafe globals, allocator, drivers, parser/hash implementation and boot/assembly path. The new module does not shrink that TCB by declaration. [seL4's verified configurations](https://docs.sel4.systems/projects/sel4/verified-configurations.html) and [assumptions](https://sel4.systems/Verification/assumptions.html) illustrate why platform coverage, boot, DMA and hardware-management assumptions must be stated explicitly.

Proposed interfaces, not yet implemented:

1. `AuthorityCore`: admit object creation/grants/transfers/revocation from authenticated principals.
2. `Arch`: install/revoke mappings and switch contexts; expose completion before releasing physical resources.
3. `Persistence`: prepare data, order durability, atomically select an admitted root, recover or reject.
4. `DeviceBroker`: bind driver domains to explicitly granted device resources and effect channels.

The implementation adapter must unmap or drain references before releasing/transferring a mapped frame. Updating an owner field does not revoke an already installed mapping. Avoid exposing raw BKC methods as a page allocator until these obligations are tested.

## Execution and performance paths

Retain current round-robin semantics as the i686 reference. First reproduce context save/restore and preemption; do not optimise an unconfirmed transition. After correctness, measure direct syscall return, cross-address-space IPC, timer entry and runnable latency distributions with logging disabled in timed regions and enabled in separate correctness runs.

For x86-64/SMP, explore per-CPU run queues, local allocation caches, cache-line separation, bounded work stealing and per-object locks. Avoid a global hash-chain lock on every allocation or context switch. Canonical checkpoints can be composed at durable/security boundaries; their synchronisation semantics must be defined before claiming deterministic multicore replay. NUMA, contention, working sets and false sharing require measurement, not a single global 'tension' score.

Normal trusted resource lookup and bounded ownership changes use local checks without full-state hashing. Image admission, authority-changing transitions, executable validation and persistent commit have stronger validation obligations. Optional receipts cannot remove security checks. The benchmark in this branch measures the cost of deliberately adding a 64-resource checkpoint after every transfer; it is not a security-equivalent replacement for a durable ledger or a Linux syscall benchmark.

## Persistence and irreversible effects

The repaired native v41 path reads existing v38 manifest storage and validates canonical 277-byte GenesisRoot and 212-byte JRNLv41 records. It checks record type, data bounds, hashes/padding, framing, zero chain anchor, sequence, receipt version, root continuity, rejected-transition non-mutation, historical rollback target membership, ledger head and final Genesis workspace agreement. Genesis/journal record presence selects a read-only validation mode before semantic parsing; malformed metadata cannot fall into legacy mutation demos.

These checks establish structural consistency, not historical authorisation. A party able to replace the entire image and every hash can forge a self-consistent history. `verifier_hash` is a label, not a signature. Restore must bind to an externally trusted root or independently authenticated policy. The initial workspace root is not supplied as an independent trust anchor to the journal verifier.

Current rollback receipts describe root history. They do not recover materialised file contents. The old workspace apply path now returns `SnapshotRequired` for rollback because no snapshot resolver is supplied. A future implementation must verify target objects, reconstruct paths/content, preserve the current authority incarnation and append a new recovery transition.

Crash safety needs explicit power-loss semantics and fault injection after each device write/flush. Clean two-boot survival is insufficient. [FSCQ](https://css.csail.mit.edu/fscq/) is prior art for specifying crashes and recovery. Selective journaling needs an explicit durability contract: volatile operations may be lost before checkpoint; committed operations survive the agreed failure model.

Model external effects as prepare → issue → acknowledge, with an irreversible frontier. Network sends, displayed output, actuator movement and GPU execution cannot generally be undone. An ambiguous acknowledgement requires idempotency or reconciliation; never claim exactly-once effects solely from a kernel journal. Recovery may repeat computation while preserving effect IDs and authority generations.

## Applications, drivers and desktop path

Continue `.bogapp` loading as a bounded native ABI fixture. Specify process lifecycle, termination, errors, capability lookup and resource cleanup before broadening the format. Then add a versioned x86-64 executable ABI, loader relocation rules, native runtime and basic toolchain. A POSIX or Linux compatibility personality may be an optional service/library layer; it is not the computational foundation or a current feature.

Move serial/block/network drivers into isolated components incrementally. User mode alone is insufficient for arbitrary DMA devices: use IOMMU mappings where available, otherwise treat the DMA driver and device as trusted or decline isolation claims. Start with QEMU virtio devices, shared-memory ownership protocols and crash/restart tests. Real RX480/1050Ti drivers, GPU memory management and firmware integration are major independent programmes.

A usable graphical environment requires framebuffer/compositor, input routing, fonts, accessibility, storage/app lifecycle, networking, sound, package/update recovery and security prompts a person can understand. Start with a software compositor and one native application in QEMU. [Redox's upstream introduction](https://github.com/redox-os/book/blob/master/src/introduction.md) is a useful precedent for the scale of building a Rust OS and application environment; BogOS has not implemented that environment.

## Novelty and falsifiable research

Capabilities, ownership, generation counters, small-step rules, immutable roots, journals, library OSes, Rust safety and selective durability are established techniques. This branch claims no novel kernel result. A possible research contribution is a measured composition of authority transitions, recovery roots and external-effect frontiers with selective verification. That needs a precise specification, comparison against existing systems and convincing workloads.

TS-inspired adaptation is a hypothesis only: a bounded controller using queue pressure/cache misses/fault costs might improve a fixed workload mix over round-robin or static budgets. Pre-register workloads and seeds, compare equal-budget controllers including conventional heuristics, include controller CPU/memory overhead and migration costs, use held-out workload changes, and reject the hypothesis if p99 latency, throughput, starvation or security regression gates fail. A winning post-hoc score is not a predictive policy.
