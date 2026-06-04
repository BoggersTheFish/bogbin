# BOGBIN v0.2-v0.6 Audit Against BOGBIN-0.1

Scope: docs_v0_2_plan.md through docs_v0_6_plan.md, checked against spec/BOGBIN_0_1.md and the current VM/container state.

## Spec Alignment

- LAW_001, no in-place wave mutation: propagation uses snapshot/frontier state, and generative data synthesis writes byte blocks only after deterministic basis evaluation.
- LAW_002, no ACCEPT without VERIFY: claim and data acceptance remain gated. Rejected claim acceptance is now repaired into deterministic reject plus quarantine state; unverified or abstained acceptance still blocks.
- LAW_003, no unordered iteration in consensus paths: graph propagation and receipt-visible accepted/rejected/quarantined lists are sorted before use.
- LAW_004, no floating-point arithmetic in consensus paths: current bases use integer byte arithmetic and fixed lookup tables.
- LAW_005, no unreceipted state transition: VM state changes are logged through receipt events, including blocked execution and contradiction repair.
- LAW_006, deterministic final receipt hash: tests cover repeat execution of the same assembled proof chain producing the same receipt hash.

## Staged Plan Status

- v0.2 generative storage opcodes: implemented by DECLARE_BASIS, LOAD_COEFFICIENTS, SYNTHESIZE, STORE_RESIDUAL, APPLY_RESIDUAL, VERIFY_HASH, and ACCEPT_DATA.
- v0.3 integer ramp basis: implemented as ramp_u8 and generalized through delta_u8.
- v0.4 triangle integer wave basis: implemented as triangle_u8 with fixed integer offsets.
- v0.5 sine lookup basis: implemented as sine8_u8 with fixed integer offsets and no runtime trigonometry.
- v0.6 residual patching: implemented through residual storage/application plus hash-gated acceptance.

## Current Hardening

- Contradictions with verifier result `rejected` are repaired into rejected and quarantined claim state instead of only failing at ACCEPT.
- Residual optimizer output is self-checked by replaying generator plus patches and comparing SHA-256 before returning a plan.
- Real-file roundtrip fixtures now include valid deterministic PNG and WAV payloads instead of PNG-like and WAV-like mock bytes.

## Remaining Boundary

The VM has moved beyond the original 0.1 document in implementation labels and container behavior, with BOG-1.3/BOGBIN-1.3 chunked containers and adaptive chunk selection. The 0.1 law set is still the compatibility floor for verifier-gated execution.
