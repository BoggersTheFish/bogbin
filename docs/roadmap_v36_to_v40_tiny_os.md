# BogOS v36-v40 Roadmap: Tiny Real OS Prototype

## Status And Goal

This is a forward roadmap. The current release is v39.0.0; v40 remains a
planned milestone.

The goal is to turn the current QEMU-only BogKernel proof into a tiny but
credible research OS prototype. The target remains deliberately narrow:
QEMU i686, bounded resources, deterministic verification, and receipt-visible
acceptance or rejection. BogOS v40 must not be described as production-ready,
POSIX-compatible, physical-hardware-capable, or a general-purpose OS.

The verifier-first rule remains central: device bytes, filesystem state, and
applications become trusted state only after their declared structure,
bounds, hashes, versions, and policy have been verified.

## Roadmap Contract

Each major version is implemented in its own PR. A milestone is complete only
when its implementation, milestone document, evaluator, negative proof
matrix, checked-in receipts/artifacts, README, PROJECT_STATUS, and
RELEASE_NOTES agree. Positive-path output alone is not completion evidence.

Each evaluator must run its own QEMU scenario, verify prerequisite milestone
evidence, parse deterministic serial receipts, and emit a JSON summary receipt
containing input hashes, evaluator hash, serial-log hash, accepted evidence,
rejected evidence, preserved guarantees, and explicit boundary flags.

| Version | Plain-English claim | Depends on |
| --- | --- | --- |
| v36.0.0 (implemented) | BogKernel can safely read and write verified sectors on one QEMU disk image. | v35.0.0 and v35.1 audit evidence |
| v37.0.0 (implemented) | BogKernel can mount, update, reboot, and remount one fixed file in a tiny persistent verified BogFS. | v36 |
| v38.0.0 (implemented) | Persistent BogFS has a bounded flat `/data` namespace and receipt-visible file lifecycle operations. | v37 |
| v39.0.0 (implemented) | A verified zero-capability app can be loaded from persistent BogFS into an isolated Ring 3 process. | v38, v32-v35 |
| v40.0.0 (Phase D complete) | v40.0.0 introduces the Genesis Workspace Root: a persistent BogFS workspace whose user-facing paths are mutable, but whose trusted state is an append-only chain of deterministic root transitions and verifier receipts. Phase D: GenesisRoot persisted as well-known object in existing v37/v38 manifest; boot/mount validation + receipt-chain survival proven (oracle + image mutation + kernel load). See [docs/v40_genesis_workspace_root.md](v40_genesis_workspace_root.md). The previous "usable persistent shell / two-boot demo" framing is deferred to v41+. | v36-v39 |

## v36.0.0: Verified Block Device Model

**Claim:** BogKernel can perform bounded, receipt-visible sector reads and
writes against one QEMU-attached block image, rejecting corruption and
unauthorized writes.

The reference device is QEMU legacy IDE/ATA PIO, primary master, LBA28, with a
raw fixed-size image and 512-byte sectors. The kernel supports one device and
single-sector synchronous reads and writes. Block access remains kernel
internal; v36 adds no Ring 3 raw-block syscall.

Every accepted read hashes the complete sector and compares it with an
expected SHA-256. Every accepted write requires an admitted LBA, expected
pre-write hash, expected post-write hash, completed write, read-back, and
post-write hash verification. Writes are restricted to a declared proof-data
range; metadata/protected and out-of-range sectors reject.

Minimum components, evaluator cases, receipts, and exact non-goals are defined
in [v36_block_device_plan.md](v36_block_device_plan.md).

**Done when:** clean-image reads and writes are deterministic across QEMU
runs; absent-device, invalid-LBA, protected-sector, stale-preimage, corrupt
read, and failed-read-back cases reject without an accepted mutation claim;
and v31-v35 behavior remains intact.

## v37.0.0: Persistent Verified BogFS

**Claim:** BogKernel can mount, verify, update, reboot, and remount a tiny
persistent BogFS stored on the v36 block device.

The on-disk format uses two superblock slots, two manifest slots, fixed-size
file records, and append-only data extents. A verified root binds format
version, generation, manifest location/hash, file records, content hashes, and
versions. Mount verifies both roots and selects the highest valid generation.

The implemented v37 path is a separate kernel boot proof; v35 Syscall ABI v2
calls 17-19 remain backed by the in-memory table. Commit order is new data and
read-back verification, inactive manifest and verification, then inactive
superblock last. The previous root remains available as fallback. This
provides a bounded recovery design, but v37 claims only clean reboot
persistence; sudden power-loss atomicity and sector atomicity are not proven.

See [v37_persistent_bogfs_plan.md](v37_persistent_bogfs_plan.md).

**Implemented evidence:** boot one writes the sole fixed file, boot two mounts
the resulting image and verifies the same versioned bytes, and corrupted state
rejects or falls back without accepting unverified data.

## v38.0.0: Flat Data File Lifecycle

**Claim:** Persistent BogFS supports a bounded flat `/data` namespace and
receipt-visible file lifecycle operations.

The filesystem gains canonical protected directory records plus create,
delete, list, read, write, and stat behavior for flat `/data` files. User mutation is restricted to `/data`; `/system`,
`/apps`, and `/receipts` remain protected. Paths are absolute canonical ASCII
paths with no NUL, repeated slash, `.` or `..`, trailing slash except root,
aliases, or overlong components.

Deletion commits a tombstone and new manifest generation. Old extents are not
securely erased. Only the immediately previous committed root is preserved as
a recovery fallback; v38 adds no user rollback API.

See [v38_file_lifecycle_plan.md](v38_file_lifecycle_plan.md).

**Done when:** directories and files can be created, listed, written, read,
statted, deleted, rebooted, and verified, with every accepted or rejected
mutation visible in receipts.

## v39.0.0: App Format v2 And Disk-Loaded Apps

**Claim:** BogKernel can verify, admit, isolate, and run applications loaded
from persistent BogFS.

`.bogapp` v2 remains a bounded custom binary container rather than ELF. Its
manifest binds identity, layout, entrypoint, requested capabilities, launch
limits, code SHA-256, and manifest SHA-256. Loading binds admission to the
BogFS path, file version, file hash, filesystem root hash, manifest hash, and
code hash. Any stale or changed source rejects before PID allocation.

Accepted apps retain v31 private CR3 address spaces, read-only executable
pages, private writable runtime data/stack, and scheduler admission. Launch
arguments, environment, and a read-only launch page remain deferred.

See [v39_disk_loaded_apps_plan.md](v39_disk_loaded_apps_plan.md).

**Implemented evidence:** a v2 app stored only on persistent BogFS survives
reboot, is verified from disk, runs as an isolated process, and malformed,
stale, or unsupported variants receive no PID, admission, or execution record.

## v40.0.0: Genesis Workspace Root

**Claim:** v40.0.0 introduces the Genesis Workspace Root: a persistent BogFS workspace whose user-facing paths are mutable, but whose trusted state is an append-only chain of deterministic root transitions and verifier receipts.

See the canonical plan document: [docs/v40_genesis_workspace_root.md](v40_genesis_workspace_root.md).

v40 is now Genesis Workspace Root.
Previous shell/user-comfort/two-boot demo work is deferred to v41+ or later.
v40 does not include package manager, full .bogapp evolution, self-hosting, rich TS graph engine, or shell comfort layer.

This milestone focuses on the hash-rooted persistent workspace model (GenesisRoot, WorkspaceRoot, materialized WorkspaceState + WorkspacePathEntry, WorkspaceOperation / WorkspaceReceipt, canonical serialization and hashing rules with domain tags, strict v40 bounds, operation semantics for CreateDirectory/CreateFile/EditFile, receipt chain invariant, and the 10 non-negotiable invariants).

The previous "usable persistent shell demo / two-boot demo" framing (bounded fs commands, visible shell, full evaluator for shell + app run across reboots) is deferred to v41 or later.

v40 does not include a package manager, full .bogapp evolution, self-hosting, rich TS graph engine, shell/user-comfort layer, or kernel-as-file-manager semantics. Kernel/BogFS persistence integration (GenesisRoot as well-known object in the existing manifest) is planned for the next phase.

See [v40_genesis_workspace_root.md](v40_genesis_workspace_root.md) for the full model, Python oracle contract, golden vectors, invariants, and acceptance criteria.

**Done when:** the pure model, canonical forms, 10 invariants as passing tests, independent Python oracle + --check mode, golden vector agreement (Python/Rust), required vector name presence (stale protection), and the documented receipt-chain proofs are complete. Persistent BogFS storage of the latest accepted GenesisRoot is the follow-on integration step.

## Explicit Cross-Version Non-Goals

The v36-v40 ladder does not add physical hardware support, a general disk
driver stack, POSIX compatibility, production reliability, networking,
production userland, users or ACLs, demand paging, swapping, ASLR, full ELF,
dynamic linking, shared memory, blocking IPC, SMP, or secure deletion.

The required v40 public wording is:

> BogOS v40 is a tiny QEMU-only i686 research OS prototype.

Any v40 status text must immediately state that it is not production-ready,
not POSIX-compatible, and does not support physical hardware.

## First Implementation PR

The first implementation PR was v36 only: it added the bounded ATA PIO single-sector
block abstraction, deterministic raw-image builder and corruption fixtures,
sector read/write/read-back receipts, the complete v36 evaluator, and checked
artifacts. It must not introduce persistent BogFS, user raw-block syscalls,
directories, or disk-loaded apps.

## Documentation Alignment Notes

- `README.md` previously described v34 as the next target inside the v33
  summary even though v34 and v35 are implemented; roadmap documentation
  removes that stale forward-looking wording.
- `PROJECT_STATUS.md` previously named post-v35 hardening as the current
  development target even though the v35.1 audit is present; v36 is now
  implemented, v37-v39 are now implemented, and v40 remains forward roadmap
  work.
- v35 and v35.1 evaluators currently derive their native evidence from the
  shared v30 QEMU serial artifact. v36 onward must use standalone milestone
  QEMU scenarios.
- Historical next-target language in old release notes remains historical and
  is not rewritten.
- The v40 section was aligned in this document to reflect the locked Genesis
  Workspace Root plan (see docs/v40_genesis_workspace_root.md). The older
  "usable persistent shell / two-boot demo" framing (previously in
  v40_tiny_os_demo_plan.md) is now noted as deferred to v41+. Useful
  historical notes in the old v40 plan document are retained for context but
  the canonical v40 reference is the Genesis doc.
