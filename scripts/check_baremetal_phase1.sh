#!/usr/bin/env bash
# Phase 1 local check: GRUB boot receipt + v16 direct-boot regression.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== v16 direct QEMU -kernel (regression) =="
python3 scripts/evaluate_bogkernel_boot.py

echo "== Phase 1 GRUB chainload evaluator =="
python3 scripts/evaluate_phase1_grub_boot.py

echo "== Phase 1 checks PASSED (QEMU) =="
echo "Hardware merge gate: capture artifacts/baremetal_phase1_<machine>.log"