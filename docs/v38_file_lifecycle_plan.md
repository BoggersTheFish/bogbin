# BogOS v38: File Lifecycle

## Claim And Dependency

Persistent BogFS supports a bounded flat `/data` namespace and receipt-visible
create, delete, list, read, write, and stat operations. It depends on the v37
mounted-root and commit protocol while using a separate v38 on-disk format.

## Directory And Path Contract

Manifest records gain an entry type (`file`, `directory`, or `tombstone`) and
monotonic lifecycle ID. These fields use reserved bytes in the v37 128-byte
record; the on-disk format version increments and v38 mounts only the v38
format. Paths are stored as canonical absolute ASCII strings.
The only canonical root is `/`. Other paths must not contain NUL, repeated
slash, `.` or `..` components, trailing slash, empty components, aliases, or
overlong components/paths.

The implemented mutable namespace is flat `/data`; nested directory creation
is deferred. Protected top-level directory records exist for `/system`,
`/apps`, and `/receipts`. Listings return immediate live `/data` children only,
sorted by canonical byte order.
User mutations are allowed only under `/data`. `/system`, `/apps`, and
`/receipts` are protected. The image builder seeds required protected
directories.

## Lifecycle Semantics And ABI

v38 deliberately remains a separate kernel boot proof. v35 ABI v2 calls
17-19 remain in-memory, and no syscall numbers 20-22 are added. The boot proof
applies fixed caller authority and the same bounded path/policy checks.

All reserved values and unsupported flags reject. Create requires a live
directory parent and no live entry at the path. Delete rejects root, protected
entries, missing entries, and non-empty directories. A deleted path may be
created again with a new monotonic lifecycle ID and version 1.

Each accepted lifecycle operation commits a new v37 root. Delete retains old
extents as unreachable evidence; it is not secure erase. Only the previous
valid root is retained for recovery, with no user-facing rollback syscall.

## Receipts, Evaluator, And Artifacts

- Add `BOGOS_BOGFS_LIFECYCLE` receipts with operation, canonical path, type,
  old/new existence and versions, old/new root hashes, status, reason, and
  mutation claim.
- Add `BOGOS_BOGFS_LIST` receipts binding directory version, ordered result
  hash, count, status, and reason.
- Preserve normal ABI v2 behavior and v37 receipts in their own scenarios.
- Add `scripts/evaluate_v38_file_lifecycle.py`.
- Check in a lifecycle disk image, serial log, and
  `artifacts/bogos_v38_file_lifecycle_receipt.json`.

## Negative Matrix

The implemented evaluator proves rejection and trusted-root non-mutation for
unauthorized caller, invalid pointer, relative path, `..` traversal, repeated
slash alias, protected/outside-mutable paths, duplicate create, missing
delete, deleted-file read/write, oversized file, table exhaustion, data
exhaustion, stale root/version/preimage, list-on-file, data read-back mismatch,
and metadata read-back mismatch.

It also proves deterministic sorted listing, delete persistence across reboot,
active-root corruption fallback, and fail-closed table/listing/data
corruption. Recreate-as-new identity and nested-directory negatives are
deferred with nested mutable directories.

## Explicit Non-Goals

No POSIX API, ownership, permissions beyond fixed path policy, links, rename,
mount points, timestamps, recursive deletion, open handles, append mode,
secure deletion, arbitrary rollback, or concurrent mutation.

## Done

v38 is done when the flat `/data` lifecycle works across reboot, all accepted
mutations bind new verified roots, all rejected mutations preserve the prior
root, and v35-v37 evidence remains intact.

## Implemented Layout And Boundary

The v38 image retains v37 superblock and manifest LBAs, increments the format
version, and holds at most eight 128-byte records. The manifest header binds
generation, occupied record count, append-only next-free LBA, next lifecycle
ID, and a record-table/listing hash. Boot one creates `/data/new.txt`, writes
it, and tombstones `/data/delete.txt` as three separate verified commits.
The bounded early kernel stack increases from 16 KiB to 32 KiB to hold the
lifecycle verifier state and receipts; manifest mutation uses one fixed
kernel-owned staging buffer.

No nested mutable directories, rename, recreation, new Ring 3 filesystem
syscalls, POSIX behavior, production reliability, or physical hardware support
is claimed.
