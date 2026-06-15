# BogOS v36 Plan: Verified Block Device Model

## Claim And Dependency

BogKernel can perform bounded, receipt-visible sector reads and writes against
one QEMU raw disk image. This depends on the v35.0.0 kernel and v35.1 audit
evidence and adds no filesystem persistence.

Implementation status: completed in v36.0.0. This is not a filesystem.

## Technical Scope

- Reference device: QEMU legacy IDE/ATA PIO primary master, LBA28.
- Media: one deterministic 4 MiB raw image, 8,192 512-byte sectors.
- Operations: synchronous presence probe, single-sector read, single-sector
  write, flush, and read-back verification.
- Admission: LBAs `0..8191` are readable. Only proof-data LBAs `64..127` are
  writable in v36. Sector 0 and LBAs `1..63`, reserved for future filesystem
  metadata, are protected.
- Verification: SHA-256 covers all 512 bytes. Reads require an expected hash.
  Writes require expected before and after hashes and commit only after
  successful read-back verification.
- v36 uses a standards-compliant full-block SHA-256 path so exact 512-byte
  sectors include the required final padding block without changing historical
  pre-v36 hashing behavior.
- Failure policy: timeout, device error, bounds error, or hash mismatch rejects
  the operation. A rejected write must never emit an accepted mutation receipt.

No Ring 3 process receives direct port access or a raw block syscall.
The existing v35 in-memory BogFS is unchanged and does not use the device.
v37 is the first milestone allowed to place BogFS state on this block layer.

## Minimum Components

- A small kernel-internal block interface with `read_sector` and
  `write_sector_verified` operations and explicit error reasons.
- ATA status polling with bounded timeouts and receipt-visible device errors.
- Deterministic sector buffers and no dynamic allocation in the I/O path.
- `scripts/make_v36_block_image.py` to build the canonical image and manifest.
- `scripts/evaluate_v36_block_device.py` to build, boot QEMU with
  `-drive file=...,format=raw,if=ide`, parse receipts, and emit the summary.
- Corruption helpers used only by the evaluator to create negative images.

## Receipts And Artifacts

Serial blocks:

- `BOGOS_BLOCK_DEVICE`: model, sector size/count, writable range, probe status.
- `BOGOS_BLOCK_READ`: LBA, expected hash, observed hash, status, reason.
- `BOGOS_BLOCK_WRITE`: LBA, before hash, requested after hash, read-back hash,
  status, reason, and `MUTATED_TRUSTED_STATE`.
- `BOGOS_BLOCK_INVARIANTS`: QEMU-only, one-device, single-sector, bounds,
  protected-range, hash-check, read-back, and no-user-raw-access claims.

Checked artifacts:

- `artifacts/bogos_v36_block_base.img`
- `artifacts/bogos_v36_block_written.img`
- `artifacts/bogos_v36_block_device_serial.log`
- `artifacts/bogos_v36_no_device_serial.log`
- `artifacts/bogos_v36_block_device_receipt.json`

The JSON receipt binds image hashes, serial hash, evaluator hash, accepted and
rejected evidence, and preserved v31-v35 evidence.

## Verification And Negative Matrix

The evaluator proves a known sector read, an admitted write, read-back hash
equality, and deterministic receipt fields. It rejects:

| Case | Required reason/evidence |
| --- | --- |
| No attached device | `device_absent` |
| LBA outside image | `lba_out_of_range` |
| Request larger than one sector | `unsupported_sector_count` |
| Write to protected sector | `protected_lba` and no mutation claim |
| Pre-write content differs from expected | `stale_preimage` |
| Read sector hash differs from manifest | `sector_hash_mismatch` |
| Device reports timeout/error | bounded `timeout` or `device_error` runtime rejection path; not fault-injected by the evaluator |
| Read-back differs from requested hash | `readback_hash_mismatch`; never claim accepted state |

Because a physical device may have partially written before a read-back
failure, v36 receipts must distinguish `DEVICE_MAY_HAVE_CHANGED` from
`MUTATED_TRUSTED_STATE`. BogKernel must not admit the new sector as trusted
state when verification fails.

## Explicit Non-Goals

No PCI discovery, virtio, DMA, interrupt-driven I/O, partitions, multiple
disks, caching, filesystem, user block API, physical hardware, or production
driver stack.

## Done

v36 is done when the evaluator independently boots its attached/no-device QEMU
scenarios, proves accepted read/write/read-back behavior and the deterministic
negative matrix, emits the declared artifacts, and the prior isolation,
loader, ABI, IPC, and in-memory BogFS evaluators still pass.
