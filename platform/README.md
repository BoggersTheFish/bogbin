# Bogbin Platform Layer

Hardware abstraction and boot artifacts for the bare-metal transition.

**Status:** Phase 0 scaffold. Kernel integration begins in Phase 1 on
`workstream/baremetal`. See [docs/roadmap_baremetal_dual_boot.md](../docs/roadmap_baremetal_dual_boot.md).

## Layout

```
platform/
  README.md           — this file
  capabilities.rs     — capability types (reference stub; integrate Phase 1)
  grub/
    bios/grub.cfg     — Multiboot1 menuentry for BIOS ISO
    uefi/grub.cfg     — same for UEFI IA32 ISO
```

## Host Dependencies (Phase 0)

```bash
# Debian/Ubuntu
sudo apt install grub-pc-bin grub-efi-ia32-bin xorriso mtools

# Fedora
sudo dnf install grub2-efi-ia32 grub2-tools xorriso mtools
```

Also required: `cargo`, `qemu-system-i386`, `python3`.

## Build GRUB Images

```bash
python3 scripts/make_grub_boot_image.py
```

Outputs:

- `artifacts/bogbin_grub_bios.iso`
- `artifacts/bogbin_grub_uefi.iso`

## Run Phase 0 / Phase 1 Evaluators

```bash
python3 scripts/evaluate_phase0_grub_hello.py
python3 scripts/evaluate_phase1_grub_boot.py
scripts/check_baremetal_phase1.sh
```

## Phase 1 USB Images

```bash
./scripts/make_phase1_boot_usb.sh
# or: BOGBIN_FEATURES=baremetal ./scripts/make_phase1_boot_usb.sh
```

See [docs/grub_dual_boot_install.md](../docs/grub_dual_boot_install.md).

## Manual USB Boot (Phase 1)

1. Build images: `python3 scripts/make_grub_boot_image.py`
2. Write BIOS ISO to USB: `sudo dd if=artifacts/bogbin_grub_bios.iso of=/dev/sdX bs=4M status=progress`
3. Boot laptop from USB (BIOS or UEFI IA32 legacy mode)
4. Capture serial output (USB-serial on COM1 path or documented adapter)
5. Save log to `artifacts/baremetal_phase1_<machine>.log`

**Do not** write to internal disk until dual-boot checklist is complete.

## Integration Plan

See [docs/adr/003-platform-hal-extraction-strategy.md](../docs/adr/003-platform-hal-extraction-strategy.md).