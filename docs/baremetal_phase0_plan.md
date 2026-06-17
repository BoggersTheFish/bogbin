# Bare-Metal Phase 0: Foundations, Tooling & Bare-Metal Readiness

## Claim And Dependency

Establish safe bare-metal infrastructure (GRUB harness, QEMU audit, platform
scaffold, safety docs) without changing QEMU proof pass criteria on `master`.
Depends on v39 release ladder and v41 journal model in `bogk-core`.

Implementation status: in progress.

## Technical Scope

- QEMU assumption audit (ADR-001) with automated drift detection
- `platform/` directory: GRUB configs, capability types (reference stub)
- GRUB ISO builder (BIOS + UEFI IA32)
- Phase 0 evaluator: boot kernel via GRUB-in-QEMU
- Dual-boot safety checklist and hardware compatibility matrix template
- Bare-metal receipt format draft

No kernel modifications. No real-hardware proof required.

## Minimum Components

- `scripts/audit_qemu_assumptions.py`
- `scripts/make_grub_boot_image.py`
- `scripts/evaluate_phase0_grub_hello.py`
- `scripts/check_baremetal_phase0.sh`
- `platform/README.md`, `platform/grub/bios/grub.cfg`, `platform/grub/uefi/grub.cfg`
- `platform/capabilities.rs` (reference stub)
- ADRs 001–003, safety/receipt docs

## Receipts And Artifacts

Serial: v16 `BOGKERNEL_BOOT_*` with optional `BOOT_PATH=grub_multiboot1`.

JSON: `artifacts/baremetal_phase0_grub_hello_receipt.json`

Audit: `artifacts/qemu_assumption_audit.json`

ISO: `artifacts/bogbin_grub_bios.iso`, `artifacts/bogbin_grub_uefi.iso`

## Verification

```bash
python3 scripts/audit_qemu_assumptions.py
python3 scripts/evaluate_phase0_grub_hello.py
scripts/check_baremetal_phase0.sh
```

## Explicit Non-Goals

Kernel changes, AHCI, real-hardware boot proof, dual-boot disk installation.

## Done When

GRUB ISO boots kernel in QEMU; audit JSON matches ADR-001; v38–v41 evaluators
unchanged on `master`; manual USB boot procedure documented for Phase 1.