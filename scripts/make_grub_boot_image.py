#!/usr/bin/env python3
"""Build GRUB boot ISOs (BIOS + UEFI IA32) for BogKernel Multiboot1 chainload."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
DEFAULT_KERNEL = (
    ROOT / "kernel" / "target" / "i686-unknown-linux-musl" / "debug" / "bogk-kernel"
)
DEFAULT_MB2_KERNEL = (
    ROOT / "kernel" / "target" / "i686-unknown-linux-musl" / "debug" / "bogk-mb2"
)
GRUB_BIOS_CFG = ROOT / "platform" / "grub" / "bios" / "grub.cfg"
GRUB_UEFI_CFG = ROOT / "platform" / "grub" / "uefi" / "grub.cfg"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def which(tool: str) -> str | None:
    return shutil.which(tool)


def build_kernel() -> Path:
    run(
        ["cargo", "build", "-p", "bogk-kernel", "--target", "i686-unknown-linux-musl"],
        cwd=ROOT / "kernel",
    )
    if not DEFAULT_KERNEL.exists():
        raise FileNotFoundError(f"kernel not found at {DEFAULT_KERNEL}")
    return DEFAULT_KERNEL


def stage_iso(
    *,
    work: Path,
    grub_cfg: Path,
    kernel: Path,
    label: str,
    mb2_kernel: Path | None = None,
) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    boot_dir = work / "boot" / "grub"
    boot_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(kernel, work / "boot" / "bogk-kernel")
    if mb2_kernel is not None and mb2_kernel.exists():
        shutil.copy2(mb2_kernel, work / "boot" / "bogk-mb2")
    shutil.copy2(grub_cfg, boot_dir / "grub.cfg")

    iso_path = ARTIFACTS / f"bogbin_grub_{label}.iso"
    if iso_path.exists():
        iso_path.unlink()

    run(
        [
            "grub-mkrescue",
            "-o",
            str(iso_path),
            str(work),
        ]
    )
    return iso_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kernel",
        type=Path,
        default=None,
        help="Path to bogk-kernel ELF (default: build debug musl target)",
    )
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--bios-only", action="store_true")
    parser.add_argument("--uefi-only", action="store_true")
    args = parser.parse_args()

    for tool in ("grub-mkrescue",):
        if which(tool) is None:
            print(
                f"Error: {tool} not found. Install grub tools per platform/README.md",
                file=sys.stderr,
            )
            return 1

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    kernel = args.kernel
    if kernel is None:
        if args.skip_build:
            kernel = DEFAULT_KERNEL
            if not kernel.exists():
                print("Error: --skip-build but kernel artifact missing", file=sys.stderr)
                return 1
        else:
            kernel = build_kernel()
    elif not kernel.exists():
        print(f"Error: kernel not found: {kernel}", file=sys.stderr)
        return 1

    mb2_kernel = DEFAULT_MB2_KERNEL
    if not mb2_kernel.exists():
        print(f"Warning: bogk-mb2 not found at {mb2_kernel} (MB2 menuentry will fail)", file=sys.stderr)

    outputs: list[Path] = []
    build_bios = not args.uefi_only
    build_uefi = not args.bios_only

    if build_bios:
        bios_work = ARTIFACTS / "grub_staging_bios"
        if bios_work.exists():
            shutil.rmtree(bios_work)
        outputs.append(
            stage_iso(work=bios_work, grub_cfg=GRUB_BIOS_CFG, kernel=kernel, label="bios")
        )

    if build_uefi:
        # IA32 UEFI — same kernel/grub.cfg; grub-mkrescue picks up EFI payloads when installed
        uefi_work = ARTIFACTS / "grub_staging_uefi"
        if uefi_work.exists():
            shutil.rmtree(uefi_work)
        outputs.append(
            stage_iso(
                work=uefi_work,
                grub_cfg=GRUB_UEFI_CFG,
                kernel=kernel,
                label="uefi",
                mb2_kernel=mb2_kernel,
            )
        )

    for path in outputs:
        print(f"Built {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())