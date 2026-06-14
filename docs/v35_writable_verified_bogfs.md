# BogOS v35: Writable Verified BogFS

## Why v35 Matters

BogOS v35 gives isolated dynamically loaded Ring 3 apps a tiny writable file
service. The service is kernel-owned, in-memory, bounded, and QEMU-only. A
write becomes trusted file state only after the kernel copies validated user
bytes into staging storage and verifies the receipt-visible SHA-256.

This is not a POSIX filesystem and has no disk persistence or directories.

## Register ABI

Writable BogFS extends Syscall ABI v2 through `int 0x80`.

| Number | Name | `EBX` | `ECX` | `EDX` | `ESI` | Success |
| ---: | --- | --- | --- | --- | --- | --- |
| 17 | `bogfs_write` | path pointer | path length | data pointer | data length | bytes committed |
| 18 | `bogfs_read` | path pointer | path length | output pointer | output capacity | bytes read |
| 19 | `bogfs_stat` | path pointer | path length | output pointer | output capacity | 40 |

`bogfs_stat` writes little-endian version and length fields followed by the
32-byte committed SHA-256. Existing ABI v2 error numbers remain stable.

## Commit Protocol

The kernel validates that the active PID was admitted by the v32 loader and
that its CR3 is active. It validates the path and data mappings against the
caller's v31 private page tables, enforces exact table paths and write policy,
copies data into a fixed 64-byte staging buffer, computes SHA-256 twice for the
receipt check, checks the 96-byte total capacity, and only then replaces the
kernel-owned committed file record.

Every write receipt includes PID, path, length, SHA-256, old version/hash, new
version/hash, status, rejection reason, and trusted-state mutation status.
Reads and stats recompute and verify the committed hash before returning data.

The tiny table contains `/data/shared.bin`, `/data/fill.bin`,
`/data/readonly.bin`, and the proof-only `/data/hashfail.bin`. The last path
deterministically injects a receipt-check mismatch to prove that failed hash
verification does not mutate state.

## Negative Proof Matrix

The QEMU negative app proves rejection of:

- kernel/bad data pointer
- oversized write
- read-only destination
- invalid destination path
- cross-process private pointer
- full bounded storage
- failed receipt hash check

Rejected writes report `MUTATED_TRUSTED_STATE=false`. When a file was resolved,
the old and new version/hash fields remain equal. A final read proves rejected
replacements did not alter the earlier committed `/data/shared.bin` bytes.

## Boundaries

BogOS v35 remains QEMU-only, i686, in-memory only, and experimental. It has no
real disk persistence, POSIX API, path creation, deletion, rename, directories,
open handles, append mode, concurrent writers, ACLs, quotas per PID, journaling,
crash recovery, SMP synchronization, or physical hardware support.
