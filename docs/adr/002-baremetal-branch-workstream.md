# ADR-002: Bare-Metal Branch Workstream

## Status

Accepted — Phase 0.

## Context

Bare-metal transition risks regressing the QEMU proof ladder (v16–v41) that
defines Bogbin's verified research substrate. QEMU milestones (v42+) continue on
`master` in parallel.

## Decision

All bare-metal experiments live on `workstream/baremetal` until Phase 1 merge gate
passes. Merge requires:

1. `scripts/evaluate_phase1_grub_boot.py` passes QEMU-via-GRUB
2. At least one real-hardware serial log in `artifacts/baremetal_phase1_<machine>.log`
3. All v38–v41 evaluators still pass on merged `master`

## Rules

### On `workstream/baremetal` (before merge)

| Allowed | Forbidden |
| --- | --- |
| New `platform/` directory and scripts | Changing QEMU evaluator pass criteria on `master` |
| `docs/baremetal_*`, `docs/adr/*` | Breaking default kernel build behavior |
| `#[cfg(feature = "baremetal")]` (feature default off) | Installing to host OS disk in automated tests |
| GRUB ISO/USB artifacts | Removing `QEMU_ONLY` receipts before Phase 1 proof |

### On `master` (always)

- v38–v41 evaluators must pass unchanged
- Default `cargo build -p bogk-kernel` produces QEMU-identical behavior
- v42+ development continues independently

### After Phase 1 merge

- `platform/` module and GRUB harness merge to `master`
- `baremetal` feature remains default-off until Phase 2+
- HAL changes require QEMU regression on every PR

## Merge Gate Checklist

- [ ] Phase 0 evaluator passes (`evaluate_phase0_grub_hello.py`)
- [ ] Phase 1 evaluator passes QEMU-via-GRUB
- [ ] Real hardware serial log captured and referenced in JSON receipt
- [ ] v38, v39, v40, v41 evaluators pass on merge candidate
- [ ] ADR-001 audit shows no undocumented assumptions
- [ ] Dual-boot safety checklist reviewed (USB boot only; no disk install)

## Consequences

- Documentation and Phase 0 tooling can land on `master` before branch creation.
- Kernel changes for bare-metal stay on `workstream/baremetal` until gate passes.
- Phase 2+ storage work requires dual-boot safety checklist sign-off per machine.