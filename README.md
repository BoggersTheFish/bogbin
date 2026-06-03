# BOGBIN v0.7

Minimal deterministic wave-state binary VM.

BOGBIN v0.7 adds automatic residual optimization: arbitrary bytes can be represented as deterministic generated base + exact residual patches, then verified by SHA-256 before acceptance.

Core laws:

- Dense tables hold identity.
- Sparse fields hold live wave-state.
- No in-place wave mutation.
- No ACCEPT without VERIFY.
- No unordered iteration in consensus paths.
- No floating point arithmetic in consensus paths.
- Same .bogbin + same state = same receipt hash.

Automatic residual pack flow:

```bash
python3 -m bogvm pack examples/auto_pack_payload.bin artifacts/auto_pack_payload.bogbin --bogasm artifacts/auto_pack_payload.bogasm --receipt artifacts/auto_pack_payload_receipt.json
python3 -m bogvm run artifacts/auto_pack_payload.bogbin --receipt artifacts/auto_pack_payload_run_receipt.json
```

Boundary:

- Automatic residual optimization only.
- Not a compression victory claim.
- Not Fourier yet.
- Not a `.bog` container compiler yet.
- Exactness comes from the `VERIFY_HASH` + `ACCEPT_DATA` gate.
