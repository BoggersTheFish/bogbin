# Bogbin Bare-Metal Transition Roadmap

## Status And Goal

This is the canonical living document for transitioning Bogbin from a QEMU-only
research prototype to a dual-bootable verified research OS on real laptop hardware.

**Current baseline:** v39.0.0 release; v40 Genesis Workspace Root Phase D and v41
workspace journal implemented on `master`. BogKernel is i686 Multiboot1, QEMU
ATA PIO, serial-proof channel, verifier-first receipts.

**Target end state:** A narrow verified research OS that boots via GRUB (BIOS/UEFI)
from its own partition, runs verified `.bogapp` processes, provides a minimal shell,
maintains receipt chains without QEMU, and dual-boots safely alongside Linux/Windows.

**Not a goal:** General-purpose daily driver, POSIX compatibility, production
reliability, or replacing the Python/user-space BogOS stack.

## Guiding Principles (Non-Negotiable)

1. **Verifier-first:** Every major subsystem produces auditable receipts and
   supports negative-testing / invariant / Python-oracle validation.
2. **Dual-boot safety first:** Never risk the host OS. Separate partitions, safe
   mounting, clear recovery paths.
3. **Layered increment:** Keep BogKernel + BogVM + BogFS + receipt spine as the
   verified core; build compatibility layers around it.
4. **QEMU primary:** Real hardware is the target; QEMU remains primary dev and CI.
5. **Bounded interfaces:** Process isolation and cryptographic verification gates
   persist as functionality grows.
6. **Docs and harnesses are deliverables:** Safety procedures and test harnesses
   ship with every phase.

## Roadmap Contract

Each bare-metal phase follows the same contract as
[roadmap_v36_to_v40_tiny_os.md](roadmap_v36_to_v40_tiny_os.md):

- Implementation + phase plan doc + evaluator + negative matrix (where applicable)
  + JSON receipt + boundary flags.
- Positive-path output alone is not completion evidence.
- Receipt strictness follows the v41 bar: kernel-emitted serial markers required;
  no simulated fallback (unlike v40 evaluator tolerance).

Per-phase detail lives in `docs/baremetal_phase{N}_plan.md` (N = 0..9).

## Branch And Workstream Policy

See [adr/002-baremetal-branch-workstream.md](adr/002-baremetal-branch-workstream.md).

| Branch | Purpose |
| --- | --- |
| `master` | QEMU proof ladder (v42+ continues here) |
| `workstream/baremetal` | All bare-metal experiments until Phase 1 merge gate |

**Merge gate (Phase 1):** `evaluate_phase1_grub_boot.py` passes QEMU-via-GRUB and
at least one real-hardware serial log is captured in `artifacts/`.

Default kernel build on `master` must remain QEMU-identical until merge.

## Phase Overview

| Phase | Claim | Depends on |
| --- | --- | --- |
| 0 | Safe bare-metal infrastructure without changing QEMU proofs | v39, v41 model |
| 1 | GRUB chainload + boot receipt on real hardware | Phase 0 |
| 2 | AHCI storage + BogFS from real partition | Phase 1, v36–v38 |
| 3 | HAL: timer, IRQ, keyboard, display on real hardware | Phase 1 |
| 4 | Memory manager + demand paging foundation | Phase 1–2 |
| 5 | Init, shell, userspace syscall runtime | Phase 3–4, v33 ABI |
| 6 | FS maturity: nested dirs, genesis/journal on real disk | Phase 2, 5, v40/v41 |
| 7 | x86_64 port, networking, BogVM native | Phases 1–6 |
| 8 | Dual-boot install, recovery, distribution | Phases 1–7 (min 1+2+5) |
| 9 | Verification hardening, TPM path, formal invariants | All phases |

**Note:** Most 2020+ laptops require Phase 7 x86_64 for broad UEFI coverage.
i686 bare-metal proofs remain valid on BIOS and IA32 UEFI paths.

## Relationship To QEMU Milestones

| QEMU (`master`) | Bare-metal relationship |
| --- | --- |
| v41 journal | Phase 6 ports to real disk |
| v40 genesis | Phase 6 ports to real disk |
| v42+ `.bogapp` hardening | Phase 5 shell benefits; parallel |
| v42+ shell (deferred) | Superseded by Phase 5 bare-metal shell |

Bare-metal work does not block v42+ on `master` until Phase 1 merge.

## Cross-Cutting Workstreams

Active in every phase:

| Workstream | Activities |
| --- | --- |
| Testing | QEMU primary + periodic real hardware; negative cases; golden vectors |
| Documentation | ADRs, hardware matrix updates, per-phase plans |
| Build | Cross-compile, GRUB images, flashing tools |
| Safety | Dual-boot review at storage milestones (Phases 2, 6, 8) |
| Verification | Every feature answers how it preserves deterministic receipts |

**Evaluator naming:**

- `scripts/evaluate_phase{N}_*.py` — phase proofs
- `scripts/evaluate_baremetal_*.py` — cross-phase smoke tests
- JSON: `artifacts/baremetal_phase{N}_*_receipt.json`

## Global Success Criteria

| Criterion | Phase |
| --- | --- |
| GRUB boot + receipt chain on real laptop | 1, 8 |
| Persistent BogFS across reboots | 2, 6 |
| Interactive shell + keyboard + screen | 5 |
| Dual-boot safety on multiple machines | 0, 8 |
| All invariants hold on real hardware | 4, 6, 9 |
| Recognizably Bogbin (verifier-first) | 9 |

## Companion Documents

| Document | Purpose |
| --- | --- |
| [adr/001-qemu-assumption-audit.md](adr/001-qemu-assumption-audit.md) | QEMU/PC assumption registry |
| [adr/002-baremetal-branch-workstream.md](adr/002-baremetal-branch-workstream.md) | Branch isolation rules |
| [adr/003-platform-hal-extraction-strategy.md](adr/003-platform-hal-extraction-strategy.md) | HAL extraction from `main.rs` |
| [dual_boot_safety_checklist.md](dual_boot_safety_checklist.md) | Pre-install safety |
| [hardware_compatibility_matrix.md](hardware_compatibility_matrix.md) | Machine test status |
| [receipt_format_baremetal.md](receipt_format_baremetal.md) | Bare-metal receipt extensions |
| [baremetal_phase0_plan.md](baremetal_phase0_plan.md) … [baremetal_phase9_plan.md](baremetal_phase9_plan.md) | Per-phase contracts |

## QEMU Assumption Registry (Summary)

Full detail in ADR-001. Current hardcoded assumptions in
`kernel/bogk-kernel/src/main.rs`:

| Concern | Assumption | Phase to address |
| --- | --- | --- |
| Boot | QEMU `-kernel` direct load | 0–1 (GRUB) |
| Block | IDE ATA PIO @ `0x1F0`, 4 MiB image | 2 (AHCI trait) |
| Serial | COM1 @ `0x3F8` proof channel | 1, 3 (HAL) |
| Display | VGA text @ `0xB8000` | 3 (VESA option) |
| IRQ | 8259 PIC, vectors 32/33 | 3 (APIC) |
| Receipts | `PLATFORM=qemu`, `QEMU_ONLY=true` | 1+ (capability flags) |
| Evaluators | `qemu-system-i386 -kernel` | 0 (GRUB harness) |

Portable without change: `bogk-core` BogFS layouts, genesis/journal model,
SHA-256, process/scheduler models, syscall ABI validation logic.

## Phase Summaries

### Phase 0: Foundations

Goal: GRUB boot harness, QEMU audit, platform scaffold, safety docs.
Done when: GRUB ISO boots kernel in QEMU; v38–v41 evaluators unchanged on `master`.
Plan: [baremetal_phase0_plan.md](baremetal_phase0_plan.md)

### Phase 1: GRUB Bare-Metal Boot

Goal: Real-hardware chainload; `BOGBIN_PHASE1_BOOT` receipt. **Merge gate.**
Plan: [baremetal_phase1_plan.md](baremetal_phase1_plan.md)

### Phase 2: Real Storage

Goal: AHCI driver, partition parse, v38 persistence on test partition.
Plan: [baremetal_phase2_plan.md](baremetal_phase2_plan.md)

### Phase 3: HAL And Core Drivers

Goal: APIC/timer, PS/2 keyboard, VESA, ACPI stub.
Plan: [baremetal_phase3_plan.md](baremetal_phase3_plan.md)

### Phase 4: Memory Management

Goal: Full e820 map, buddy allocator, demand paging foundation.
Plan: [baremetal_phase4_plan.md](baremetal_phase4_plan.md)

### Phase 5: Userspace Foundation

Goal: Init, shell, `boglibc` syscall wrapper; deferred v40 shell work.
Plan: [baremetal_phase5_plan.md](baremetal_phase5_plan.md)

### Phase 6: Filesystem Maturity

Goal: Nested dirs, genesis/journal on real disk, host inspection tools.
Plan: [baremetal_phase6_plan.md](baremetal_phase6_plan.md)

### Phase 7: Advanced Features

Goal: x86_64 port, minimal networking, BogVM native, self-host bootstrap.
Plan: [baremetal_phase7_plan.md](baremetal_phase7_plan.md)

### Phase 8: Installation And Distribution

Goal: Safe dual-boot install, recovery media, versioned releases.
Plan: [baremetal_phase8_plan.md](baremetal_phase8_plan.md)

### Phase 9: Verification Hardening

Goal: End-to-end receipts without QEMU; TPM prototype; formal invariants.
Plan: [baremetal_phase9_plan.md](baremetal_phase9_plan.md)

## Quick Verification (Phase 0)

```bash
python3 scripts/audit_qemu_assumptions.py
python3 scripts/evaluate_phase0_grub_hello.py
scripts/check_baremetal_phase0.sh
```