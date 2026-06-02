# BOGBIN v0.1

Minimal deterministic wave-state binary VM.

Core laws:

- Dense tables hold identity.
- Sparse fields hold live wave-state.
- No in-place wave mutation.
- No ACCEPT without VERIFY.
- No unordered iteration in consensus paths.
- No floating point arithmetic in consensus paths.
- Same .bogbin + same state = same receipt hash.
