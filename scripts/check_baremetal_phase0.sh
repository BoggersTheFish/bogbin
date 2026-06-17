#!/usr/bin/env bash
# Phase 0 local check: audit + GRUB hello evaluator.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== QEMU assumption audit =="
python3 scripts/audit_qemu_assumptions.py

echo "== Phase 0 GRUB hello evaluator =="
python3 scripts/evaluate_phase0_grub_hello.py

echo "== Phase 0 checks PASSED =="