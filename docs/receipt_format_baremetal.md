# Bare-Metal Receipt Format Extensions

## Status

Draft — Phase 0 baseline; finalized in Phase 9.

## Layers

Bogbin uses two receipt layers (unchanged from QEMU milestones):

1. **Serial receipts** — `key=value` lines between `BEGIN`/`END` markers on COM1
2. **JSON summary receipts** — host evaluators write `artifacts/baremetal_phase*_*.json`

Bare-metal adds fields without breaking existing v16–v41 parsers.

## Serial Extensions

### Phase 0 (GRUB hello)

Reuses v16 markers with optional additions:

```text
BOGKERNEL_BOOT_BEGIN
BOGKERNEL_FORMAT=BOGKERNEL-boot-receipt-16.0
PLATFORM=qemu|baremetal
BOOT_PATH=qemu_direct|grub_multiboot1
BOOT_FIRMWARE=bios|uefi|unknown
BOOT_LOADER=grub2|qemu
EXECUTION_STATUS=completed
BOGKERNEL_BOOT_END
```

### Phase 1 (bare-metal boot)

```text
BOGBIN_PHASE1_BOOT_BEGIN
PLATFORM=baremetal
BOOT_FIRMWARE=bios|uefi
BOOT_LOADER=grub2
BOOT_PATH=grub_multiboot1
EARLY_CONSOLE=serial|vga|both
MEMORY_MAP_SOURCE=multiboot
EXECUTION_STATUS=completed
BOGBIN_PHASE1_BOOT_END
```

### Phase 2+ (storage, HAL, memory, userspace)

See per-phase plans. Common fields:

| Field | Phases | Values |
| --- | --- | --- |
| `STORAGE_BACKEND` | 2+ | `qemu_ide`, `ahci` |
| `TIMER` | 3+ | `lapic`, `pit` |
| `IRQ_MODEL` | 3+ | `apic`, `pic` |
| `ARCH` | 7+ | `i686`, `x86_64` |

## JSON Receipt Envelope

Extends existing evaluator JSON (v36–v41 style):

```json
{
  "format": "BOGBIN-baremetal-phase0-receipt-1.0",
  "execution_status": "completed",
  "platform": "qemu",
  "boot_path": "grub_multiboot1",
  "boot_firmware": "bios",
  "boot_loader": "grub2",
  "hardware_id": null,
  "verified_on_hardware": false,
  "boundary_flags": {
    "qemu_grub_chainload": true,
    "physical_hardware": false,
    "dual_boot_installed": false
  },
  "input_hashes": {},
  "serial_log_hashes": {},
  "evaluator_sha256": "..."
}
```

### New fields

| Field | Type | Description |
| --- | --- | --- |
| `boot_path` | string | How kernel was loaded |
| `boot_firmware` | string | `bios`, `uefi`, or `unknown` |
| `boot_loader` | string | `grub2`, `qemu`, etc. |
| `hardware_id` | string or null | Matrix ID e.g. `hw-001` |
| `verified_on_hardware` | bool | True when real serial log attached |
| `boundary_flags.physical_hardware` | bool | True for Phase 1+ hardware proofs |
| `boundary_flags.dual_boot_installed` | bool | True after Phase 8 install |

## Strictness Rule

Follow v41 evaluator bar: kernel-emitted serial markers are required. Evaluators
must not use simulated serial hashes (v40 fallback pattern is forbidden for
bare-metal phases).

## Phase 9 Finalization

- Disk-backed receipt log on BogFS (`/system/receipt_log`)
- Optional TPM PCR extension fields
- Schema entry in `schemas/` if JSON envelope stabilizes