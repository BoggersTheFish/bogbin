# Engineering Roadmap

Milestones are ordered by dependency and exit evidence, not optimistic dates. Keep i686 as the research reference until an x86-64 replacement passes equivalent behavior checks. Every milestone retains failed experiments and a reproducible status file.

| Milestone | Engineering work | Exit gate |
|---|---|---|
| G0: honest reproducibility (this branch) | Isolated build, classify old evidence, repair native Genesis/journal boundary, bounded BKC reference machine, benchmarks | Core/boot/storage/new journal checks execute; old failures explicitly listed; no unsupported recovery/performance claims |
| G1: native execution baseline | Diagnose Ring 3 entry/exit/longjmp, stack alignment, segment/TSS and saved context; restore interrupt-state discipline; test compiler/optimisation variants | v26–v35.1 and v39 app execution checks all complete repeatedly; canary/reg-save/fault tests pass; logging-independent correctness |
| G2: ownership-to-MMU refinement | Replace one physical-page lifecycle with BKC-backed authority; track mappings, revoke/flush before reuse; quotas and resource cleanup | Host oracle and QEMU agree on traces; stale/foreign/aliased mappings cannot access transferred frames; one actual Rust invariant verified with Verus or equivalent |
| G3: recoverable workspace | Materialised immutable content/index snapshots; authorised transitions; explicit trusted root; atomic durable commit; real rollback resolver | Crash injection after each write/flush yields an admitted old/new state; file bytes/path view reconstructed; rejected restore preserves state; epochs never rewind |
| G4: x86-64 platform | Separate arch layer, long mode, 4-level tables, NX/W^X, exceptions, syscalls and full register state; versioned native executable ABI | i686 fixtures and x64 equivalents pass; kernel/user permission and pointer-crossing tests pass; x64 kernel boots through disposable UEFI/BIOS fixtures |
| G5: modern I/O and isolation | Virtio block/net/input, interrupt domains, bounded buffer ownership, DMA model and driver restart protocol | Malformed descriptors/driver crashes contained in QEMU; DMA authority assumptions explicit; no stale buffer access after restart |
| G6: multicore and sustained memory | AP startup, per-CPU queues, locks/atomics, scalable allocator/reclamation, contention telemetry | 1/2/4/8-vCPU correctness and fairness; no leaks under sustained cycles; matched Linux-guest tests report throughput, memory and p99/p99.9 |
| G7: useful application environment | Native runtime, filesystem namespace/permissions, packages with rollback, networking, terminal/editor/build tools | Third-party port or native app completes meaningful tasks; install/update failure recovery verified; applications cannot mint authority |
| G8: graphical desktop | Software compositor/framebuffer, input focus/permissions, fonts/accessibility, sound, settings and application launcher | Repeatable user task suite, measured input-to-frame latency, compositor crash recovery and accessible interaction |
| G9: hardware pilot | Exact hardware inventory, explicit owner approval, recoverable backups, removable-media boot, limited drivers | Recovery rehearsal succeeds first; no host disk writes unless separately approved; serial evidence and rollback procedure retained |
| G10: production programme | Driver breadth, GPU stack, security response, compatibility, installer/update system, fuzzing, long-duration reliability and usability studies | Independently repeated workload-specific advantages and reliability/security evidence; clearly stated unsupported hardware/workloads |

## Immediate G1 experiment

Pin the current Rust/QEMU build and a small app that exits through the existing interrupt ABI. Save the user entry state, syscall entry state, kernel jump buffer, stack bounds and return target without serial formatting inside the critical window. Compare expected stack/register canaries before/after exit, then two-process yield and timer preemption. Bisect against the v39 tag in the same environment. Change one mechanism per experiment; do not replace the scheduler to hide the failure. Preserve failed traces and distinguish emulator/timing/toolchain effects from kernel defects.

Investigate the v37 intermittent failed commit concurrently only when independent instrumentation can avoid changing the test's semantics. The current ATA poll bound and interrupt handling merit inspection, but are hypotheses rather than established causes.

## Performance experiment ladder

1. Shared pure operation kernels on Linux: correctness, instruction/work counts, optional-validation costs. This branch supplies only the first microbenchmark.
2. Equivalent native workloads inside BogOS and Linux guests under identical QEMU/KVM settings. Keep security/durability/logging contracts equal. Do not compare emulated BogOS directly to native Linux.
3. Controlled physical comparison only after G9 approval and recovery gates. Record CPU/GPU model, microcode, memory, firmware, device drivers, power state, kernel configuration, cache/durability policy and mitigations.
4. Held-out application mix and long-duration trials. A win on one operation is a workload-specific result; “better general-purpose OS” needs broad application, reliability, security and usability evidence.

## Research stop rules

- No speed claim when output, rejection behavior or durability differs from the baseline.
- No adaptive-policy win from post-hoc workload selection or free controller computation.
- No safety claim inferred from valid hashes alone, bounded tests, source language or a receipt string.
- No transition to x86-64/SMP/real GPU work until the preceding lifecycle interfaces can be tested in isolation.
- If a design increases tail latency, leak rate, authority exposure or recovery ambiguity beyond its agreed budget, reject or narrow it even if mean throughput rises.

The long-term goal remains an independently developed, usable OS. Linux currently has overwhelming advantages in driver support, application compatibility, operational maturity and accumulated optimisation. Challenge those with measured alternatives rather than assuming architectural novelty will overcome them.
