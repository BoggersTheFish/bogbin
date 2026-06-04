# BOGPK-0.1: Binary-Packed BOG Container

BOGPK-0.1 is the compact reconstruction blueprint for BOGBIN payload storage.

It is not a receipt format. It is not proof authority. The VM remains proof authority through deterministic reconstruction and SHA-256 verification.

## Goals

- Remove JSON metadata bloat from `.bog` containers.
- Store transform and basis selections as packed enum IDs.
- Derive chunk offsets implicitly from chunk index and selected chunk size.
- Compress residual patch metadata with delta-coded offsets and zero-run records.
- Preserve deterministic byte-for-byte encoding.

## File Layout

All integers are unsigned. Multi-byte fixed-width integers are big-endian. Varints use unsigned LEB128 with the shortest valid encoding only.

```text
BOGPKHeader
TransformBasisStream
ChunkResidualIndexStream
ResidualPatchStream
OptionalHashStream
```

## Header

```text
magic                  6 bytes   ASCII "BOGPK1"
version                1 byte    0x01
flags                  1 byte
chunk_size_code        1 byte
original_length        varuint
chunk_count            varuint
total_residual_count   varuint
whole_sha256           32 bytes
```

### Flags

```text
bit 0: has_transformed_chunk_hashes
bit 1: has_original_chunk_hashes
bit 2: has_zero_residual_runs
bit 3: reserved, must be 0
bit 4: reserved, must be 0
bit 5: reserved, must be 0
bit 6: reserved, must be 0
bit 7: reserved, must be 0
```

### Chunk Size Code

```text
0 = 16 bytes
1 = 32 bytes
2 = 64 bytes
3 = 128 bytes
```

Chunk offsets are implicit:

```text
offset(chunk_index) = chunk_index * chunk_size
```

All chunks except the final chunk have `chunk_size` bytes. Final chunk length is:

```text
final_length = original_length - ((chunk_count - 1) * chunk_size)
```

Decoders must reject `original_length == 0` when `chunk_count > 0`, `chunk_count == 0` when `original_length > 0`, `chunk_count != ceil(original_length / chunk_size)`, and final lengths outside `1..chunk_size`.

## Enum Packing

Each chunk descriptor stores transform and basis in one byte:

```text
bits 7..5   transform_id
bits 4..1   basis_id
bit 0       residual encoding, 0 = delta offsets, 1 = bitmask
```

### Transform IDs

```text
0 = identity
1 = xor_previous
2 = delta_previous
3 = nibble_split
4 = mtf
5 = bwt
6 = bwt_mtf
7 = reserved
```

### Basis IDs

```text
0 = zero_block
1 = repeat_byte
2 = delta_u8
3 = dictionary_u8
4 = rle_u8
5 = ramp_u8
6 = triangle_u8
7 = sine8_u8
8 = fourier8_u8
9..15 = reserved
```

## Transform/Basis Descriptor Stream

One descriptor per chunk:

```text
descriptor             1 byte
start_byte             1 byte
delta                  1 byte
transform_param        varuint only for bwt and bwt_mtf
residual_count         varuint
```

No chunk name, offset, or nominal length is stored. Chunk index is the descriptor order.

`delta` is present for every descriptor even when the basis ignores it. This keeps the first packed format simple and branch-light. A later version may omit zero deltas through descriptor flags.

`transform_param` stores the BWT primary index for `bwt` and `bwt_mtf`. It is omitted for all other transforms.

## Residual Patch Stream

Residuals are grouped by chunk in descriptor order.

For each chunk with `residual_count > 0` and descriptor bit 0 clear:

```text
offset_delta           varuint
byte                   1 byte
```

Offsets are strictly increasing within a chunk.

```text
actual_offset[0] = offset_delta[0]
actual_offset[n] = actual_offset[n-1] + 1 + offset_delta[n]
```

This makes adjacent residual offsets cheap while still supporting sparse patches.

For each chunk with `residual_count > 0` and descriptor bit 0 set:

```text
residual_mask          ceil(chunk_length / 8) bytes
residual_bytes         residual_count bytes
```

Mask bit order is least-significant bit first within each byte:

```text
mask[offset / 8] & (1 << (offset % 8))
```

Residual bytes are stored in ascending offset order. Decoders must reject masks where the number of set bits does not match `residual_count`. Decoders must also reject high bits in the final mask byte that would describe offsets outside the implied chunk length.

The encoder should choose bitmask residuals only when the bitmask plus residual byte stream is smaller than the delta-offset stream.

## Zero-Residual Runs

If `flags.has_zero_residual_runs` is set, a zero-residual chunk run may replace repeated descriptors where:

- transform_id matches
- basis_id matches
- start_byte matches
- delta matches
- residual_count is 0

Run record:

```text
0xFF                   1 byte descriptor sentinel
run_length             varuint
descriptor             1 byte
start_byte             1 byte
delta                  1 byte
transform_param        varuint only for bwt and bwt_mtf
```

`run_length` must be at least 2.

## Optional Hash Stream

When `has_transformed_chunk_hashes` is set:

```text
transformed_sha256[chunk_count]  32 bytes each
```

When `has_original_chunk_hashes` is set:

```text
original_sha256[chunk_count]     32 bytes each
```

Compact mode should omit per-chunk hashes and rely on `whole_sha256`. Audit mode may include both chunk hash streams.

## Decoder Requirements

- Reject non-minimal varints.
- Reject truncated and oversized varints.
- Reject reserved flag bits.
- Reject reserved transform IDs and basis IDs.
- Reject chunk counts that do not match original length and chunk size.
- Reject total residual counts larger than original length.
- Reject residual offsets outside the implied chunk length.
- Reject residual offsets that are not strictly increasing.
- Reject bitmask residual bits outside the implied chunk length.
- Reconstruct transformed chunk bytes from descriptor plus residual stream.
- Invert the selected transform.
- Reject invalid transform parameters.
- Concatenate original chunks in descriptor order.
- Verify `whole_sha256`.
- Reject trailing bytes.

## Parser Split

The container module must support two tracks:

- JSON `.bog`: human-readable audit/debug manifest.
- Binary `.bogpk`: strict packed reconstruction stream.

Both tracks must compile or reconstruct to the same payload bytes for the same plan. The binary path should avoid JSON parsing and feed decoded chunk plans directly into existing synthesis, residual application, transform inversion, and hash verification routines.

## Boundary

- BOGPK-0.1 is a blueprint format, not a receipt.
- No entropy coding yet.
- No compression victory claim until measured `.bogpk` size is smaller than input.
- VM proof authority remains hash-gated acceptance.
