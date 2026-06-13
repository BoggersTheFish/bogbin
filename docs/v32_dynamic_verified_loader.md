# BogOS v32: Dynamic Verified Process Loading

## Why v32 Matters

BogOS v31 proved isolated Ring 3 execution, but its legacy `spawn` path treats
an entire BogFS file as raw executable bytes. v32 adds a separate `load`
command that discovers a structured `.bogapp` in the mounted initrd, validates
its manifest and code before PID allocation, and admits only verified code into
the existing v31 private-address-space path.

## v31 Foundation

Every admitted v32 process inherits the v31 guarantees: a distinct aligned
CR3, supervisor-only kernel and paging structures, private read-only code,
private writable runtime data and stack, CR3 switching, page-fault blocking,
and timer-preemptive scheduling.

## Minimal `.bogapp` Contract

The phase-1 format is a deterministic 136-byte big-endian header followed by
exactly the declared code bytes. The canonical container length is therefore
`136 + code_length`; trailing bytes are rejected.

| Offset | Size | Field |
| --- | ---: | --- |
| 0 | 8 | magic `BOGAPP32` |
| 8 | 4 | format version, currently `1` |
| 12 | 4 | header size, `136` |
| 16 | 4 | entrypoint offset |
| 20 | 4 | code offset |
| 24 | 4 | code length |
| 28 | 4 | required capability bits |
| 32 | 24 | NUL-terminated ASCII app name |
| 56 | 16 | NUL-terminated ASCII app version |
| 72 | 32 | expected code SHA-256 |
| 104 | 32 | SHA-256 of header bytes `0..104` |

The code offset must be the canonical, 8-byte-aligned value `136`. Code length
must be nonzero, fit the fixed v31 code slot, and add to the offset without
overflow. The entrypoint must be inside the code bounds; phase 1 further
restricts it to offset zero. App name and version fields must contain nonempty
ASCII text followed by canonical all-zero padding, so overlong or ambiguous
truncation is rejected. The capability policy is `empty_only`: any nonzero
capability request is rejected rather than silently ignored.
`scripts/pack_v32_bogapp.py` creates deterministic canonical containers.

## Verification And Admission

`load <name>` resolves `/apps/<name>.bogapp` through the mounted BogFS/initrd.
The kernel checks magic, version, exact container length, canonical text
fields, lengths, offsets, entrypoint, capabilities, manifest hash, and code
hash before creating a process record. A valid app is copied into a private
page-aligned code slot, mapped with v31 permissions, checked by the v31 mapping
invariants, assigned a PID, and enqueued.

`BOGOS_LOAD` records discovery and verification. `BOGOS_PROCESS_ADMIT` records
the isolated mapping and execution permission. Missing, malformed,
hash-mismatched, and invalid-entrypoint apps receive deterministic rejection
receipts and no PID. PID allocation occurs only after all container and hash
checks pass. Rejected dynamic apps do not receive process-admission receipts
and do not enter the scheduler.

The QEMU demo proves `/apps/dynamic_hello.bogapp` loads, receives private
mappings, runs in Ring 3, is timer-preempted, resumes, and exits. It also proves
rejection of:

- `/apps/bad_dynamic_hello.bogapp`: internal code hash mismatch;
- `/apps/malformed_dynamic.bogapp`: malformed container;
- `/apps/invalid_entrypoint.bogapp`: unsupported/out-of-bounds entrypoint;
- `/apps/missing_dynamic.bogapp`: absent from BogFS.
- `/apps/bad_magic.bogapp`: wrong container magic;
- `/apps/bad_version.bogapp`: unsupported format version;
- `/apps/zero_code_length.bogapp`: empty code payload;
- `/apps/bad_code_offset.bogapp`: noncanonical/out-of-bounds code offset;
- `/apps/bad_code_length.bogapp`: code length exceeds the container;
- `/apps/entrypoint_at_end.bogapp`: entrypoint is exactly outside code bounds;
- `/apps/unsupported_capability.bogapp`: nonempty capability request with
  otherwise valid hashes;
- `/apps/trailing_bytes.bogapp`: bytes outside the declared contract.
- `/apps/bad_manifest_hash.bogapp`: manifest hash inconsistency;
- `/apps/noncanonical_name.bogapp`: ambiguous nonzero bytes after text NUL.

## v32.1 Loader Hardening Audit

The v32.1 audit adds no new OS feature. It makes parser rejection reasons
receipt-visible, expands `BOGOS_LOAD` with contract fields, expands
`BOGOS_PROCESS_ADMIT` with mapping permissions and admission source, and makes
the evaluator fail if a rejected app receives a PID, admission receipt, or
execution record. `artifacts/bogos_v32_loader_audit_receipt.json` summarizes
the QEMU evidence while the released milestone remains v32.0.0.

## Boundaries

BogOS v32 remains a QEMU-only, i686/ELF32-adjacent experimental proof, not a
production OS. The phase-1 container is not a full ELF loader. Demand paging,
shared libraries, package-manager integration, writable persistent
filesystems, nonempty capability admission, arbitrary entrypoint offsets,
swapping, ASLR, and physical hardware support remain out of scope.
