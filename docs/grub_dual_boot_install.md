# GRUB USB Boot Guide (Phase 1)

Phase 1 proves GRUB → Multiboot1 → BogKernel chainloading. **No host disk
installation** — USB boot only.

See [dual_boot_safety_checklist.md](dual_boot_safety_checklist.md) before any
disk-based work (Phase 2+).

## Build Boot Media

```bash
# Default (QEMU + USB; use baremetal GRUB menuentry for hardware receipt)
./scripts/make_phase1_boot_usb.sh

# Or force PLATFORM=baremetal in kernel build
BOGBIN_FEATURES=baremetal ./scripts/make_phase1_boot_usb.sh
```

Outputs:

- `artifacts/bogbin_grub_bios.iso` — legacy BIOS / CSM
- `artifacts/bogbin_grub_uefi.iso` — UEFI IA32 (i686 kernel)

## Write USB (BIOS)

Replace `/dev/sdX` with your USB device (not a system disk):

```bash
sudo dd if=artifacts/bogbin_grub_bios.iso of=/dev/sdX bs=4M status=progress conv=fsync
sync
```

## Boot Laptop

1. Insert USB, enter firmware boot menu (F12/F2/Esc varies by vendor)
2. Select USB — **BIOS legacy** or **UEFI IA32** matching your ISO
3. Choose **Bogbin Research Kernel (baremetal receipt)** for hardware proof
   - Passes `platform=baremetal firmware=bios|uefi` via Multiboot cmdline
4. Capture serial output (USB-serial adapter on COM1, or firmware UART if exposed)

## Save Hardware Receipt

Save the full serial log:

```bash
cp /path/to/captured.log artifacts/baremetal_phase1_<machine-id>.log
```

Re-run evaluator to attach hardware evidence:

```bash
python3 scripts/evaluate_phase1_grub_boot.py
```

Merge gate requires `PLATFORM=baremetal` in the hardware log's Phase 1 block.

## Expected Serial Markers

```text
BOGBIN_PHASE1_BOOT_BEGIN
PLATFORM=baremetal
BOOT_FIRMWARE=bios|uefi
BOOT_LOADER=grub2
BOOT_PATH=grub_multiboot1
EARLY_CONSOLE=both
MEMORY_MAP_SOURCE=multiboot
EXECUTION_STATUS=completed
BOGBIN_PHASE1_BOOT_END
```

## QEMU Regression

```bash
python3 scripts/evaluate_phase1_grub_boot.py
python3 scripts/evaluate_phase0_grub_hello.py
python3 scripts/evaluate_bogkernel_boot.py
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Black screen, no serial | Try BIOS ISO vs UEFI ISO; enable legacy boot |
| GRUB loads, kernel silent | Serial baud 115200 on COM1; try serial debug menuentry |
| `MEMORY_MAP_SOURCE=none` | GRUB too old or non-Multiboot path; verify `multiboot` command in grub.cfg |
| `BOOT_PATH=qemu_direct` | Booted via QEMU `-kernel`, not GRUB ISO |

## Next Phase

Phase 2 adds AHCI storage on an isolated test partition — still not host root disk
until Phase 8 install guide.