# Real File Roundtrip Report

BOGBIN / BOGVM v4.0 evaluates exact file roundtrip across small deterministic text, JSON, binary, PNG, and WAV fixtures with deterministic adaptive chunk-size selection, cost-aware reversible transform selection, compact BOGPK storage, and SHA-256 verification. BogOS Lite builds on this file/archive substrate for managed workspaces.

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
- Total chunk count: 38
- Total residual count: 460
- Container format: BOGPK-0.1
- v1.2 mean residual density: 0.631188
- Current mean residual density: 0.469867
- Residual density delta from v1.2: -0.161321
- Residual density improved from v1.2: true
- Aggregate transform counts: identity 28, xor_previous 1, delta_previous 1, nibble_split 3, mtf 4, bwt 0, bwt_mtf 1
- Total container bytes: 940
- Mean container-to-input ratio: 0.960163
- Aggregate container smaller than input: true
- All containers smaller than input: false

Cases:

| Name | Type | Bytes | Selected chunk | Chunks | Residuals | Density | Container/Input | Smaller | Passed |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `text_payload` | text | 124 | 16 | 8 | 81 | 0.653226 | 1.387097 | false | true |
| `json_payload` | json | 127 | 16 | 8 | 95 | 0.748031 | 1.472441 | false | true |
| `binary_noise_like_payload` | binary | 160 | 128 | 2 | 0 | 0.0 | 0.33125 | true | true |
| `png_payload` | png | 268 | 16 | 17 | 184 | 0.686567 | 1.238806 | false | true |
| `wav_payload` | wav | 300 | 128 | 3 | 100 | 0.333333 | 0.653333 | true | true |

Boundary:

- This is a roundtrip correctness report.
- This is not a compression benchmark victory.
- This is not a claim that `.bog` beats existing formats.
- The adaptive tournament evaluates chunk sizes 16, 32, 64, and 128.
- The transform tournament evaluates identity, xor_previous, delta_previous, nibble_split, mtf, bwt, and bwt_mtf.
- The transform tournament scores estimated packed size, residual count, transform cost, basis cost, and decode cost.
- The aggregate compression threshold is crossed.
- Not every individual fixture is smaller than input yet.
- Current outliers above 1.0 are `text_payload`, `json_payload`, and `png_payload`.
- VM verification remains proof authority through `VERIFY_HASH` + `ACCEPT_DATA`.
- Exact recovery is checked with SHA-256.
