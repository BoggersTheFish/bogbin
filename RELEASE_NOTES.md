# BOGBIN / BOGVM Release Notes

## v1.3.1: Contradiction and Residual Hardening

v1.3.1 hardens the current v1.3 execution path and updates the real-file report to use valid deterministic image/audio payloads.

Proof:

- Verifier-rejected claim acceptance is repaired into deterministic rejected and quarantined claim state.
- Unverified or abstained claim acceptance remains blocked by `LAW_002`.
- Residual optimizer output is replay-checked before use: basis synthesis plus residual patches must reconstruct the target SHA-256 exactly.
- The real-file report now evaluates deterministic text, JSON, binary, valid PNG, and valid WAV payloads.
- The staged v0.2-v0.6 audit is documented against the BOGBIN-0.1 VM laws.

Report:

- v1.2 mean residual density: `0.631188`
- Current mean residual density: `0.576098`
- Residual density delta from v1.2: `-0.05509`
- Residual density improved from v1.2: `true`
- Exact roundtrip: 5/5

Verification:

~~~bash
python3 -m unittest discover -s tests
python3 scripts/evaluate_real_file_roundtrip.py
~~~

Boundary:

- Contradiction repair only applies after verifier result `rejected`.
- Unverified acceptance remains blocked.
- Valid PNG/WAV fixtures are deterministic small fixtures, not compression benchmarks.
- Exactness remains verified through BOGVM and SHA-256 checks.

## v1.3.0: Adaptive Chunk Tournament

v1.3.0 adds deterministic adaptive chunk-size selection.

Proof:

- Container packing can evaluate chunk sizes `16`, `32`, `64`, and `128`.
- Candidate plans are scored by total residual count, residual density, chunk count, then chunk size.
- `.bog` metadata records whether the tournament was enabled, candidate chunk sizes, selected chunk size, selected residual count, selected density, and per-candidate results.
- `python3 -m bogvm pack input.bin output.bog --auto-chunk --receipt ...` enables the tournament.
- Explicit `--chunk-size` behavior is preserved.
- Exact roundtrip remains 5/5 on the real-file report.

Report:

- v1.2 mean residual density: `0.631188`
- Current mean residual density: `0.555693`
- Residual density delta from v1.2: `-0.075495`
- Residual density improved from v1.2: `true`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 scripts/evaluate_real_file_roundtrip.py
~~~

Boundary:

- Adaptive deterministic chunk-size tournament only.
- Not a compression benchmark victory.
- Not a claim that `.bog` beats ZIP/PNG/WAV/etc.
- Not Fourier.
- Not hardware execution.
- Exactness remains verified through BOGVM and SHA-256 checks.

## v1.2.0: Dictionary + Delta Bases

v1.2.0 adds deterministic bases to reduce residual density on the real-file roundtrip report.

Proof:

- `zero_block` generates all-zero chunks.
- `delta_u8` generates arithmetic byte sequences with `byte[i] = (start_byte + i * delta) mod 256`.
- The optimizer searches delta values `0..255` deterministically and chooses the best start byte for each delta.
- `dictionary_u8` and `rle_u8` are deterministic one-byte base generators for this release; exactness still comes from residual patches and SHA-256 verification.
- Tie-breaking remains residual count, basis order, then coefficient tuple.
- Exact roundtrip remains 5/5 on the real-file report.

Report:

- Baseline mean residual density: `0.867574`
- Current mean residual density: `0.631188`
- Residual density delta: `-0.236386`
- Residual density improved: `true`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 scripts/evaluate_real_file_roundtrip.py
~~~

Boundary:

- Adds deterministic bases and residual-density comparison.
- Not a compression benchmark victory.
- Not a claim that `.bog` beats ZIP/PNG/WAV/etc.
- Not Fourier.
- Not hardware execution.
- Exactness remains verified through BOGVM and SHA-256 checks.

## v1.1.0: Basis Tournament + Real File Report

v1.1.0 adds a deterministic real-file evaluation/report harness.

Proof:

- `scripts/evaluate_real_file_roundtrip.py` builds deterministic fixture files for text, JSON, binary/noise-like, PNG-like, and WAV-like payloads.
- Each case is packed to `.bog`, compiled to `.bogbin`, verified through BOGVM, unpacked, and SHA-256 compared against the original.
- The report records basis counts, residual density, chunk counts, hashes, VM run status, and roundtrip pass/fail.
- Every accepted case must recover exact bytes.

Artifacts:

- `artifacts/real_file_roundtrip_report.json`
- `artifacts/real_file_roundtrip_receipt.json`
- `docs/real_file_roundtrip_report.md`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 scripts/evaluate_real_file_roundtrip.py
~~~

Boundary:

- Real-file roundtrip report only.
- Not a compression benchmark victory.
- Not a claim that `.bog` beats existing formats.
- Not Fourier.
- Not hardware execution.
- Exactness remains verified through BOGVM and SHA-256 checks.

## v1.0.0: Exact File Roundtrip

v1.0.0 adds exact deterministic file reconstruction.

Proof:

- `reconstruct_bog_container_bytes(container)` reconstructs every chunk from basis, start byte, length, and residual patches.
- Reconstruction verifies each `chunk_sha256`.
- Reconstructed chunks are concatenated in deterministic index order.
- The final byte stream is checked against `whole_sha256`.
- `python3 -m bogvm unpack` writes recovered bytes and an unpack receipt.
- A file can complete: `input.bin -> output.bog -> output.bogbin -> verified VM run -> recovered.bin`.

Artifacts:

- `examples/roundtrip_payload.bin`
- `artifacts/roundtrip_payload.bog`
- `artifacts/roundtrip_payload.bogasm`
- `artifacts/roundtrip_payload.bogbin`
- `artifacts/roundtrip_payload_pack_receipt.json`
- `artifacts/roundtrip_payload_run_receipt.json`
- `artifacts/roundtrip_payload_unpack_receipt.json`
- `artifacts/roundtrip_payload_recovered.bin`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm pack examples/roundtrip_payload.bin artifacts/roundtrip_payload.bog --chunk-size 64 --receipt artifacts/roundtrip_payload_pack_receipt.json
python3 -m bogvm compile artifacts/roundtrip_payload.bog artifacts/roundtrip_payload.bogbin --bogasm artifacts/roundtrip_payload.bogasm
python3 -m bogvm run artifacts/roundtrip_payload.bogbin --receipt artifacts/roundtrip_payload_run_receipt.json
python3 -m bogvm unpack artifacts/roundtrip_payload.bog artifacts/roundtrip_payload_recovered.bin --receipt artifacts/roundtrip_payload_unpack_receipt.json
sha256sum examples/roundtrip_payload.bin artifacts/roundtrip_payload_recovered.bin
~~~

Boundary:

- Exact deterministic file roundtrip.
- Not compression victory.
- Not Fourier.
- Not hardware execution.
- VM verification remains proof authority.

## v0.9.0: .bog Container Compiler

v0.9.0 adds a deterministic `.bog` container format and compiler.

Proof:

- `build_bog_container(data, chunk_size=64)` creates a deterministic `BOG-0.9` JSON-compatible container.
- The container stores chunk names, offsets, lengths, basis choices, start bytes, residuals, per-chunk SHA-256 hashes, total residual count, and whole-file SHA-256.
- `write_bog_container()` writes canonical JSON with sorted keys and stable separators.
- `read_bog_container()` validates required fields and schema constraints.
- `compile_bog_container_to_bogasm()` deterministically compiles container plans into ordinary `.bogasm`.
- `python3 -m bogvm compile` assembles that `.bogasm` into `.bogbin`.
- Running the compiled `.bogbin` verifies and accepts each chunk through VM `VERIFY_HASH` + `ACCEPT_DATA`.

Artifacts:

- `examples/container_payload.bin`
- `artifacts/container_payload.bog`
- `artifacts/container_payload.bogasm`
- `artifacts/container_payload.bogbin`
- `artifacts/container_payload_pack_receipt.json`
- `artifacts/container_payload_run_receipt.json`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm pack examples/container_payload.bin artifacts/container_payload.bog --chunk-size 64 --receipt artifacts/container_payload_pack_receipt.json
python3 -m bogvm compile artifacts/container_payload.bog artifacts/container_payload.bogbin --bogasm artifacts/container_payload.bogasm
python3 -m bogvm run artifacts/container_payload.bogbin --receipt artifacts/container_payload_run_receipt.json
~~~

Boundary:

- `.bog` container compiler only.
- `.bog` is a deterministic storage/manifest container.
- `.bog` is not proof authority.
- VM verification remains proof authority.
- Not compression victory.
- Not Fourier.
- Not hardware execution.

## v0.8.0: Chunked Auto Pack

v0.8.0 adds deterministic chunked automatic packing.

Proof:

- `optimize_chunked_residual_plan(data, chunk_size=64)` splits input bytes into sequential chunks.
- Each chunk is optimized independently with the existing residual optimizer and deterministic tie-breaking.
- `pack_chunked_bytes_to_bogasm()` emits one data block per chunk: `payload_chunk_0000`, `payload_chunk_0001`, and so on.
- Every chunk is synthesized, residual-patched, `VERIFY_HASH` checked, and `ACCEPT_DATA` accepted independently by the VM.
- `python3 -m bogvm pack` defaults to chunked mode when input length is greater than `--chunk-size`.
- `--single-block` preserves the v0.7 one-block `payload` behavior.
- The pack receipt includes deterministic `chunk_count`, `chunk_size`, `total_residual_count`, and `whole_sha256`.

Whole-payload boundary:

- v0.8 does not add a whole-payload VM opcode.
- The VM verifies chunks.
- The pack receipt records the whole input SHA-256 deterministically as `whole_sha256`.
- The verifier boundary remains authoritative for accepted chunk data through `VERIFY_HASH` + `ACCEPT_DATA`.

Artifacts:

- `examples/chunked_payload.bin`
- `artifacts/chunked_payload.bogasm`
- `artifacts/chunked_payload.bogbin`
- `artifacts/chunked_payload_receipt.json`
- `artifacts/chunked_payload_run_receipt.json`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm pack examples/chunked_payload.bin artifacts/chunked_payload.bogbin --chunk-size 64 --bogasm artifacts/chunked_payload.bogasm --receipt artifacts/chunked_payload_receipt.json
python3 -m bogvm run artifacts/chunked_payload.bogbin --receipt artifacts/chunked_payload_run_receipt.json
~~~

Boundary:

- Chunked deterministic auto-pack only.
- Not a `.bog` container compiler yet.
- Not compression victory.
- Not Fourier.
- Not hardware execution.

## v0.7.0: Automatic Residual Optimizer

v0.7.0 adds a deterministic automatic pack pipeline.

Public wording:

BOGBIN v0.7 adds automatic residual optimization: arbitrary bytes can be represented as deterministic generated base + exact residual patches, then verified by SHA-256 before acceptance.

Proof:

- `bogvm.bases.synthesize_basis()` is the shared deterministic basis implementation for `repeat_byte`, `ramp_u8`, `triangle_u8`, and `sine8_u8`.
- `bogvm.optimizer.optimize_residual_plan()` exhaustively tests every existing basis and every start byte `0..255`.
- The optimizer chooses by smallest residual count, then basis order, then lowest start byte.
- `bogvm.packer.pack_bytes_to_bogasm()` emits deterministic `.bogasm` with `STORE_RESIDUAL` patches, `VERIFY_HASH`, and `ACCEPT_DATA`.
- `python3 -m bogvm pack` reads bytes, emits `.bogasm`, assembles `.bogbin`, runs BOGVM, checks the receipt accepted `payload`, and writes the receipt.

Artifacts:

- `examples/auto_pack_payload.bin`
- `artifacts/auto_pack_payload.bogasm`
- `artifacts/auto_pack_payload.bogbin`
- `artifacts/auto_pack_payload_receipt.json`
- `artifacts/auto_pack_payload_run_receipt.json`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm pack examples/auto_pack_payload.bin artifacts/auto_pack_payload.bogbin --bogasm artifacts/auto_pack_payload.bogasm --receipt artifacts/auto_pack_payload_receipt.json
python3 -m bogvm run artifacts/auto_pack_payload.bogbin --receipt artifacts/auto_pack_payload_run_receipt.json
~~~

Boundary:

- Automatic residual optimization only.
- Not a compression victory claim.
- Not Fourier yet.
- Not a `.bog` container compiler yet.
- Not hardware/laptop execution yet.
- Exactness comes from `VERIFY_HASH` + `ACCEPT_DATA` gate.

## v0.1.1: Blocked Execution Receipts

v0.1.1 makes blocked VM-law failures auditable. Contradictory programs now emit blocked receipts instead of only tracebacking.

Proof:

- `examples/contradiction.bogasm` creates support and conflict pressure on the same claim.
- `INTERFERE` reports support pressure, conflict pressure, net pressure, and tension.
- `VERIFY` rejects the claim.
- `ACCEPT` is blocked because the claim is not verified.
- The CLI writes `artifacts/contradiction_receipt.json`.

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm assemble examples/contradiction.bogasm artifacts/contradiction.bogbin
python3 -m bogvm run artifacts/contradiction.bogbin --receipt artifacts/contradiction_receipt.json || echo "blocked receipt emitted"
~~~

Boundary:

- Blocked execution is not success.
- Blocked execution is still auditable.
- No `ACCEPT` without `VERIFY`.
- Candidate graph contamination remains zero.

## v0.1.0: Minimal Wave-State Binary VM

v0.1.0 creates the first minimal BOGVM.

Proof:

- `.bogasm` source assembles into `.bogbin`.
- BOGVM executes fixed-point sparse graph-state propagation.
- `examples/proof_chain.bogasm` verifies `A -> B -> C`, then accepts `claim_A_C`.
- The VM emits `artifacts/proof_chain_receipt.json`.

Boundary:

- This is a toy VM proof, not a full operating system.
- No Fourier/generative storage yet.
- No laptop port yet.
- No direct hardware execution yet.

## v0.2.0: Hash-Gated Generative Storage Opcodes

v0.2.0 adds the first deterministic generative storage surface to BOGVM.

Proof:

- `DECLARE_BASIS repeat_byte` declares a deterministic generator basis.
- `LOAD_COEFFICIENTS` stores generation parameters instead of raw output bytes.
- `SYNTHESIZE` reconstructs a generated data block.
- `VERIFY_HASH` checks the regenerated bytes against an expected SHA-256 hash.
- `ACCEPT_DATA` only accepts generated data after hash verification.
- Bad generated data/hash paths emit blocked receipts.

Artifacts:

- `examples/repeat_byte_storage.bogasm`
- `examples/repeat_byte_bad_hash.bogasm`
- `artifacts/repeat_byte_storage.bogbin`
- `artifacts/repeat_byte_storage_receipt.json`
- `artifacts/repeat_byte_bad_hash.bogbin`
- `artifacts/repeat_byte_bad_hash_receipt.json`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm assemble examples/repeat_byte_storage.bogasm artifacts/repeat_byte_storage.bogbin
python3 -m bogvm run artifacts/repeat_byte_storage.bogbin --receipt artifacts/repeat_byte_storage_receipt.json
python3 -m bogvm assemble examples/repeat_byte_bad_hash.bogasm artifacts/repeat_byte_bad_hash.bogbin
python3 -m bogvm run artifacts/repeat_byte_bad_hash.bogbin --receipt artifacts/repeat_byte_bad_hash_receipt.json || echo "bad hash correctly blocked"
~~~

Boundary:

- This is a deterministic toy generator, not a compression victory claim.
- Generated data is not accepted without hash verification.
- No Fourier/wave basis yet.
- No `.bog` container compiler yet.
- No laptop port yet.

## v0.3.0: Deterministic Integer Wave Basis

v0.3.0 adds the first position-dependent deterministic generator basis.

Proof:

- `DECLARE_BASIS ramp_u8` declares an integer wave-style basis.
- `LOAD_COEFFICIENTS` stores start byte and length.
- `SYNTHESIZE` reconstructs generated bytes using the rule:
  `byte[i] = (start + i) mod 256`
- `VERIFY_HASH` checks the reconstructed byte field.
- `ACCEPT_DATA` accepts only after hash verification.

Artifacts:

- `examples/ramp_u8_storage.bogasm`
- `artifacts/ramp_u8_storage.bogbin`
- `artifacts/ramp_u8_storage_receipt.json`

Verification:

    python3 -m unittest discover -s tests -p "test_*.py" -q
    python3 -m bogvm assemble examples/ramp_u8_storage.bogasm artifacts/ramp_u8_storage.bogbin
    python3 -m bogvm run artifacts/ramp_u8_storage.bogbin --receipt artifacts/ramp_u8_storage_receipt.json

Boundary:

- Integer deterministic basis only.
- No floating point.
- No Fourier basis yet.
- No compression victory claim.
- No `.bog` container compiler yet.
- No laptop port yet.

## v0.4.0: Triangle Integer Wave Basis

v0.4.0 adds the first periodic deterministic integer wave basis.

Proof:

- `DECLARE_BASIS triangle_u8` declares a periodic integer oscillator basis.
- `LOAD_COEFFICIENTS` stores start byte and length.
- `SYNTHESIZE` reconstructs bytes using a fixed integer triangle wave:
  `offsets = 0, 32, 64, 96, 128, 96, 64, 32`
  `byte[i] = (start + offsets[i mod 8]) mod 256`
- `VERIFY_HASH` gates the reconstructed byte field.
- `ACCEPT_DATA` accepts only after hash verification.
- Bad hash paths emit blocked receipts.

Artifacts:

- `examples/triangle_u8_storage.bogasm`
- `examples/triangle_u8_bad_hash.bogasm`
- `artifacts/triangle_u8_storage.bogbin`
- `artifacts/triangle_u8_storage_receipt.json`
- `artifacts/triangle_u8_bad_hash.bogbin`
- `artifacts/triangle_u8_bad_hash_receipt.json`

Verification:

    python3 -m unittest discover -s tests -p "test_*.py" -q
    python3 -m bogvm assemble examples/triangle_u8_storage.bogasm artifacts/triangle_u8_storage.bogbin
    python3 -m bogvm run artifacts/triangle_u8_storage.bogbin --receipt artifacts/triangle_u8_storage_receipt.json
    python3 -m bogvm assemble examples/triangle_u8_bad_hash.bogasm artifacts/triangle_u8_bad_hash.bogbin
    python3 -m bogvm run artifacts/triangle_u8_bad_hash.bogbin --receipt artifacts/triangle_u8_bad_hash_receipt.json || echo "triangle bad hash correctly blocked"

Boundary:

- Toy-scale integer oscillator only.
- No floating point.
- No sine/cosine lookup table yet.
- No Fourier basis yet.
- No compression victory claim.
- No `.bog` container compiler yet.
- No laptop port yet.

## v0.5.0: Fixed Integer Sine Lookup Basis

v0.5.0 adds the first sine-like deterministic lookup-table basis.

Proof:

- `DECLARE_BASIS sine8_u8` declares a fixed integer sine-like oscillator.
- `LOAD_COEFFICIENTS` stores start byte and length.
- `SYNTHESIZE` reconstructs bytes using a fixed 8-step integer sine lookup table:
  `offsets = 0, 90, 127, 90, 0, -90, -127, -90`
  `byte[i] = (start + offsets[i mod 8]) mod 256`
- `VERIFY_HASH` gates the reconstructed byte field.
- `ACCEPT_DATA` accepts only after hash verification.
- Bad hash paths emit blocked receipts.

Artifacts:

- `examples/sine8_u8_storage.bogasm`
- `examples/sine8_u8_bad_hash.bogasm`
- `artifacts/sine8_u8_storage.bogbin`
- `artifacts/sine8_u8_storage_receipt.json`
- `artifacts/sine8_u8_bad_hash.bogbin`
- `artifacts/sine8_u8_bad_hash_receipt.json`

Verification:

    python3 -m unittest discover -s tests -p "test_*.py" -q
    python3 -m bogvm assemble examples/sine8_u8_storage.bogasm artifacts/sine8_u8_storage.bogbin
    python3 -m bogvm run artifacts/sine8_u8_storage.bogbin --receipt artifacts/sine8_u8_storage_receipt.json
    python3 -m bogvm assemble examples/sine8_u8_bad_hash.bogasm artifacts/sine8_u8_bad_hash.bogbin
    python3 -m bogvm run artifacts/sine8_u8_bad_hash.bogbin --receipt artifacts/sine8_u8_bad_hash_receipt.json || echo "sine8 bad hash correctly blocked"

Boundary:

- Fixed integer lookup table only.
- No floating point.
- No runtime sine/cosine.
- No FFT yet.
- No Fourier basis yet.
- No compression victory claim.
- No `.bog` container compiler yet.
- No laptop port yet.

## v0.6.0: Residual Patching for Exact Reconstruction

v0.6.0 adds deterministic residual patching.

Proof:

- A generator can synthesize a base byte field.
- `STORE_RESIDUAL` stores deterministic byte corrections.
- `APPLY_RESIDUAL` applies corrections to the generated byte field.
- `VERIFY_HASH` gates the exact reconstructed bytes.
- `ACCEPT_DATA` accepts only after hash verification.
- Bad hash paths emit blocked receipts.

Artifacts:

- `examples/residual_patch_storage.bogasm`
- `examples/residual_patch_bad_hash.bogasm`
- `artifacts/residual_patch_storage.bogbin`
- `artifacts/residual_patch_storage_receipt.json`
- `artifacts/residual_patch_bad_hash.bogbin`
- `artifacts/residual_patch_bad_hash_receipt.json`

Verification:

    python3 -m unittest discover -s tests -p "test_*.py" -q
    python3 -m bogvm assemble examples/residual_patch_storage.bogasm artifacts/residual_patch_storage.bogbin
    python3 -m bogvm run artifacts/residual_patch_storage.bogbin --receipt artifacts/residual_patch_storage_receipt.json
    python3 -m bogvm assemble examples/residual_patch_bad_hash.bogasm artifacts/residual_patch_bad_hash.bogbin
    python3 -m bogvm run artifacts/residual_patch_bad_hash.bogbin --receipt artifacts/residual_patch_bad_hash_receipt.json || echo "residual bad hash correctly blocked"

Boundary:

- Deterministic byte residuals only.
- No automatic residual optimization yet.
- No compression victory claim.
- No Fourier basis yet.
- No `.bog` container compiler yet.
- No laptop port yet.
