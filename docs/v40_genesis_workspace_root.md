# BOGBIN v40.0.0 — Genesis Workspace Root

v40 introduces the Genesis Workspace Root: a persistent BogFS workspace whose user-facing paths are mutable, but whose trusted state is an append-only chain of deterministic root transitions and verifier receipts.

## Claim

BogKernel can persist one native `GenesisRoot` (with an associated `WorkspaceRoot`) on the verified block device / persistent BogFS, apply deterministic `WorkspaceOperation`s (CreateFile / EditFile / CreateDirectory), produce `WorkspaceReceipt`s that prove the transition, and maintain the append-only chain under the ledger root.

User-facing paths (e.g. `/bog/workspace/hello.txt`) are convenient mutable projections. The trusted state is always the root chain: old root + operation + capability + verifier → new root + receipt.

The receipt chain is the single source of truth. Replaying the receipts from genesis must reconstruct the identical final `WorkspaceState` / root hashes.

## Non-Goals

v40 does **not** include:

- Package manager or registry operations beyond the empty `package_registry_root` sentinel.
- Full `.bogapp` evolution or loader hardening.
- Self-hosting loop.
- Rich TS graph engine or content objects beyond basic File/Directory.
- Shell / user comfort layer or ergonomic path commands.
- Full capability policy engine (only a single v40 write capability sentinel is defined).
- Kernel acting as a file manager (kernel sees only old root + operation + capability → new root + receipt).
- New disk superblock / manifest format changes (GenesisRoot lives as a well-known object inside the existing v37/v38 persistent BogFS manifest).
- Demand paging, SMP, physical hardware, POSIX, networking, or production reliability.

## Core Model

The model lives in `bogk-core` as a pure deterministic implementation (passing unit tests + oracle vector agreement).

- `Hash32` — newtype wrapper around `[u8; 32]`.
- `GenesisRoot` — top-level persistent trusted workspace object containing sub-root hashes (most sentinels are empty for v40).
- `WorkspaceRoot` — hash commitment (version, object_table_hash, path_index_hash, previous_workspace_root, last_operation_receipt).
- `WorkspaceState` — materialized state used by `apply_workspace_operation` (contains the actual `objects` and `paths` arrays + counts + the `root` commitment).
- `WorkspacePathEntry` — path_hash, path_len, path_bytes (fixed 256), object_id.
- `WorkspaceObject` — object_id, object_kind, content_hash, size_bytes, created_by_operation (note: uses `created_by_operation`, not `created_by_receipt`, to avoid receipt/root hash circularity).
- `WorkspaceOperation` — op_version, op_kind, old_workspace_root, target_path_hash, input_content_hash, input_size_bytes, capability_hash, tool_receipt_hash (explicitly commits to canonical target path semantics).
- `WorkspaceReceipt` — receipt_version, operation_hash, old_workspace_root, new_workspace_root, verifier_hash, accepted.
- `ObjectKind` — File, Directory (v40 only).
- `WorkspaceOpKind` — CreateFile, EditFile, CreateDirectory (v40 only).
- `WorkspaceError` — InvalidOldRoot, PathTooLong, PathEmpty, PathAlreadyExists, PathNotFound, WrongObjectKind, ContentTooLarge, NoSlotsAvailable, InvalidCapability.

`WorkspaceRoot` is a hash commitment only. `WorkspaceState` is the materialized object graph that `apply_workspace_operation` actually mutates and from which root hashes are recomputed via `rebuild_workspace_root_from_state`.

## Canonical Serialization and Hashing

All hashing uses SHA-256 with explicit domain-separated tags (no collisions across structure types).

- Tags: `GENROOTv1`, `WSROOTv1`, `WSOBJTABv1`, `WSPATHIDXv1`, `WSOPv1`, `CAPv1`.
- Little-endian integers.
- Fixed 256-byte path fields (padded with zeros after actual length).
- No Rust struct padding; explicit byte layouts.
- `Option<Hash32>` encoded as 1-byte present flag (0/1) + 32-byte hash (zeros when absent).
- Object table: sorted by `object_id` before canonical serialization.
- Path index: sorted by canonical path bytes (length then lex) before serialization.

`canonical_operation_payload` includes the actual canonical target path bytes (not just the hash) so verifiers see exactly what is being mutated.

Empty tables produce the hash of the bare tag (e.g. `sha256(b"WSOBJTABv1")`).

## Strict v40 Bounds

- `MAX_WORKSPACE_OBJECTS = 128`
- `MAX_WORKSPACE_PATHS = 128`
- `MAX_WORKSPACE_PATH_BYTES = 256`
- `MAX_FILE_CONTENT_BYTES = 65536`
- Only `File` and `Directory` object kinds.
- Only `CreateFile`, `EditFile`, and `CreateDirectory` operation kinds.

All limits are enforced in constructors and `apply_workspace_operation`.

## Operation Semantics

- **CreateDirectory**: path must be absent, valid write capability, slots available. Creates a new `WorkspaceObject` (Directory) and a `WorkspacePathEntry`.
- **CreateFile**: path must be absent, valid write capability, `input_size_bytes <= 65536`, slots available. Creates a new `WorkspaceObject` (File) and a `WorkspacePathEntry`.
- **EditFile**: path must be present, target object must be `File`, valid write capability, `input_size_bytes <= 65536`. Creates a **new** `WorkspaceObject` for the new content and repoints the existing `WorkspacePathEntry` to it. Old object remains (content-addressed).

v40 uses a single capability sentinel: `hash_domain("CAPv1", b"write:/workspace")`.

Invalid capability, duplicate path on create, missing path on edit, editing a directory, oversized content, or no slots → `WorkspaceError` with no mutation of the old state/root.

## Receipt Chain

```
old WorkspaceState / root + WorkspaceOperation + capability
    → apply_workspace_operation(...) → new WorkspaceState / root
    → WorkspaceReceipt (operation_hash, old_root, new_root, verifier, accepted)
```

The core invariant (implemented and tested):

```
new_state = apply_workspace_operation(old_state, op, target_path)
new_root_hash = new_state.root.compute_hash()
```

The receipt commits the transition:
- `old_root_hash → new_root_hash` through `operation_hash` (which includes canonical target path bytes + content hash + size + capability + tool receipt).
- `accepted` + `verifier_hash` record the outcome.

Replaying the receipt chain from the initial blank genesis root must produce identical final `WorkspaceState` / root hashes.

## The 10 Invariants

These are non-negotiable and implemented as passing `bogk-core` tests (Phase A + oracle agreement):

1. Same genesis root + same operation = same new root.
2. Same file content + same path + same capability = same receipt hash.
3. Different content changes the workspace root.
4. Different path changes the workspace root.
5. Invalid `old_root` is rejected.
6. Invalid capability is rejected.
7. Receipt spoofing boundaries are still blocked.
8. Replaying receipts reconstructs the final workspace root exactly.
9. BogFS path view can be rebuilt from roots.
10. Cache objects never affect trusted workspace root unless promoted by receipt.

## Python Oracle and Golden Vectors

`tools/gen_v40_workspace_vectors.py` is an **independent** oracle (pure Python, no Rust calls) that recomputes the exact same canonical forms, apply logic, and hashes.

- `fixtures/v40_genesis_workspace_vectors.json` contains the golden vectors (blank + the 8 core cases: CreateDirectory, CreateFile, EditFile, full replay, bad-cap rejection, path tamper, content tamper good + mismatch).
- Each vector records: name, op_kind, target_path, input hashes/size, capability, old/expected-new root, operation hash, table/index hashes, accepted, error label.
- `--check` mode recomputes in memory and fails on any byte/hash/field mismatch or missing required name (stale-fixture / hand-edit protection).

Rust tests in `bogk-core` load the JSON and perform exact field + model verification against the oracle output.

CI-friendly commands:

```
python3 tools/gen_v40_workspace_vectors.py --check
cargo test -p bogk-core v40
```

The Python oracle is the source of truth for the contract. Rust must match.

## Kernel / Userland Boundary (Intended)

Kernel (eventual) owns only the narrow trusted spine:

- GenesisRoot load / save (as well-known object)
- WorkspaceRoot hash validation
- Basic capability check against the sentinel
- Receipt boundary protection
- Append accepted workspace receipt under ledger root
- Quarantine / reject on invalid root transition (no mutation of old root)

Userland / reference code owns:

- Path normalization
- Operation construction / formatting
- Replay tooling
- Fixture / vector generation
- Debug printing

The kernel must **not** become a file manager. It should only ever see:

old root + operation + capability → new root + receipt (accept / reject)

## Persistence Integration Plan (Future)

- GenesisRoot should initially live as a well-known object inside the existing v37/v38 persistent BogFS manifest (no new superblock region in v40).
- Latest accepted root pointer maintained in the manifest.
- Workspace receipts appended under the `ledger_root`.
- Boot / mount validates the current root and can replay the chain.
- Phase C (pure model + docs + vectors) complete. Phase D (this integration) proven: GenesisRoot as well-known manifest object + boot/mount validation + chain survival. Kernel remains narrow spine only.

## Acceptance Criteria

v40 is done when the following are proven (via passing `bogk-core` tests + oracle vector agreement):

1. Blank initial `WorkspaceState` / `GenesisRoot` can be created.
2. `CreateDirectory("/workspace")` succeeds and changes the root deterministically.
3. `CreateFile("/workspace/hello.txt", content)` succeeds with correct new object + path entry.
4. `EditFile` on an existing file creates a new object and repoints the path entry.
5. Deterministic replay of the full positive chain produces the identical final root.
6. Tamper (content, path, old_root) produces a different root or rejection.
7. Bad capability produces `InvalidCapability` with no root mutation.
8. Exact Python oracle / Rust model agreement on all vector fields (operation hash, root hashes, table hashes, acceptance).
9. Required vector names are present in the oracle JSON (stale protection).
10. (Phase D complete) Persistent BogFS stores the latest accepted `GenesisRoot` (as well-known object/record inside existing v37/v38 manifest) and the receipt chain (via workspace_root + last_op_receipt) survives reboot/remount with kernel mount validation. Proven via oracle apply, image mutation, two-boot QEMU, corruption negatives, and replay.

## Next Phases (High-Level)

- Phase D: persistent BogFS integration (GenesisRoot as well-known object in existing manifest; boot/mount validation; ledger append).
- v41: native workspace journal receipts (multi-operation history, root history inspection, rollback to previous root).
- v42: `.bogapp` manifest and loader hardening.
- v43: native archive app matching Python oracle vectors.
- v44: Receipt Broker + Verifier Registry as core userland services.
- v45: first self-hosting loop (store source, archive/package/verify, build native tools, rerun inside the OS, emit connecting receipts).

All future work must preserve the receipt chain invariant and the narrow kernel/userland boundary.