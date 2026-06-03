# BOGBIN v0.8

Minimal deterministic wave-state binary VM.

BOGBIN v0.7 adds automatic residual optimization: arbitrary bytes can be represented as deterministic generated base + exact residual patches, then verified by SHA-256 before acceptance.

BOGBIN v0.8 adds chunked automatic packing: larger inputs are split into deterministic fixed-size chunks, each chunk receives its own optimized basis/residual plan, and every chunk is verified by SHA-256 before acceptance.

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

Chunked pack flow:

```bash
python3 -m bogvm pack examples/chunked_payload.bin artifacts/chunked_payload.bogbin --chunk-size 64 --bogasm artifacts/chunked_payload.bogasm --receipt artifacts/chunked_payload_receipt.json
python3 -m bogvm run artifacts/chunked_payload.bogbin --receipt artifacts/chunked_payload_run_receipt.json
```

The VM verifies and accepts each chunk as its own data block. v0.8 does not add a whole-payload VM opcode; the pack receipt includes deterministic `chunk_count`, `chunk_size`, `total_residual_count`, and `whole_sha256` fields for whole-payload audit.

Boundary:

- Chunked deterministic auto-pack only.
- Not a compression victory claim.
- Not Fourier yet.
- Not a `.bog` container compiler yet.
- Not hardware execution.
- Exactness comes from the `VERIFY_HASH` + `ACCEPT_DATA` gate.
