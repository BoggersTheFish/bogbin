# BOGBIN v0.9

Minimal deterministic wave-state binary VM.

BOGBIN v0.7 adds automatic residual optimization: arbitrary bytes can be represented as deterministic generated base + exact residual patches, then verified by SHA-256 before acceptance.

BOGBIN v0.8 adds chunked automatic packing: larger inputs are split into deterministic fixed-size chunks, each chunk receives its own optimized basis/residual plan, and every chunk is verified by SHA-256 before acceptance.

BOGBIN v0.9 adds a deterministic `.bog` container compiler. A `.bog` file stores chunk plans, basis choices, residuals, hashes, and pack metadata as a storage/manifest container; it is not proof authority.

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

Container compile flow:

```bash
python3 -m bogvm pack examples/container_payload.bin artifacts/container_payload.bog --chunk-size 64 --receipt artifacts/container_payload_pack_receipt.json
python3 -m bogvm compile artifacts/container_payload.bog artifacts/container_payload.bogbin --bogasm artifacts/container_payload.bogasm
python3 -m bogvm run artifacts/container_payload.bogbin --receipt artifacts/container_payload_run_receipt.json
```

The `.bog` container is deterministic storage metadata only. The VM still proves chunk data through `VERIFY_HASH` + `ACCEPT_DATA` after the container is compiled to `.bogbin`.

Boundary:

- `.bog` container compiler only.
- `.bog` is a deterministic storage/manifest container.
- `.bog` is not proof authority.
- VM verification remains proof authority.
- Not a compression victory claim.
- Not Fourier yet.
- Not hardware execution.
- Exactness comes from the `VERIFY_HASH` + `ACCEPT_DATA` gate.
