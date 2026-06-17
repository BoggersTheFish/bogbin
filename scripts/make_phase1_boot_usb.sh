#!/usr/bin/env bash
# Build GRUB USB-boot images for Phase 1 bare-metal testing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FEATURES="${BOGBIN_FEATURES:-baremetal}"

KERNEL_DIR="$ROOT/kernel/target/i686-unknown-linux-musl/debug"
MB1_ELF="$KERNEL_DIR/bogk-kernel"
MB2_ELF="$KERNEL_DIR/bogk-mb2"

echo "== Building bogk-kernel MB1 (features: ${FEATURES:-default}, flags 0x7 video) =="
if [ -n "$FEATURES" ]; then
  (cd kernel && cargo build -p bogk-kernel --target i686-unknown-linux-musl --features "$FEATURES")
else
  (cd kernel && cargo build -p bogk-kernel --target i686-unknown-linux-musl)
fi

echo "== Building bogk-mb2 (clean Multiboot2 header, separate image) =="
(cd kernel && cargo build -p bogk-mb2 --target i686-unknown-linux-musl)

if command -v grub-file >/dev/null 2>&1; then
  echo "== grub-file multiboot validation =="
  grub-file --is-x86-multiboot "$MB1_ELF"
  echo "bogk-kernel: grub-file --is-x86-multiboot => $?"
  grub-file --is-x86-multiboot2 "$MB2_ELF"
  echo "bogk-mb2: grub-file --is-x86-multiboot2 => $?"
else
  echo "warn: grub-file not found — skip header validation"
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