# BOGBIN v1.6 Plan: Binary-Packed Container

Goal: reduce `.bog` blueprint overhead while preserving exact reconstruction and auditability.

## Problem

The v1.5 transform tournament reduces residual density, but the JSON `.bog` container is much larger than the input fixture set:

- Mean residual density before sorting transforms: `0.503575`
- Mean residual density with sorting transforms: `0.469867`
- Mean container/input ratio: `38.548519`
- All containers smaller than input: `false`

The payload model improved. The metadata model did not.

The initial v1.6 `.bogpk` path plus sorting transforms and bitmask residuals reduces the mean container/input ratio to `0.960163`. The aggregate fixture set crosses the compression threshold, but not every individual fixture is smaller yet.

## Direction

Introduce a binary-packed container alongside the current JSON container.

JSON `.bog` remains the audit/debug format. Binary `.bogpk` becomes the compression-threshold target.

Formal draft spec: `spec/BOGPK_0_1.md`.

## Initial Binary Layout

Header:

- `magic`: `BOGPK1`
- `version`: `1`
- `flags`: bitset
- `chunk_size_code`: 2 bits
- `original_length`: varint
- `chunk_count`: varint
- `total_residual_count`: varint
- `whole_sha256`: 32 bytes

Chunk descriptor stream:

- `transform_id`: 2 bits
- `basis_id`: 4 bits
- `start_byte`: 8 bits
- `delta`: 8 bits
- `length_override`: varint only for the final short chunk
- `residual_count`: varint

Residual stream:

- Offset deltas as varints.
- Residual bytes as raw bytes.
- Zero-residual chunk runs as RLE records.
- Dense residual chunks may use bitmask residual encoding.

Optional verification stream:

- Per-transformed-chunk SHA-256 hashes only when requested by a flag.
- Per-original-chunk SHA-256 hashes only when requested by a flag.
- Default compact mode relies on whole-payload SHA-256 plus deterministic reconstruction order.

## Validation Requirements

- Binary decode must reconstruct the same bytes as JSON `.bog`.
- Binary decode must produce the same whole SHA-256.
- Binary encode must be deterministic byte-for-byte.
- The report must include JSON container size, binary container size, and input size.
- Compression-threshold success is only true when binary container size is smaller than input size.

## Boundary

- No entropy coding in the first binary container.
- No compression victory claim until the report proves it.
- No change to VM proof authority: accepted data still requires hash verification.
