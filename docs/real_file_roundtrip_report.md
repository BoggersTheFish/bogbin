# Real File Roundtrip Report

BOGBIN / BOGVM v1.4.0 evaluates exact file roundtrip across small deterministic text, JSON, binary, PNG, and WAV fixtures with deterministic adaptive chunk-size selection.

Command:

```bash
python3 scripts/evaluate_real_file_roundtrip.py
```

Artifacts:

- `artifacts/real_file_roundtrip_report.json`
- `artifacts/real_file_roundtrip_receipt.json`
- `artifacts/real_file_roundtrip/`

Current report summary:

- Case count: 5
- Passed roundtrip count: 5
- Roundtrip success rate: 1.0
- Total input bytes: 979
- Total chunk count: 54
- Total residual count: 564
- v1.2 mean residual density: 0.631188
- Current mean residual density: 0.576098
- Residual density delta from v1.2: -0.05509
- Residual density improved from v1.2: true

Cases:

| Name | Type | Bytes | Selected chunk | Chunks | Residuals | Density | Passed |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `text_payload` | text | 124 | 16 | 8 | 89 | 0.717742 | true |
| `json_payload` | json | 127 | 16 | 8 | 100 | 0.787402 | true |
| `binary_noise_like_payload` | binary | 160 | 128 | 2 | 0 | 0.0 | true |
| `png_payload` | png | 268 | 16 | 17 | 187 | 0.697761 | true |
| `wav_payload` | wav | 300 | 16 | 19 | 188 | 0.626667 | true |

Boundary:

- This is a roundtrip correctness report.
- This is not a compression benchmark victory.
- This is not a claim that `.bog` beats existing formats.
- The adaptive tournament evaluates chunk sizes 16, 32, 64, and 128.
- VM verification remains proof authority through `VERIFY_HASH` + `ACCEPT_DATA`.
- Exact recovery is checked with SHA-256.
