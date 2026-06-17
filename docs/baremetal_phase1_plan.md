# Bare-Metal Phase 1: Bootloader Integration & Initial Bare-Metal Boot

## Claim And Dependency

BogKernel chainloads via GRUB (Multiboot1) on real hardware (BIOS and UEFI) and
emits `BOGBIN_PHASE1_BOOT` receipt. Depends on Phase 0 GRUB harness.

**This phase is the merge gate to `master`.**

Implementation status: QEMU-via-GRUB proof complete (`evaluate_phase1_grub_boot.py`);
real-hardware USB boot log pending at `artifacts/baremetal_phase1_<machine>.log`.

## Technical Scope

- Multiboot header flags: memory map + cmdline
- `platform/boot/multiboot.rs` extracted from `main.rs`
- `baremetal` Cargo feature (default off)
- Early serial + VGA on real hardware
- GRUB templates for BIOS and UEFI
- USB boot testing on 1+ real machines

## Minimum Components

- `scripts/evaluate_phase1_grub_boot.py`
- `scripts/make_phase1_boot_usb.sh`
- `docs/grub_dual_boot_install.md` (USB-only; no disk install)
- `#[cfg(feature = "baremetal")]` platform paths

## Receipts

```text
BOGBIN_PHASE1_BOOT_BEGIN
PLATFORM=baremetal
BOOT_FIRMWARE=bios|uefi
BOOT_LOADER=grub2
BOOT_PATH=grub_multiboot1
EARLY_CONSOLE=serial|vga|both
MEMORY_MAP_SOURCE=multiboot
BOGBIN_PHASE1_BOOT_END
```

Artifacts: `artifacts/baremetal_phase1_<machine>.log`,
`artifacts/baremetal_phase1_grub_boot_receipt.json`

## Explicit Non-Goals

Disk installation, storage driver, full HAL, userspace.

## Done When

Evaluator passes QEMU-via-GRUB and 1+ real hardware serial log captured;
v38–v41 evaluators pass on merge candidate.