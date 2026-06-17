# Bare-Metal Phase 6: Filesystem Maturity & Practical Persistence

## Claim And Dependency

Nested directories, genesis workspace root, and v41 journal on real disk with
host inspection tools. Depends on Phase 2, 5, and v40/v41 in `bogk-core`.

## Technical Scope

- Nested BogFS directories, rename, bounded permissions
- v40 genesis + v41 journal on AHCI partition (strict serial evidence)
- Alternate-root management on real disk
- `scripts/inspect_bogfs_partition.py` for host-side verification
- Document clean-reboot vs power-loss boundary (same as v37 caveat)

## Minimum Components

- `scripts/evaluate_phase6_fs_maturity.py`
- Full v38 + v40 + v41 receipt chain on hardware across two boots

## Receipts

v38 lifecycle + v40 genesis + v41 journal markers with `PLATFORM=baremetal`.

## Explicit Non-Goals

POSIX permissions model, power-loss atomicity proof, distributed FS.

## Done When

v41-equivalent journal on real partition; nested dir negative matrix; host
inspection tool works from Linux.