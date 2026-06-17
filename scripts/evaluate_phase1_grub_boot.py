#!/usr/bin/env python3
"""Phase 1: GRUB chainload boot with BOGBIN_PHASE1_BOOT receipt (QEMU + hardware slot)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
RECEIPT_PATH = ARTIFACTS / "baremetal_phase1_grub_boot_receipt.json"
SERIAL_LOG = ARTIFACTS / "baremetal_phase1_grub_qemu_serial.log"
BIOS_ISO = ARTIFACTS / "bogbin_grub_bios.iso"

REQUIRED_PHASE1_FIELDS = {
    "BOOT_PATH": "grub_multiboot1",
    "BOOT_LOADER": "grub2",
    "MEMORY_MAP_SOURCE": "multiboot",
    "EXECUTION_STATUS": "completed",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def parse_block(text: str, begin: str, end: str) -> dict[str, str]:
    """Parse receipt block; tolerant of GRUB ANSI escape noise on the same lines."""
    start = text.find(begin)
    end_idx = text.find(end)
    if start == -1 or end_idx == -1 or end_idx < start:
        return {}
    chunk = text[start : end_idx + len(end)]
    fields: dict[str, str] = {}
    for line in chunk.splitlines():
        for segment in line.replace("\r", "").split("\x1b"):
            segment = segment.strip()
            if "=" in segment and not segment.startswith("["):
                key, value = segment.split("=", 1)
                key = key.strip()
                if key.isascii() and key.replace("_", "").isalnum():
                    fields[key] = value.strip()
    return fields


def attach_hardware_logs() -> list[dict]:
    logs = sorted(ARTIFACTS.glob("baremetal_phase1_*.log"))
    logs = [p for p in logs if p.name != SERIAL_LOG.name]
    entries = []
    for path in logs:
        text = path.read_text(encoding="utf-8", errors="replace")
        fields = parse_block(text, "BOGBIN_PHASE1_BOOT_BEGIN", "BOGBIN_PHASE1_BOOT_END")
        entries.append(
            {
                "hardware_id": path.stem.replace("baremetal_phase1_", ""),
                "log_path": str(path.relative_to(ROOT)),
                "phase1_fields": fields,
                "serial_log_sha256": sha256_bytes(text.encode("utf-8")),
                "verified": "BOGBIN_PHASE1_BOOT_END" in text
                and fields.get("PLATFORM") == "baremetal",
            }
        )
    return entries


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    for tool in ("cargo", "qemu-system-i386", "python3"):
        if run(["which", tool]).returncode != 0:
            print(f"Error: {tool} not found")
            return 1

    print("Building GRUB BIOS ISO...")
    mk = run(["python3", str(ROOT / "scripts" / "make_grub_boot_image.py"), "--bios-only"])
    if mk.returncode != 0:
        print(mk.stderr or mk.stdout)
        return 1

    kernel_path = (
        ROOT / "kernel" / "target" / "i686-unknown-linux-musl" / "debug" / "bogk-kernel"
    )

    if SERIAL_LOG.exists():
        SERIAL_LOG.unlink()

    print("Booting GRUB ISO in QEMU...")
    proc = subprocess.Popen(
        [
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
    )

    output = ""
    success = False
    deadline = time.time() + 90
    while time.time() < deadline:
        if SERIAL_LOG.exists():
            output = SERIAL_LOG.read_text(encoding="utf-8", errors="replace")
            if "BOGBIN_PHASE1_BOOT_END" in output and "BOOT_PATH=" in output:
                success = True
                break
        time.sleep(0.5)

    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()

    phase1 = parse_block(output, "BOGBIN_PHASE1_BOOT_BEGIN", "BOGBIN_PHASE1_BOOT_END")
    v16 = parse_block(output, "BOGKERNEL_BOOT_BEGIN", "BOGKERNEL_BOOT_END")

    missing = [k for k, v in REQUIRED_PHASE1_FIELDS.items() if phase1.get(k) != v]
    if success and missing:
        print(f"Error: Phase 1 field mismatch: {missing}")
        print("Got:", phase1)
        success = False

    hardware_logs = attach_hardware_logs()
    hardware_verified = any(e["verified"] for e in hardware_logs)

    print("Phase 1 serial fields:", phase1)
    if missing:
        print("Missing/mismatched:", missing)

    receipt = {
        "format": "BOGBIN-baremetal-phase1-receipt-1.0",
        "execution_status": "completed" if success else "failed",
        "platform": phase1.get("PLATFORM", "unknown"),
        "boot_path": phase1.get("BOOT_PATH"),
        "boot_firmware": phase1.get("BOOT_FIRMWARE"),
        "boot_loader": phase1.get("BOOT_LOADER"),
        "early_console": phase1.get("EARLY_CONSOLE"),
        "memory_map_source": phase1.get("MEMORY_MAP_SOURCE"),
        "hardware_id": None,
        "verified_on_hardware": hardware_verified,
        "boundary_flags": {
            "qemu_grub_chainload": True,
            "physical_hardware": hardware_verified,
            "dual_boot_installed": False,
            "phase1_qemu_pass": success,
        },
        "serial_markers_verified": success,
        "phase1_fields": phase1,
        "v16_boot_fields": v16,
        "input_hashes": {
            "bogbin_grub_bios_iso": sha256_file(BIOS_ISO) if BIOS_ISO.exists() else None,
            "bogk_kernel_elf": sha256_file(kernel_path) if kernel_path.exists() else None,
        },
        "serial_log_hashes": {
            "grub_qemu_boot": sha256_bytes(output.encode("utf-8")) if output else None,
        },
        "hardware_logs": hardware_logs,
        "manual_hardware_procedure": {
            "summary": "Flash USB from make_phase1_boot_usb.sh; capture serial to artifacts/baremetal_phase1_<machine>.log",
            "doc": "docs/grub_dual_boot_install.md",
            "expected_markers": ["BOGBIN_PHASE1_BOOT_BEGIN", "BOGBIN_PHASE1_BOOT_END"],
            "expected_platform": "baremetal",
            "grub_menuentry": "Bogbin Research Kernel (baremetal receipt)",
        },
    }
    receipt["evaluator_sha256"] = sha256_bytes(Path(__file__).read_bytes())

    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"Receipt written to {RECEIPT_PATH}")

    if not success:
        print("Error: Phase 1 QEMU-via-GRUB proof failed")
        return 1

    if not hardware_verified:
        print("NOTE: No verified real-hardware log yet (expected before merge gate).")
        print("      Save serial capture to artifacts/baremetal_phase1_<machine>.log")

    print("Phase 1 GRUB boot proof PASSED (QEMU)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())