# Real File Roundtrip Report

BOGBIN / BOGVM v1.3 evaluates exact file roundtrip across small real-file-like fixtures with deterministic adaptive chunk-size selection.

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
- Total input bytes: 808
- Total chunk count: 44
- Total residual count: 449
- v1.2 mean residual density: 0.631188
- Current mean residual density: 0.555693
- Residual density delta from v1.2: -0.075495
- Residual density improved from v1.2: true

Cases:

| Name | Type | Bytes | Selected chunk | Chunks | Residuals | Density | Passed |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `text_payload` | text | 124 | 16 | 8 | 89 | 0.717742 | true |
| `json_payload` | json | 127 | 16 | 8 | 100 | 0.787402 | true |
| `binary_noise_like_payload` | binary | 160 | 128 | 2 | 0 | 0.0 | true |
| `fake_png_payload` | png_like | 225 | 16 | 15 | 152 | 0.675556 | true |
| `fake_wav_payload` | wav_like | 172 | 16 | 11 | 108 | 0.627907 | true |

Boundary:

- This is a roundtrip correctness report.
- This is not a compression benchmark victory.
- This is not a claim that `.bog` beats existing formats.
- The adaptive tournament evaluates chunk sizes 16, 32, 64, and 128.
- VM verification remains proof authority through `VERIFY_HASH` + `ACCEPT_DATA`.
- Exact recovery is checked with SHA-256.
