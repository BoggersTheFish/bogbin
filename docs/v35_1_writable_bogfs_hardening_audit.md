# BogOS v35.1: Writable BogFS Hardening Audit

This audit strengthens evidence for v35.0.0 without changing its release claim,
ABI numbers, in-memory boundary, or fixed-table design.

## Length Boundary

The audited policy explicitly rejects zero-length writes with `invalid_length`.
An exact 64-byte write succeeds and advances the destination version. A 65-byte
write rejects without trusted-state mutation.

## Version And Failure Preservation

Two repeated writes to `/data/shared.bin` prove deterministic version
transitions `1 -> 2 -> 3`. A later storage-full replacement reports equal old
and new version/hash fields. Stat receipts before and after that failure are
identical, and a following read returns the version-3 committed bytes.

## Path And Table Policy

Only exact fixed-table byte strings identify files. An alias attempt containing
`..` rejects as `invalid_path`. `/system`, `/apps`, and `/receipts` paths reject
as `protected_path`. A canonical attempt to create `/data/new.bin` rejects as
`file_table_full`. Another process's private pointer rejects before copying.

## IPC Interaction

A self-channel queues one message. The process then performs a rejected
protected-path BogFS write. Poll receipts remain at queue depth one before and
after the failed file operation, and the same message ID/hash is subsequently
received. Failed BogFS operations therefore mutate neither trusted file state
nor IPC queue state.

## Boundary

The audit remains QEMU-only, i686, in-memory only, fixed-table, and non-POSIX.
It adds no persistence, path creation, directories, or block-device support.
