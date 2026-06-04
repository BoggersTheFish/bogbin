# BOGBIN v1.5-dev

Minimal deterministic wave-state binary VM.

BOGBIN v0.7 adds automatic residual optimization: arbitrary bytes can be represented as deterministic generated base + exact residual patches, then verified by SHA-256 before acceptance.

BOGBIN v0.8 adds chunked automatic packing: larger inputs are split into deterministic fixed-size chunks, each chunk receives its own optimized basis/residual plan, and every chunk is verified by SHA-256 before acceptance.

BOGBIN v0.9 adds a deterministic `.bog` container compiler. A `.bog` file stores chunk plans, basis choices, residuals, hashes, and pack metadata as a storage/manifest container; it is not proof authority.

BOGBIN v1.0 adds exact deterministic file roundtrip: `input.bin -> output.bog -> output.bogbin -> verified VM run -> recovered.bin`, with matching SHA-256.

BOGBIN v1.1 adds a real-file roundtrip report harness over deterministic text, JSON, binary, image-like, and audio-like fixtures. It reports basis choices, residual density, chunk counts, hashes, and pass/fail status.

BOGBIN v1.2 adds deterministic `zero_block`, `delta_u8`, `dictionary_u8`, and `rle_u8` bases. The real-file report compares against the v1.1 baseline mean residual density of `0.867574`; the current report is `0.631188` with exact 5/5 roundtrip.

BOGBIN v1.3 adds deterministic adaptive chunk-size selection across chunk sizes `16`, `32`, `64`, and `128`. The current real-file report uses deterministic text, JSON, binary, valid PNG, and valid WAV payloads. It selects the best chunk size per file and improves mean residual density from the v1.2 baseline `0.631188` to `0.576098`, with exact 5/5 roundtrip.

BOGBIN v1.4.0 frames the next storage path around reversible transform selection plus exact verification hardening. In this release, verifier-rejected contradictions are repaired into deterministic rejected and quarantined claim state, residual optimizer plans are replay-checked before use, and the real-file report no longer relies on fake image/audio payloads.

BOGBIN v1.5-dev executes the first reversible transform tournament across chunk payloads before basis selection. Candidate transforms are `identity`, `xor_previous`, `delta_previous`, and `nibble_split`; selected transform metadata is stored per chunk, VM verification checks the transformed bytes, and container unpacking inverts the transform while checking original chunk and whole-payload SHA-256. It also adds a bounded integer-only `fourier8_u8` basis. The current transform-enabled report reduces mean residual density to `0.503575`, but `.bog` containers remain larger than the input files.

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

Exact roundtrip flow:

```bash
python3 -m bogvm pack examples/roundtrip_payload.bin artifacts/roundtrip_payload.bog --chunk-size 64 --receipt artifacts/roundtrip_payload_pack_receipt.json
python3 -m bogvm compile artifacts/roundtrip_payload.bog artifacts/roundtrip_payload.bogbin --bogasm artifacts/roundtrip_payload.bogasm
python3 -m bogvm run artifacts/roundtrip_payload.bogbin --receipt artifacts/roundtrip_payload_run_receipt.json
python3 -m bogvm unpack artifacts/roundtrip_payload.bog artifacts/roundtrip_payload_recovered.bin --receipt artifacts/roundtrip_payload_unpack_receipt.json
sha256sum examples/roundtrip_payload.bin artifacts/roundtrip_payload_recovered.bin
```

Real-file report flow:

```bash
python3 scripts/evaluate_real_file_roundtrip.py
```

The report is written to `artifacts/real_file_roundtrip_report.json`, with an audit receipt at `artifacts/real_file_roundtrip_receipt.json`.

Boundary:

- Adaptive deterministic chunk-size and reversible transform tournaments.
- Adds residual-density comparison against v1.2.
- `.bog` is a deterministic storage/manifest container.
- `.bog` is not proof authority.
- VM verification remains proof authority.
- Not a compression victory claim.
- Not a claim that `.bog` beats existing formats.
- First bounded integer-only Fourier-style basis only; no broad Fourier compressor claim.
- Not hardware execution.
- Exactness comes from the `VERIFY_HASH` + `ACCEPT_DATA` gate.
