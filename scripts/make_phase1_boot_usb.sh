#!/usr/bin/env bash
# Build GRUB USB-boot images for Phase 1 bare-metal testing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FEATURES="${BOGBIN_FEATURES:-baremetal}"

echo "== Building kernel (features: ${FEATURES:-default}, Multiboot1 header) =="
if [ -n "$FEATURES" ]; then
  (cd kernel && cargo build -p bogk-kernel --target i686-unknown-linux-musl --features "$FEATURES")
else
  (cd kernel && cargo build -p bogk-kernel --target i686-unknown-linux-musl)
fi

echo "== Building UEFI GRUB ISO (Multiboot1 + gfxpayload=keep) =="
python3 scripts/make_grub_boot_image.py --skip-build --uefi-only

echo ""
echo "Artifacts:"
ls -la artifacts/bogbin_grub_uefi.iso

echo ""
echo "USB write (DESTROYS target device — triple-check /dev/sdX):"
echo "  ./scripts/flash_boggerdrive.sh"
echo ""
echo "Real-hardware serial capture:"
echo "  # boot 'Bogbin Research Kernel (baremetal receipt)' menuentry"
echo "  # save serial log to artifacts/baremetal_phase1_<machine>.log"
echo ""
echo "For baremetal platform receipt without cmdline, rebuild with:"
echo "  BOGBIN_FEATURES=baremetal $0"