# Bare-Metal Phase 9: Verification Hardening & Long-Term Evolution

## Claim And Dependency

End-to-end verifier-first properties on real hardware without QEMU dependency;
TPM prototype; formal invariant model; TS/graph long-term vision. Depends on all
prior phases and oracle framework (`gen_v40_workspace_vectors.py`).

## Technical Scope

- Receipt adaptation: disk-backed log on BogFS; remove QEMU-only serial assumptions
- TPM 2.0 measured boot prototype (optional path)
- Negative matrix for all Phase 2–8 subsystems
- Formal invariant document
- Unified bare-metal evaluator matrix
- Optional CI: `.github/workflows/baremetal-qemu.yml`

## Minimum Components

- `docs/verification_invariants_formal.md`
- `docs/ts_graph_native_vision.md`
- `docs/receipt_format_baremetal.md` (finalized)
- `platform/tpm/measured_boot.rs` (prototype or documented deferral ADR)
- `scripts/evaluate_baremetal_full_matrix.py`

## Receipts

`BOGBIN_VERIFICATION_SPINE_BEGIN/END` — cross-phase invariant attestation.

## Explicit Non-Goals

Mandatory TPM for all installs, formal verification tooling (Coq/Lean), Byzantine
consensus.

## Done When

Full receipt chain verifiable without QEMU; negative matrix complete; invariant
doc reviewed; TPM path documented (working or explicit deferral).