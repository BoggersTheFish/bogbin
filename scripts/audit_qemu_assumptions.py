#!/usr/bin/env python3
"""Scan the repo for QEMU-specific assumptions; emit audit JSON."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
AUDIT_PATH = ARTIFACTS / "qemu_assumption_audit.json"
ADR_PATH = ROOT / "docs" / "adr" / "001-qemu-assumption-audit.md"

# Patterns aligned with ADR-001
PATTERNS = {
    "boot_qemu_kernel": {
        "pattern": r"qemu-system-i386.*-kernel",
        "category": "boot",
        "adr_id": "B01",
    },
    "multiboot_flags_zero": {
        "pattern": r"0x00000000,\s*// flags",
        "category": "boot",
        "adr_id": "B02",
        "paths": [ROOT / "kernel" / "bogk-kernel" / "src" / "main.rs"],
    },
    "ata_port_1f0": {
        "pattern": r"0x1[fF]0",
        "category": "storage",
        "adr_id": "S01",
    },
    "serial_port_3f8": {
        "pattern": r"0x3[fF]8",
        "category": "console",
        "adr_id": "C01",
    },
    "vga_b8000": {
        "pattern": r"0x[bB]8000",
        "category": "console",
        "adr_id": "C02",
    },
    "ps2_ports": {
        "pattern": r"0x6[04]",
        "category": "console",
        "adr_id": "C03",
    },
    "pic_ports": {
        "pattern": r"0x[12][0-9a-fA-F]0",
        "category": "irq",
        "adr_id": "I01",
    },
    "qemu_only_receipt": {
        "pattern": r"QEMU_ONLY=true",
        "category": "receipt",
        "adr_id": "R02",
    },
    "platform_qemu": {
        "pattern": r'PLATFORM=qemu|"platform":\s*"qemu"',
        "category": "receipt",
        "adr_id": "R01",
    },
    "ide_drive_arg": {
        "pattern": r"if=ide",
        "category": "storage",
        "adr_id": "S03",
    },
    "qemu_legacy_model": {
        "pattern": r"qemu_legacy_ide_ata_pio",
        "category": "storage",
        "adr_id": "R03",
    },
    "i686_musl_target": {
        "pattern": r"i686-unknown-linux-musl",
        "category": "build",
        "adr_id": "T01",
    },
}

SCAN_DIRS = [
    ROOT / "kernel",
    ROOT / "scripts",
]
SCAN_EXTENSIONS = {".rs", ".py", ".md", ".toml", ".ld"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan_file(path: Path, key: str, spec: dict) -> list[dict]:
    if spec.get("paths") and path not in spec["paths"]:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    regex = re.compile(spec["pattern"])
    hits = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if regex.search(line):
            hits.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "line": line_no,
                    "snippet": line.strip()[:120],
                }
            )
    return hits


def collect_matches() -> dict:
    results = {}
    for key, spec in PATTERNS.items():
        hits: list[dict] = []
        paths = spec.get("paths")
        if paths:
            files = [p for p in paths if p.exists()]
        else:
            files = []
            for base in SCAN_DIRS:
                if not base.exists():
                    continue
                for path in base.rglob("*"):
                    if path.suffix in SCAN_EXTENSIONS and path.is_file():
                        files.append(path)
        for path in files:
            hits.extend(scan_file(path, key, spec))
        results[key] = {
            "adr_id": spec["adr_id"],
            "category": spec["category"],
            "pattern": spec["pattern"],
            "match_count": len(hits),
            "matches": hits[:50],  # cap per pattern
        }
    return results


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    matches = collect_matches()
    total = sum(v["match_count"] for v in matches.values())

    adr_text = ADR_PATH.read_text(encoding="utf-8") if ADR_PATH.exists() else ""
    adr_ids = set(re.findall(r"\b([BSMCIRT]\d{2})\b", adr_text))
    found_ids = {v["adr_id"] for v in matches.values()}
    undocumented = sorted(found_ids - adr_ids)
    missing_in_repo = sorted(adr_ids - found_ids)

    audit = {
        "format": "BOGBIN-qemu-assumption-audit-1.0",
        "adr_path": str(ADR_PATH.relative_to(ROOT)),
        "adr_sha256": sha256_file(ADR_PATH) if ADR_PATH.exists() else None,
        "total_matches": total,
        "patterns": matches,
        "adr_coverage": {
            "adr_ids_in_doc": sorted(adr_ids),
            "adr_ids_with_matches": sorted(found_ids),
            "undocumented_match_ids": undocumented,
            "doc_ids_without_matches": missing_in_repo,
        },
        "drift_detected": bool(undocumented),
    }

    AUDIT_PATH.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {AUDIT_PATH}")
    print(f"Total matches: {total}")
    if undocumented:
        print(f"WARNING: undocumented ADR IDs with matches: {undocumented}")
        return 1
    print("ADR coverage OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())