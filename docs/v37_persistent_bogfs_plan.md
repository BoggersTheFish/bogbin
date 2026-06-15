# BogOS v37: Persistent Verified BogFS

## Claim And Dependency

BogKernel can mount, verify, update, reboot, and remount a tiny persistent
BogFS on the v36 verified block device. This is the first disk persistence
claim, but only for clean QEMU reboots.

## On-Disk Layout

Use the v36 4 MiB image and this fixed bounded layout:

| Region | Purpose |
| --- | --- |
| Sector 0 | Reserved/protected |
| Sector 1 / 2 | Superblock A / B |
| Sectors 8..15 / 16..23 | Manifest A / B |
| Sectors 24..63 | Reserved/protected |
| Sectors 64..8191 | Append-only data extents |

v37 replaces the v36 evaluator's proof-only writable-range policy with a
filesystem-owned admission map: only the inactive superblock, inactive
manifest, and newly allocated data extents may be written during a commit.
All other sectors remain protected for that operation.

Each superblock contains magic, format version, generation, manifest slot,
manifest length, manifest SHA-256, root SHA-256, and its own checksum. Each
manifest contains generation, entry count, next-free-data sector, and
fixed-size file records. A file record contains canonical path, flags, version,
byte length, extent start/count, and content SHA-256.

All integers are little-endian. A superblock occupies one sector and must have
canonical zero padding. A manifest occupies exactly eight sectors: a 64-byte
header followed by at most 31 canonical 128-byte file records and zero
padding. Paths occupy 64 bytes, contain at most 63 ASCII bytes, and are
NUL-terminated with zero padding. A file occupies contiguous complete sectors;
unused bytes in its final sector are canonical zeroes and are included in the
extent read-back hash but excluded from the file content hash.

The root hash deterministically binds the superblock fields and verified
manifest hash. Empty/padding bytes must be canonical zeroes.

## Mount And Commit Protocol

Mount verifies both superblocks, checks all referenced bounds and canonical
fields, verifies manifest and file content hashes, then selects the highest
valid generation. Equal-generation disagreement rejects as ambiguous. If only
one root is valid, mount it and emit fallback evidence. If neither is valid,
reject the mount.

v37 deliberately uses a separate kernel boot-proof path. Syscall ABI v2
numbers 17-19 and the v35 in-memory BogFS behavior remain unchanged. The boot
proof applies equivalent bounded caller, pointer, path, length, policy, stale
preimage, and storage-full admission checks before its one accepted fixed-file
commit. Wiring persistent BogFS into Ring 3 syscalls is deferred.

Commit order:

1. Copy validated user bytes into bounded kernel staging and hash them.
2. Write new append-only data extent through v36 and verify read-back.
3. Build the inactive manifest slot with the incremented file/root generation,
   write it, and verify read-back and hash.
4. Write the inactive superblock last and verify it.
5. Admit the new root only after every verification succeeds.

The prior valid root remains the fallback. Failed commits preserve the
previous trusted root, though the disk may contain unreachable partial data.

## Components, Evaluator, And Artifacts

- Persistent BogFS parser, mount verifier, fixed table, and commit state.
- Deterministic image builder: `scripts/make_v37_bogfs_image.py`.
- Corruption images are generated in temporary storage by the evaluator.
- Two-boot evaluator: `scripts/evaluate_v37_persistent_bogfs.py`.
- Serial receipts: `BOGOS_BOGFS_MOUNT`, `BOGOS_BOGFS_COMMIT`,
  `BOGOS_PERSISTENT_BOGFS`, plus existing syscall receipts.
- Artifacts: seeded/mutated images, first/reboot serial logs, and
  `artifacts/bogos_v37_persistent_bogfs_receipt.json`.

The evaluator must start from a canonical seed image, run a write in boot one,
preserve the mutated image, boot it again, and prove matching root, file
version, length, hash, and bytes.

## Negative Matrix

Reject or fall back without accepting unverified bytes for bad superblock
magic/version/checksum, manifest pointer outside the image, manifest hash
mismatch, noncanonical padding/path, duplicate file record, overlapping or
out-of-range extent, content hash mismatch, equal-generation root conflict,
generation rollback below both known valid roots, data exhaustion, manifest
capacity exhaustion, and injected failure at each commit stage.

Rejected writes must retain the previous trusted root, version, hash, stat
result, and readable bytes. Corruption of both roots must reject mount.

## Crash-Safety Boundary And Non-Goals

The ordered alternate-root design limits what can be accepted after an
interrupted commit, but v37 does not prove sudden power-loss atomicity,
hardware cache flush behavior, or sector atomicity. The claimed persistence
test is clean QEMU shutdown/reboot only.

No POSIX, directories, create/delete, journaling, garbage collection, extent
reuse, concurrent writers, open handles, physical disks, or arbitrary image
sizes.

## Done

v37 is done when the standalone boot proof mounts and commits the fixed file,
the two-boot evaluator proves survival, every implemented corruption case
rejects or falls back correctly, and all accepted writes use ATA write,
read-back, and SHA-256 verification before root admission.

## Implemented Boundary

The implemented proof contains exactly one canonical file,
`/data/persist.bin`, with a 64-byte maximum. It alternates two superblock and
manifest slots and appends one-sector file versions. Boot one commits
`V37-PERSISTED-DATA`; boot two verifies the same version, content hash, root
hash, LBA, and bytes from the same image.

The corruption evaluator proves superblock-checksum, root-hash,
manifest-hash, file-table, and file-content failures fall back to the prior
valid root. Corruption of both roots rejects mount. This is clean-reboot
evidence only. No POSIX, directories, create/delete, rename, journaling,
garbage collection, disk-loaded apps, physical hardware, or production
filesystem claim is made.
