# Real File Roundtrip Report

BOGBIN / BOGVM v1.1 adds a deterministic evaluation harness for exact file roundtrip across small real-file-like fixtures.

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
- Total chunk count: 14
- Total residual count: 701
- Mean residual density: 0.867574

Cases:

| Name | Type | Bytes | Chunks | Residuals | Density | Passed |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `text_payload` | text | 124 | 2 | 99 | 0.798387 | true |
| `json_payload` | json | 127 | 2 | 105 | 0.826772 | true |
| `binary_noise_like_payload` | binary | 160 | 3 | 154 | 0.9625 | true |
| `fake_png_payload` | png_like | 225 | 4 | 204 | 0.906667 | true |
| `fake_wav_payload` | wav_like | 172 | 3 | 139 | 0.80814 | true |

Boundary:

- This is a roundtrip correctness report.
- This is not a compression benchmark victory.
- This is not a claim that `.bog` beats existing formats.
- VM verification remains proof authority through `VERIFY_HASH` + `ACCEPT_DATA`.
- Exact recovery is checked with SHA-256.
