# Bare-Metal Phase 8: Dual-Boot Safety, Installation & Distribution

## Claim And Dependency

Safe dual-boot installation alongside Linux/Windows with recovery media and
versioned releases. Depends on Phases 1–7 (minimum: 1+2+5 for basic install;
7 for broad hardware).

## Technical Scope

- Partition layout recommendations and guided setup script
- GRUB menuentry templates, os-prober notes
- Recovery USB/ISO: boot repair, BogFS inspect, genesis rollback
- Signed/receipted release artifacts under `artifacts/releases/`
- User docs: install, daily use, verification, troubleshooting

## Minimum Components

- `docs/installation_dual_boot.md`
- `scripts/create_bogbin_partition.sh`
- `scripts/make_recovery_image.py`
- `platform/grub/dual_boot_menuentry.cfg`
- `scripts/evaluate_phase8_install_smoke.py`

## Receipts

`BOGBIN_RELEASE_MANIFEST` with artifact hashes and version.

## Safety

Full [dual_boot_safety_checklist.md](dual_boot_safety_checklist.md) required.
Test matrix: 3+ laptops × Linux/Windows coexistence × multi-boot cycles.

## Explicit Non-Goals

Installer GUI, automatic partition resizing without user confirmation, Windows
bootloader replacement without GRUB coexistence plan.

## Done When

Clean install on 2+ dual-boot configs without host damage; recovery USB restores
menu; release verifiable from host Linux.