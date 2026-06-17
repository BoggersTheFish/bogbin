#!/usr/bin/env python3
"""Phase 0: boot BogKernel via GRUB ISO in QEMU; verify hello receipt."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS / "baremetal_phase0_grub_hello_receipt.json"
SERIAL_LOG = ARTIFACTS / "baremetal_phase0_grub_serial.log"
BIOS_ISO = ARTIFACTS / "bogbin_grub_bios.iso"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def build_grub_iso() -> int:
    script = ROOT / "scripts" / "make_grub_boot_image.py"
    result = run(["python3", str(script), "--bios-only"])
    if result.returncode != 0:
        print(result.stderr or result.stdout)
    return result.returncode


def parse_boot_markers(text: str) -> dict:
    fields = {}
    in_block = False
    for line in text.splitlines():
        if line.strip() == "BOGKERNEL_BOOT_BEGIN":
            in_block = True
            continue
        if line.strip() == "BOGKERNEL_BOOT_END":
            in_block = False
            continue
        if in_block and "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip()
    return fields


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    for tool in ("cargo", "qemu-system-i386", "python3"):
        if run(["which", tool]).returncode != 0:
            print(f"Error: {tool} not found")
            return 1

    print("Building GRUB BIOS ISO...")
    if build_grub_iso() != 0:
        return 1
    if not BIOS_ISO.exists():
        print(f"Error: missing {BIOS_ISO}")
        return 1

    kernel_path = (
        ROOT / "kernel" / "target" / "i686-unknown-linux-musl" / "debug" / "bogk-kernel"
    )

    if SERIAL_LOG.exists():
        SERIAL_LOG.unlink()

    print("Booting GRUB ISO in QEMU...")
    qemu_cmd = [
        "qemu-system-i386",
        "-cdrom",
        str(BIOS_ISO),
        "-serial",
        f"file:{SERIAL_LOG}",
        "-display",
        "none",
        "-no-reboot",
        "-m",
        "128",
    ]
    proc = subprocess.Popen(qemu_cmd)
    success = False
    output = ""
    deadline = time.time() + 45
    while time.time() < deadline:
        if SERIAL_LOG.exists():
            output = SERIAL_LOG.read_text(encoding="utf-8", errors="replace")
            if "BOGKERNEL_BOOT_END" in output:
                success = True
                break
        time.sleep(0.5)

    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()

    fields = parse_boot_markers(output)
    print("Serial output (tail):")
    print("\n".join(output.splitlines()[-30:]))

    receipt = {
        "format": "BOGBIN-baremetal-phase0-receipt-1.0",
        "execution_status": "completed" if success else "failed",
        "platform": fields.get("PLATFORM", "unknown"),
        "boot_path": "grub_multiboot1",
        "boot_firmware": "bios",
        "boot_loader": "grub2",
        "hardware_id": None,
        "verified_on_hardware": False,
        "boundary_flags": {
            "qemu_grub_chainload": True,
            "physical_hardware": False,
            "dual_boot_installed": False,
            "qemu_only_boundary": fields.get("PLATFORM") == "qemu",
        },
        "serial_markers_verified": success,
        "serial_fields": fields,
        "input_hashes": {
            "bogbin_grub_bios_iso": sha256_file(BIOS_ISO),
            "bogk_kernel_elf": sha256_file(kernel_path) if kernel_path.exists() else None,
        },
        "serial_log_hashes": {
            "grub_qemu_boot": sha256_bytes(output.encode("utf-8")) if output else None,
        },
        "manual_hardware_procedure": {
            "summary": "Write artifacts/bogbin_grub_bios.iso to USB; boot with serial capture.",
            "doc": "platform/README.md",
            "expected_markers": ["BOGKERNEL_BOOT_BEGIN", "BOGKERNEL_BOOT_END"],
        },
    }

    script_bytes = Path(__file__).read_bytes()
    receipt["evaluator_sha256"] = sha256_bytes(script_bytes)

    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")

    if not success:
        print("Error: BOGKERNEL_BOOT_END not found in serial log")
        return 1

    print("Phase 0 GRUB hello receipt PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())