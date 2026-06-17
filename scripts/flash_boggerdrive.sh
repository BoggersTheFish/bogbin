#!/usr/bin/env bash
# Flash Bogbin GRUB ISO to BOGGERDRIVE (/dev/sda). Requires sudo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Prefer UEFI ISO on UEFI laptops (Acer Spin etc.); fall back to BIOS hybrid.
if [ -f "${ROOT}/artifacts/bogbin_grub_uefi.iso" ]; then
  ISO="${ROOT}/artifacts/bogbin_grub_uefi.iso"
else
  ISO="${ROOT}/artifacts/bogbin_grub_bios.iso"
fi
DEV="/dev/sda"

if [ ! -f "$ISO" ]; then
  echo "Missing $ISO — run ./scripts/make_phase1_boot_usb.sh first"
  exit 1
fi

echo "Target device:"
lsblk -o NAME,SIZE,MODEL,LABEL,MOUNTPOINTS "$DEV"
echo ""
echo "ISO: $ISO"
echo "WARNING: This erases ALL data on $DEV (BOGGERDRIVE)."
echo "System disk should be nvme0n1 — NOT $DEV."
read -r -p "Type YES to flash $ISO to $DEV: " confirm
if [ "$confirm" != "YES" ]; then
  echo "Aborted."
  exit 1
fi

udisksctl unmount -b "${DEV}1" 2>/dev/null || true
sudo umount "${DEV}"* 2>/dev/null || true

sudo dd if="$ISO" of="$DEV" bs=4M status=progress conv=fsync
sync
echo "Done. Safely remove USB and reboot into firmware boot menu (F12)."