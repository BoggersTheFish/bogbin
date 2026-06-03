# Real File Roundtrip Report

BOGBIN / BOGVM v1.2 evaluates exact file roundtrip across small real-file-like fixtures after adding deterministic `zero_block`, `delta_u8`, `dictionary_u8`, and `rle_u8` bases.

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
- Total residual count: 510
- Baseline mean residual density: 0.867574
- Current mean residual density: 0.631188
- Residual density delta: -0.236386
- Residual density improved: true

Cases:

| Name | Type | Bytes | Chunks | Residuals | Density | Passed |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `text_payload` | text | 124 | 2 | 99 | 0.798387 | true |
| `json_payload` | json | 127 | 2 | 105 | 0.826772 | true |
| `binary_noise_like_payload` | binary | 160 | 3 | 0 | 0.0 | true |
| `fake_png_payload` | png_like | 225 | 4 | 189 | 0.84 | true |
| `fake_wav_payload` | wav_like | 172 | 3 | 117 | 0.680233 | true |

Boundary:

- This is a roundtrip correctness report.
- This is not a compression benchmark victory.
- This is not a claim that `.bog` beats existing formats.
- The deterministic fixture set includes arithmetic byte patterns, so `delta_u8` can fit some chunks exactly.
- VM verification remains proof authority through `VERIFY_HASH` + `ACCEPT_DATA`.
- Exact recovery is checked with SHA-256.
