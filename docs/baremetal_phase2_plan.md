# Bare-Metal Phase 2: Real Storage Driver & Persistent Boot

## Claim And Dependency

Replace QEMU ATA PIO with AHCI behind a block trait; mount BogFS from a real
partition with v38-equivalent persistence. Depends on Phase 1 and v36–v38 proofs.

## Technical Scope

- `platform/block.rs` trait preserving v36 verified-sector semantics
- `platform/block/qemu_ide.rs` (extracted), `platform/block/ahci.rs` (new)
- `platform/partition.rs` — GPT/MBR parse, Bogbin partition identification
- Partition-relative BogFS mount
- QEMU AHCI dev path (`-device ich9-ahci`) for primary dev
- Two-boot persistence on isolated USB/spare partition only

## Minimum Components

- `scripts/make_baremetal_disk_image.py`
- `scripts/flash_bogbin_partition.sh`
- `scripts/evaluate_phase2_ahci_persistence.py`
- Dual-boot safety checklist sign-off per machine

## Receipts

Extend `BOGOS_BLOCK_DEVICE`: `MODEL=ahci`, `BACKEND=ahci|qemu_ide`.

`BOGBIN_PHASE2_STORAGE_BEGIN/END` with partition UUID, probe status.

## Negative Matrix

Mirror v36: `device_absent`, `lba_out_of_range`, `protected_lba`,
`stale_preimage`, `sector_hash_mismatch`, `readback_hash_mismatch`.

## Safety Gate

Mandatory checklist before internal disk tests. Destructive tests on USB/spare
partition only until Phase 8.

## Explicit Non-Goals

Host OS partition modification, nested directories, userspace shell.

## Done When

v38-equivalent lifecycle on QEMU-AHCI and real test partition; two-boot receipt
chain on hardware; QEMU-IDE backend still passes.