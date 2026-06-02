# BOGBIN-0.1: Minimal Wave-State Binary

BOGBIN-0.1 is a deterministic binary instruction format for verifier-gated graph/wave-state computation.

## Memory Model

Dense:
- node_table
- edge_table
- claim_table
- receipt_ledger

Sparse:
- activation_current
- activation_scratch
- tension_current
- pressure fields

## VM Laws

LAW_001: No in-place wave mutation.
LAW_002: No ACCEPT without VERIFY.
LAW_003: No unordered iteration in consensus paths.
LAW_004: No floating-point arithmetic in consensus paths.
LAW_005: No unreceipted state transition.
LAW_006: Same .bogbin + same initial state must produce the same final receipt hash.
