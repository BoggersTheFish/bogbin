# BOGBIN v1.5 Next Architecture

## Implemented in v1.5 Development

- Reversible transform tournament before basis selection.
- Per-chunk transform metadata in `.bog` containers.
- VM verification of transformed chunk bytes.
- Container reconstruction that inverts transforms and verifies original chunk and whole-payload SHA-256.
- Bounded integer-only `fourier8_u8` basis.
- Compression-threshold reporting through container/input size ratios.

## Current Measurements

- Exact roundtrip remains 5/5.
- Mean residual density is `0.469867`.
- JSON `.bog` compression threshold was not crossed: JSON containers remained larger than source inputs.
- Mean JSON `.bog` container-to-input ratio was `38.548519`.
- Sorting transforms plus bitmask residual packing reduce mean `.bogpk` container-to-input ratio to `0.960163`.
- Aggregate compression threshold is crossed; per-file threshold is not crossed for every fixture.

## Current Outliers

The aggregate `.bogpk` result is smaller than aggregate input size, but three individual fixtures remain above threshold:

| Fixture | Type | Input bytes | BOGPK bytes | Ratio | Smaller | Residual density |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| `text_payload` | text | 124 | 172 | 1.387097 | false | 0.653226 |
| `json_payload` | json | 127 | 187 | 1.472441 | false | 0.748031 |
| `png_payload` | png | 268 | 332 | 1.238806 | false | 0.686567 |
| `binary_noise_like_payload` | binary | 160 | 53 | 0.33125 | true | 0.0 |
| `wav_payload` | wav | 300 | 196 | 0.653333 | true | 0.333333 |

Boundary reading:

- The text and JSON fixtures are small enough that descriptor and residual overhead still dominate.
- The PNG fixture still carries high residual density after sorting transforms.
- The binary-noise-like fixture is actually an arithmetic byte sequence and maps cleanly to `delta_u8`.
- The WAV fixture benefits from sorting/MTF paths enough to cross the per-file threshold.

Next pressure point: reduce residual payload cost for small text/JSON chunks and introduce dictionary/string-oriented bases before adding more broad transforms.

## Binary Container Packing Plan

The current `.bog` container is transparent JSON. That is useful for audit, but it is the main reason the JSON path did not cross the compression threshold. Container generation now splits human-readable receipts from compact reconstruction blueprints through `.bogpk`.

Target format: `BOGPK1`

Header:

- Magic: 6 bytes, `BOGPK1`.
- Version: 1 byte.
- Flags: 1 byte.
- Chunk size code: 2 bits for `16`, `32`, `64`, `128`.
- Chunk count: varint.
- Total residual count: varint.
- Whole SHA-256: 32 bytes.

Per-chunk descriptor stream:

- Transform ID: 3 bits for `identity`, `xor_previous`, `delta_previous`, `nibble_split`, `mtf`, `bwt`, and `bwt_mtf`.
- Basis ID: 4 bits for current deterministic basis order.
- Start byte: 8 bits.
- Delta byte: 8 bits.
- Length override: omitted for full chunks; varint only for final short chunk.
- Transformed chunk SHA-256: optional by flag; omit when a Merkle root or whole transformed stream hash is used.
- Original chunk SHA-256: optional by flag; omit when whole SHA-256 plus deterministic chunk order is sufficient for the trust boundary.

Residual stream:

- Residual count per chunk: varint, or run-length encoded when adjacent chunks share count `0`.
- Residual offsets: delta-coded varints from previous offset.
- Residual bytes: raw byte stream.
- Zero-residual chunk runs: RLE pair `(run_length, descriptor_reference)`.

Expected immediate impact:

- Remove JSON key names, decimal strings, repeated chunk names, repeated offsets, and repeated lengths.
- Preserve deterministic reconstruction and SHA-256 verification.
- Keep the JSON `.bog` format available as an audit/debug representation, but stop treating it as the compression target.

Non-goals for the next step:

- No entropy coder yet.
- No claim that packed `.bog` beats existing file formats.
- No removal of receipts; receipts move to a separate audit artifact.

## Bare-Metal Direction

The Python VM remains the proof harness. A TS-BIOS path should begin as an interface contract before implementation:

- Define binary receipt layout independent of Python JSON.
- Define a fixed instruction decoding ABI.
- Define deterministic memory regions for dense tables, sparse fields, data blocks, and receipts.
- Preserve `LAW_004`: no floating-point arithmetic in consensus paths.
- Preserve hash-gated acceptance for claims and data.

## Software VM to Signal Bridge

The current `.bogbin` stream can be mapped toward bare-metal execution as a deterministic signal schedule:

- Instruction word: fixed-width opcode plus operand lanes, decoded without dynamic allocation.
- Basis signal: basis ID selects a deterministic integer waveform generator.
- Transform signal: transform ID selects a reversible pre/post-processing circuit.
- Coefficient lane: start byte, delta byte, and length feed the generator.
- Residual lane: offset and byte streams patch generated bytes into exact transformed chunks.
- Verifier lane: SHA-256 unit or firmware routine compares transformed chunk hash before data acceptance.
- Receipt lane: accepted/rejected/quarantined transitions append fixed binary receipt records.

The `.bogpk` stream can act as the compact pre-VM blueprint:

- Header signal: establishes chunk size, chunk count, total residual count, and whole SHA-256.
- Descriptor signal: emits transform ID, basis ID, start byte, delta byte, and optional BWT primary index.
- Residual signal: emits either delta-coded residual offsets or bitmask residual lanes.
- Reconstruction signal: synthesizes transformed chunks, applies residuals, inverts transforms, and exposes original bytes to verifier memory.
- Verification signal: hashes reconstructed bytes and gates acceptance before receipt emission.

The bare-metal bridge should first target an emulator with fixed memory maps:

- Dense table region.
- Sparse activation/tension region.
- Data block synthesis region.
- Residual patch stream region.
- Receipt ledger region.

Only after the emulator proves identical receipt hashes to Python should the work move to BIOS or hardware-adjacent execution.

No hardware execution, BIOS boot path, or laptop port is implemented in this phase.

## Boundary

- Not a compression victory claim.
- Not a claim that `.bog` beats existing formats.
- Not a full Fourier compressor.
- Not bare-metal execution yet.
