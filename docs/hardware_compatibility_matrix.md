# Hardware Compatibility Matrix

Template for tracking bare-metal test status. Update after each Phase 1+ hardware
session.

## Legend

| Status | Meaning |
| --- | --- |
| `pending` | Not yet tested |
| `pass` | Phase criteria met; receipt in `artifacts/` |
| `partial` | Boots but phase criteria incomplete |
| `fail` | Blocked; see notes |
| `n/a` | Out of scope for current phase |

## Machines

| Machine ID | Model | CPU | Firmware | Chipset | Storage | Serial | Phase 0 | Phase 1 | Phase 2 | Phase 3 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hw-001` | _TBD_ | _TBD_ | BIOS / UEFI | _TBD_ | _TBD_ | _TBD_ | pending | pending | n/a | n/a | |
| `hw-002` | _TBD_ | _TBD_ | BIOS / UEFI | _TBD_ | _TBD_ | _TBD_ | pending | pending | n/a | n/a | |

## Phase Coverage Targets

| Phase | Minimum hardware evidence |
| --- | --- |
| 0 | QEMU-via-GRUB only (no hardware required) |
| 1 | 1+ real machine USB boot + serial receipt |
| 2 | 1+ machine on isolated USB/spare partition |
| 3 | 2+ machines (timer + keyboard) |
| 4 | 1+ machine with varying RAM size |
| 5 | 1+ machine interactive shell |
| 6 | 1+ machine two-boot persistence |
| 7 | 1+ x86_64 UEFI laptop |
| 8 | 2+ dual-boot configs (Linux+Bogbin, Windows+Bogbin) |
| 9 | Cross-phase matrix review |

## Artifact Links

When a machine passes a phase, link the receipt:

| Machine | Phase | Serial log | JSON receipt |
| --- | --- | --- | --- |
| _example_ | 1 | `artifacts/baremetal_phase1_hw-001.log` | `artifacts/baremetal_phase1_grub_boot_receipt.json` |

## Known QEMU-Only Development

Primary development remains QEMU. Real-hardware rows update on scheduled validation
runs, not every commit.