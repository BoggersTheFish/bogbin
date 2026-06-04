# Real File Roundtrip Report

BOGBIN / BOGVM v1.5-dev evaluates exact file roundtrip across small deterministic text, JSON, binary, PNG, and WAV fixtures with deterministic adaptive chunk-size selection and reversible transform selection.

Command:

```bash
python3 scripts/evaluate_real_file_roundtrip.py
```

Artifacts:

- `artifacts/real_file_roundtrip_report.json`
- `artifacts/real_file_roundtrip_receipt.json`
- `artifacts/reversible_transform_tournament_report.json`
- `artifacts/reversible_transform_tournament_receipt.json`
- `artifacts/real_file_roundtrip/`

Current report summary:

- Case count: 5
- Passed roundtrip count: 5
- Roundtrip success rate: 1.0
- Total input bytes: 979
- Total chunk count: 45
- Total residual count: 493
- v1.2 mean residual density: 0.631188
- Current mean residual density: 0.503575
- Residual density delta from v1.2: -0.127613
- Residual density improved from v1.2: true
- Aggregate transform counts: identity 31, xor_previous 2, delta_previous 9, nibble_split 3
- Total container bytes: 37739
- Mean container-to-input ratio: 38.548519
- All containers smaller than input: false

Cases:

| Name | Type | Bytes | Selected chunk | Chunks | Residuals | Density | Container/Input | Smaller | Passed |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `text_payload` | text | 124 | 16 | 8 | 87 | 0.701613 | 55.137097 | false | true |
| `json_payload` | json | 127 | 16 | 8 | 95 | 0.748031 | 55.472441 | false | true |
| `binary_noise_like_payload` | binary | 160 | 128 | 2 | 0 | 0.0 | 13.51875 | false | true |
| `png_payload` | png | 268 | 16 | 17 | 186 | 0.69403 | 48.701493 | false | true |
| `wav_payload` | wav | 300 | 16 | 10 | 125 | 0.416667 | 28.806667 | false | true |

Boundary:

- This is a roundtrip correctness report.
- This is not a compression benchmark victory.
- This is not a claim that `.bog` beats existing formats.
- The adaptive tournament evaluates chunk sizes 16, 32, 64, and 128.
- The transform tournament evaluates identity, xor_previous, delta_previous, and nibble_split.
- The compression threshold is measured but not reached.
- VM verification remains proof authority through `VERIFY_HASH` + `ACCEPT_DATA`.
- Exact recovery is checked with SHA-256.
