# BogOS v39: Persistent Disk-Loaded Apps

## Claim And Dependency

BogKernel can verify, admit, isolate, and run applications loaded from
persistent BogFS. It depends on v38 path/lifecycle semantics and preserves the
v31-v35 process, paging, scheduler, syscall, IPC, and file guarantees.

## `.bogapp` v2 Contract

Use a bounded custom binary format, not ELF. The canonical header is 160 bytes
and is followed by exactly the declared code bytes:

| Offset | Size | Field |
| ---: | ---: | --- |
| 0 | 8 | magic `BOGAPP39` |
| 8 | 4 | little-endian format version `2` |
| 12 | 4 | header size `160` |
| 16 | 4 | total container length |
| 20 | 4 | entrypoint offset within code |
| 24 | 4 | canonical code offset `160` |
| 28 | 4 | code length |
| 32 | 4 | requested capability bitset |
| 36 | 4 | required Syscall ABI version `2` |
| 40 | 4 | maximum argument count, at most `4` |
| 44 | 4 | maximum total argument bytes, at most `128` |
| 48 | 32 | canonical NUL-terminated ASCII app name |
| 80 | 16 | canonical NUL-terminated ASCII app version |
| 96 | 32 | expected code SHA-256 |
| 128 | 32 | SHA-256 of header bytes `0..128` |

Code length must be nonzero and fit the existing bounded private code slot.
The entrypoint may be any supported offset inside verified code. Unknown
capabilities, unknown flags, noncanonical padding, overlap, overflow, and
trailing bytes reject.

The implemented proof admits only the empty capability bitset. Capability
subsets remain deferred; no capability grants raw block access or bypasses
syscall pointer validation.

## Verified Loading And Launch Data

The loader opens `/apps/<name>.bogapp` from one stable verified BogFS root and
binds the load receipt to path, file lifecycle identity/version, file content
hash, root hash, manifest hash, and code hash. Before PID allocation it
rechecks that these values still identify the mounted source; mismatch rejects
as `stale_manifest`.

Accepted code enters the existing v31 path: distinct CR3, supervisor-only
kernel, private read-only executable pages, private writable data/stack,
mapping invariant verification, PID allocation, and v30 scheduling.

The implemented proof records launch limits in the manifest but supplies no
arguments, environment, or launch page. Those remain deferred.

The v1 initrd loader remains only as a compatibility proof path. The v39 claim
requires v2 apps loaded from persistent BogFS.

## Tools, Receipts, And Artifacts

- `scripts/pack_v39_bogapp.py` creates canonical v2 containers.
- `scripts/make_v39_disk_apps_image.py` creates the immutable persistent app
  image.
- `scripts/evaluate_v39_disk_loaded_apps.py` performs positive, stale-source,
  malformed, and isolation scenarios across persistent images.
- Extend `BOGOS_LOAD` and `BOGOS_PROCESS_ADMIT` or add v2-specific receipts
  that bind filesystem root/source version, manifest/code hashes,
  capabilities, launch-page hash, and rejection reason.
- Check in the persistent app image, serial log, malformed fixtures, and
  `artifacts/bogos_v39_disk_loaded_apps_receipt.json`.

## Rejection Matrix

Reject before PID allocation for malformed/short header, bad magic/version,
manifest hash mismatch, code hash mismatch, unsupported capability, invalid or
out-of-bounds entrypoint, zero/oversized code, invalid/overlapping offsets,
length overflow, noncanonical text/padding, trailing bytes, missing app,
wrong entry type, stale file lifecycle identity/version/hash/root, protected
app mutation attempt, and invalid launch arguments.

For every rejected app the evaluator must prove no PID, no process-admission
receipt, no address-space allocation claim, and no execution record.

## Explicit Non-Goals

No full ELF or ELF-lite claim, dynamic linking, shared libraries, ASLR, demand
paging, signatures as a new kernel trust layer, package manager integration,
network fetch, production capability security, or physical hardware.

## Done

v39 is done when a v2 app stored only on persistent BogFS survives reboot,
loads from a verified root, runs in an isolated process, and every rejection
case is proven before PID allocation.

## Implemented Boundary

The immutable image contains `/apps/hello.bogapp`,
`/apps/bad-magic.bogapp`, `/apps/bad-code-hash.bogapp`, and
`/apps/bad-capability.bogapp`. The valid app is a nine-byte i686 program that
calls Syscall ABI v2 `exit`.

Early boot verifies the v39 root, every BogFS file hash, and the app container,
then copies only verified code into bounded kernel staging. PID allocation,
private process mapping, scheduler admission, Ring 3 execution, and exit occur
later through the existing process path. No disk writes, package management,
launch arguments, shell command, full ELF, or production app support are
implemented.
