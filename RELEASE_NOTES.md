# BOGBIN / BOGVM Release Notes

## v15.0.0: Verifier-First Vertical Expansion

- Adds BogMesh signed claims, peer trust, deterministic conflict pressure, quarantine, winner, convergence, and context-split receipts.
- Adds BogPilot Swarm budgeted candidate tournaments, deterministic best-path selection, Genesis-only admission, and replay verification.
- Adds BogBoot QEMU-reference device/memory manifests and signed boot receipts.
- Adds BogIRQ device-boundary claim gating with monotonic ticks, capabilities, quarantine, hardware state roots, and verification.
- Adds `bog vertical demo` and `scripts/evaluate_verifier_first_vertical.py` for the complete signed vertical proof.

### Boundary

BogBoot and BogIRQ model QEMU/device-boundary behavior in user space. They are not a physical bootloader, driver stack, pin-level verifier, or bare-metal kernel. BogMesh is a signed local-first reference transport, not Byzantine consensus.

## v10.0.0: BogOS HyperGenesis: Portable Self-Verifying Computer

v10 turns the local Genesis world into portable, third-party-verifiable, capability-only compute.

- Adds `bog hypergenesis demo`, the complete trusted-boot-through-portable-replay flagship proof.
- Adds BogNet `.bogproof` export, clean verification, and replay with no private key material.
- Adds BogCell, a deterministic app VM whose only I/O instructions are Bog-mediated capabilities.
- Adds BogBuild, a tiny `.bogsrc` compiler with signed source, compiler, bytecode, and capability evidence.
- Adds `bog ledger verify` over both receipt history and immutable state history.
- Adds `bog state diff`, `bog state checkout`, and `bog state prove-file`.
- Adds BogPilot, where planner proposals have no authority and every action is verified or blocked.
- Adds signed-directory registry mirroring through `bog registry sync --source`.
- Adds `scripts/evaluate_hypergenesis.py`, producing the final receipt and portable `.bogproof`.

### Boundary

- BogCell is intentionally small and deterministic; it is not a general native runtime.
- Native/Python BogK apps retain the v8/v9 host-syscall boundary.
- BogPilot is a local deterministic planner demonstration. Proof authority remains with Bog.

## v9.0.0: BogOS Genesis: Verified Session OS

v9 turns the verified workspace and BogK runtime into a complete local, user-space operating environment proof.

- `bog genesis demo` executes trusted boot, signed local registry sync, lockfile verification, signed dependency-pinned installs, brokered app runs, verified state changes, forbidden-access rejection, tamper rejection, rollback, and full-session replay.
- `bog boot` records the exact workspace, trust store, installed package index, kernel state, registry, lockfile, previous proof root, and writable state root being entered.
- Genesis receipts are Ed25519-signed and chained with `previous_hash` into an append-only local transparency ledger.
- The signed local registry describes exact package versions, dependencies, bundle/tree/receipt hashes, signing key IDs, and capability requirements.
- `bog.lock` pins the registry hash/signature, trusted key IDs, exact packages, dependencies, and hashes.
- Genesis writable BogFS stores immutable content-addressed objects and copy-on-write state manifests.
- `bog rollback <receipt>` restores a prior verified state root without deleting later objects.
- `bog shell` provides controlled `status`, `install`, `run`, `fs read`, `fs write`, `ledger`, `rollback`, and `replay session` commands.
- `bog replay-session [genesis_receipt.json]` verifies the receipt chain and deterministically replays all recorded state-root transitions.
- `scripts/evaluate_genesis.py` emits `artifacts/genesis_receipt.json`.

### Boundary

- BogOS Genesis is a verifier-first operating substrate in user space, not a bootable kernel or host syscall sandbox.
- The registry is local and signed. Remote transport and version-range solving remain future work.

## v8.0.0: BogK Capability Runtime

v8 moves Bog-native apps from observed post-run policy toward brokered pre-access capabilities.

- Adds the `bog_runtime` ABI: `bog_read`, `bog_write`, `bog_env`, `bog_dependency`, and `bog_receipt`.
- `BOGOS-app-manifest-8.0` adds explicit read/write/env/dependency capabilities.
- `bog kernel run --brokered <app>` verifies package, dependency, signature, and app policy state before starting a brokered process.
- BogK re-verifies the app package and authorizes each official I/O request before access, then emits ordered `BOGK-capability-syscall-receipt-8.0` nodes.
- Final `BOGK-brokered-process-receipt-8.0` receipts link package/dependency/policy verification, syscall evidence, process output hashes, and a final proof hash.
- `bog kernel replay <receipt.json>` re-verifies current package/tree/dependency/policy state, syscall order/evidence, brokered outputs, and the final proof hash.
- `scripts/evaluate_bogk_capability_runtime.py` emits the BogK Brokered Capability Proof, including allowed operations, pre-access blocks, tamper-before-start rejection, and replay.
- Current BogK state and operation receipts use `8.0` formats; existing `BOGK-state-7.0` workspaces migrate on open.

### Boundary

- Brokered Bog-native apps use BogK as their official I/O path.
- Brokered mode is not a host-kernel sandbox. Arbitrary direct native syscalls remain outside BogK's prevention boundary.
- Legacy app execution remains post-run checked.

## v7.0.0: BogK User-Space Kernel Contract

v7.0.0 adds BogK, a user-space kernel contract for verified workspace operations over BogOS Lite.

The final v7.0.0 release also adds:

- Draft 2020-12 schemas and runtime validation for archive manifests, decoded BOGPK metadata, package receipts, `bog_app.json`, common receipts, and BogK receipts.
- Ed25519-signed package receipts, workspace trust stores, and trusted-signature enforcement for install, verify, app run, doctor, and BogK operations.
- Explicit dependency metadata with transitive archive/tree/package/signature verification.
- `THREAT_MODEL.md`, which separates runtime policy from sandboxing and defines what counts as proof.
- `scripts/evaluate_signed_dependency_demo.py`, which emits one final proof receipt after a signed dependency/app install, BogK run, tamper rejection, and undeclared-write rejection.

The release version is `v7.0.0`. Existing BogK wire-format identifiers retain their `7.0` suffix for compatibility.

Proof:

- `bog kernel boot` creates `.bogos/kernel/state.json` with `BOGK-state-7.0`, plus kernel receipts, process records, mount records, and a JSONL syscall log.
- `bog kernel status` reports boot state, deterministic process records, visible apps/mounts, syscall count, and kernel receipt state.
- `bog kernel run <app>` delegates execution to the existing v6 verified app path and wraps the result in a deterministic `BOGK-process-receipt-7.0`.
- Tampered installed packages remain blocked before app execution.
- `bog kernel syscall read <mount> <path>` delegates to the existing verified BogFS-mounted read path and records a `BOGK-syscall-receipt-7.0`.
- `bog kernel syscall write <app> <path> <data>` only writes inside `.bogos/appdata/<app>/` when the app manifest write policy allows the path.
- Unknown apps, mounts, syscalls, unsafe paths, and undeclared writes are blocked with kernel receipts.
- `scripts/evaluate_bog_kernel_lite.py` emits `artifacts/bog_kernel_lite_report.json` and `artifacts/bog_kernel_lite_receipt.json`.

Boundary:

- BogK is a user-space kernel contract, not a real OS kernel, bootloader, bare-metal runtime, driver stack, or syscall-tracing sandbox.
- Trusted package signature/dependency verification and the v6 runtime policy remain proof authority.

## v6.0.0: Verified App Runtime Policy

v6.0 moves BogOS Lite from "is this package valid before I run it?" to "what is this app allowed to touch?"

Proof:

- `bog_app.json` app entries now define a runtime policy: app name, entrypoint, allowed files, expected hashes, permissions, environment variables, read policy, write policy, and receipt path.
- `bog app run app-name` verifies the installed package before execution, verifies manifest-declared file hashes, runs from `.bogos/appdata/<app>/`, and records a `BOGOS-app-runtime-policy-receipt-6.0` inside the app-run receipt.
- App subprocesses receive a controlled environment including `BOG_PACKAGE_DIR`, `BOG_APP_RUNTIME_DIR`, `BOG_APP_ALLOWED_FILES`, `BOG_APP_READ_POLICY`, `BOG_APP_WRITE_POLICY`, and `BOG_APP_RECEIPT_PATH`.
- Runtime writes are diffed after execution. Undeclared writes are blocked in the receipt.
- Installed package files are snapshotted before and after execution. Package mutation during app run is blocked.
- v5-style app manifests without policy fields are no longer enough for an accepted app run.

Boundary:

- This is a verified local runtime policy layer, not a kernel sandbox.
- Read policy is declared and file-hash verified, but Python subprocess execution is not syscall-traced.
- Network and subprocess permissions are not granted in v6.
- At v6.0.0, there was no remote trust, dependency solving, or signature verification.

## v5.0.0: Verified App/Package Demo

v5.0 moves the story from verified workspace to verified local software environment.

Proof:

- Packages may include `bog_app.json` with app entrypoints.
- `bog store install demo-app --name demo-app --version 1.0.0` installs a runnable app package into the verified store.
- `bog store verify demo-app-1.0.0` verifies installed package data and archive recipes.
- `bog app run demo-app` verifies the installed package before running its app command.
- If installed app files are corrupted, `bog app run demo-app` blocks before execution and records the verification failure.

Boundary:

- App execution is local subprocess execution after verification.
- This is not a sandbox, dependency solver, remote package ecosystem, or signature authority.

## v4.5.0: Public Demo Pack

v4.5 adds a one-command public proof loop.

Proof:

- `bog demo pack` creates a fixture app project inside the workspace.
- The demo archives, restores, mounts, reads through BogFS, installs into the package store, verifies, runs the app, corrupts installed data, rejects the corrupted package, and emits a final report.
- `scripts/evaluate_bogos_lite_demo.py` writes `artifacts/bogos_lite_demo_report.json` and `artifacts/bogos_lite_demo_receipt.json`.

Boundary:

- The demo pack is a deterministic local proof artifact.
- It is not a benchmark or remote trust workflow.

## v4.1.0: BogOS Lite UX Hardening

v4.1 makes the workspace inspectable.

Proof:

- `bog doctor` verifies workspace directories, archives, and installed packages.
- `bog status --verbose` reports archive, mount, package, app, receipt, and latest-receipt details.
- `bog receipt latest` is an explicit alias for the latest receipt.
- `bog corrupt-test package` mutates installed data and verifies that Bog rejects it.
- `bog workspace tree` prints workspace archives, mounts, packages, apps, receipts, and restored entries.

Boundary:

- UX hardening improves local observability; it does not add kernel, driver, or remote registry behavior.

## v4.0.0: BogOS Lite

v4.0 adds a user-level Bog-managed workspace. This is not a kernel, BIOS, bootloader, or driver milestone.

Proof:

- `bog init workspace` creates `.bogos/` workspace state, archive storage, receipt storage, and a local package store.
- `bog archive project/` stores a project as a verified Bog archive under the workspace.
- `bog restore archive` restores a workspace archive exactly and records a receipt.
- `bog fs mount archive name` verifies and records a read-only BogFS mount.
- `bog fs read mount path` reconstructs bytes from recipes and records a read receipt.
- `bog store install package` packages a source directory when needed, installs it into the workspace store, and records receipts.
- `bog store verify package` verifies installed package data and package archive recipes.
- `bog status` reports archives, mounts, packages, receipts, and the latest receipt.
- `bog receipt` prints the latest receipt.
- The killer-demo test archives a mixed project, restores it, installs it, reads it through BogFS, corrupts installed data, verifies again, and gets a blocked receipt explaining the hash mismatch.

Boundary:

- BogOS Lite is user-space workspace management.
- BogFS remains read-only.
- At v4.0.0, the package store was local and did not resolve dependencies, fetch remotes, or verify signatures.
- Rejection receipts explain local verification failure reasons; they are not legal/security attestations.

## v3.0.0: Bog Package Store

v3.0 adds local verified recipe bundles.

Proof:

- `python3 -m bogvm store package` builds a bundle from a source directory archive and writes a package receipt.
- `python3 -m bogvm store install` verifies the bundle receipt, restores the archive, checks the tree hash, and records the package in `index.json`.
- Install receipts include package key, archive tree hash, bundle hash, restored tree hash, and execution status.

Boundary:

- No dependency solver yet.
- No remote registry yet.
- No signature authority yet.
- Package installs are verified local recipe-bundle installs.

## v2.5.0: BogFS Prototype

v2.5 adds a read-only filesystem-style layer over BOG directory archives.

Proof:

- `BogFS.listdir()` enumerates archive entries.
- `BogFS.stat()` returns path, size, and SHA-256.
- `BogFS.read_bytes()` and `read_text()` reconstruct file bytes from `.bogpk` recipes and verify object hashes.
- CLI access is available through `python3 -m bogvm fs ls|stat|cat`.

Boundary:

- This is a userspace read API and CLI, not a kernel mount.
- Writes are not supported.

## v2.0.0: Directory Roundtrip

v2.0 adds the first proper folder milestone.

Proof:

- `python3 -m bogvm archive source archive_dir --receipt ...` stores each file as a verified `.bogpk` object and writes a deterministic manifest.
- `python3 -m bogvm restore archive_dir output_dir --receipt ...` reconstructs every file and verifies file hashes plus the whole tree hash.
- Tests cover a mixed folder containing a small website, Python file, image-like bytes, audio-like bytes, text, JSON, and binary data.

Boundary:

- Archive manifests and tree hashes verify directory reconstruction outside the VM.
- File object reconstruction still uses the existing BOGPK recipe path.

## v1.9.0: Real Corpus Smoke

v1.9 keeps the deterministic real-file smoke active on text, JSON, binary, PNG, and WAV fixtures.

Proof:

- `scripts/evaluate_real_file_roundtrip.py` emits a v2.0-format report and receipt.
- Every case packs to `.bogpk`, compiles to `.bogbin`, runs through BOGVM verification, unpacks, and matches SHA-256.

Boundary:

- This is a correctness smoke, not a benchmark suite.

## v1.8.0: Transform Tournament Upgrade

v1.8 changes transform selection from residual-density-only selection to cost-aware selection.

Proof:

- Candidate plans carry scoring metadata.
- Scoring includes estimated packed container size, residual count, transform cost, basis cost, and decode cost.
- Tie-breaking remains deterministic.

Boundary:

- Costs are deterministic estimates for choosing plans, not measured CPU timings.

## v1.7.0: BOGPK Hardening

v1.7 makes the binary parser defensive.

Proof:

- Rejects bad magic.
- Rejects non-minimal, oversized, and truncated varints.
- Rejects reserved flags, transform IDs, and basis IDs.
- Rejects residual offsets outside implied chunk length.
- Rejects impossible chunk counts and residual totals.
- Rejects invalid bitmask offsets and bad BWT transform params.
- Rejects trailing bytes and whole-payload hash mismatches.

Boundary:

- Optional per-chunk hash streams remain reserved in this implementation.

## v1.6.0: Binary-Packed BOGPK Container

v1.6 adds the first binary-packed `.bogpk` container path beside JSON `.bog`.

Proof:

- Transform and basis selections are packed into one descriptor byte.
- Chunk offsets are implicit from chunk index and selected chunk size.
- Residual patch offsets are delta-coded.
- Dense residual patches can use per-chunk bitmasks.
- Repeated zero-residual chunks can be encoded as zero-run records.
- `.bogpk` byte streams decode back into normal chunk plans and feed the existing compile/unpack paths.
- Sorting transforms `mtf`, `bwt`, and `bwt_mtf` are included in the transform tournament.

Report:

- JSON `.bog` mean container/input ratio: `38.548519`
- Current `.bogpk` mean container/input ratio: `0.960163`
- Aggregate `.bogpk` container size smaller than input: `true`
- All `.bogpk` containers smaller than input: `false`
- Exact roundtrip: 5/5

Boundary:

- The aggregate compression threshold is crossed, but per-file threshold is not crossed for every fixture.
- No entropy coding yet.
- VM proof authority remains hash-gated acceptance.

## v1.5.0-dev: Reversible Transform Tournament

v1.5 development executes the first reversible transform tournament and adds a bounded integer-only Fourier-style basis.

Proof:

- Candidate transforms are evaluated deterministically before basis selection: `identity`, `xor_previous`, `delta_previous`, `nibble_split`, `mtf`, `bwt`, and `bwt_mtf`.
- Each transformed chunk is optimized with the existing residual basis tournament.
- The compiled VM verifies transformed chunk bytes with `VERIFY_HASH` + `ACCEPT_DATA`.
- Container unpacking inverts the selected transform and verifies both original chunk SHA-256 and whole-payload SHA-256.
- `fourier8_u8` uses fixed 8-step integer sine/cosine lookup tables and integer arithmetic only.
- The report emits compression-threshold evidence instead of claiming victory.

Report:

- v1.2 mean residual density: `0.631188`
- v1.4 transform-free report density: `0.576098`
- Current transform-enabled mean residual density: `0.469867`
- Exact roundtrip: 5/5
- All `.bog` containers smaller than input: `false`

Boundary:

- Not a compression victory claim.
- Not a claim that `.bog` beats ZIP/PNG/WAV/etc.
- Fourier support is one bounded integer-only basis, not a full spectral compressor.
- TS-BIOS and bare-metal execution remain roadmap work.

## v1.4.0: Reversible Transform Framing and Verification Hardening

v1.4.0 frames the next storage path around reversible transform selection plus exact verification hardening. It updates the current execution path and real-file report without making a compression victory claim.

Proof:

- Verifier-rejected claim acceptance is repaired into deterministic rejected and quarantined claim state.
- Unverified or abstained claim acceptance remains blocked by `LAW_002`.
- Residual optimizer output is replay-checked before use: basis synthesis plus residual patches must reconstruct the target SHA-256 exactly.
- The real-file report now evaluates deterministic text, JSON, binary, valid PNG, and valid WAV payloads.
- The staged v0.2-v0.6 audit is documented against the BOGBIN-0.1 VM laws.
- No reversible transform tournament report/receipt artifact is generated in this release.

Report:

- v1.2 mean residual density: `0.631188`
- Current mean residual density: `0.576098`
- Residual density delta from v1.2: `-0.05509`
- Residual density improved from v1.2: `true`
- Exact roundtrip: 5/5

Verification:

~~~bash
python3 -m unittest discover -s tests
python3 scripts/evaluate_real_file_roundtrip.py
~~~

Boundary:

- Reversible transform selection is release framing and boundary-setting here; tournament implementation/reporting remains future work.
- Contradiction repair only applies after verifier result `rejected`.
- Unverified acceptance remains blocked.
- Valid PNG/WAV fixtures are deterministic small fixtures, not compression benchmarks.
- Exactness remains verified through BOGVM and SHA-256 checks.

## v1.3.0: Adaptive Chunk Tournament

v1.3.0 adds deterministic adaptive chunk-size selection.

Proof:

- Container packing can evaluate chunk sizes `16`, `32`, `64`, and `128`.
- Candidate plans are scored by total residual count, residual density, chunk count, then chunk size.
- `.bog` metadata records whether the tournament was enabled, candidate chunk sizes, selected chunk size, selected residual count, selected density, and per-candidate results.
- `python3 -m bogvm pack input.bin output.bog --auto-chunk --receipt ...` enables the tournament.
- Explicit `--chunk-size` behavior is preserved.
- Exact roundtrip remains 5/5 on the real-file report.

Report:

- v1.2 mean residual density: `0.631188`
- Current mean residual density: `0.555693`
- Residual density delta from v1.2: `-0.075495`
- Residual density improved from v1.2: `true`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 scripts/evaluate_real_file_roundtrip.py
~~~

Boundary:

- Adaptive deterministic chunk-size tournament only.
- Not a compression benchmark victory.
- Not a claim that `.bog` beats ZIP/PNG/WAV/etc.
- Not Fourier.
- Not hardware execution.
- Exactness remains verified through BOGVM and SHA-256 checks.

## v1.2.0: Dictionary + Delta Bases

v1.2.0 adds deterministic bases to reduce residual density on the real-file roundtrip report.

Proof:

- `zero_block` generates all-zero chunks.
- `delta_u8` generates arithmetic byte sequences with `byte[i] = (start_byte + i * delta) mod 256`.
- The optimizer searches delta values `0..255` deterministically and chooses the best start byte for each delta.
- `dictionary_u8` and `rle_u8` are deterministic one-byte base generators for this release; exactness still comes from residual patches and SHA-256 verification.
- Tie-breaking remains residual count, basis order, then coefficient tuple.
- Exact roundtrip remains 5/5 on the real-file report.

Report:

- Baseline mean residual density: `0.867574`
- Current mean residual density: `0.631188`
- Residual density delta: `-0.236386`
- Residual density improved: `true`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 scripts/evaluate_real_file_roundtrip.py
~~~

Boundary:

- Adds deterministic bases and residual-density comparison.
- Not a compression benchmark victory.
- Not a claim that `.bog` beats ZIP/PNG/WAV/etc.
- Not Fourier.
- Not hardware execution.
- Exactness remains verified through BOGVM and SHA-256 checks.

## v1.1.0: Basis Tournament + Real File Report

v1.1.0 adds a deterministic real-file evaluation/report harness.

Proof:

- `scripts/evaluate_real_file_roundtrip.py` builds deterministic fixture files for text, JSON, binary/noise-like, PNG-like, and WAV-like payloads.
- Each case is packed to `.bog`, compiled to `.bogbin`, verified through BOGVM, unpacked, and SHA-256 compared against the original.
- The report records basis counts, residual density, chunk counts, hashes, VM run status, and roundtrip pass/fail.
- Every accepted case must recover exact bytes.

Artifacts:

- `artifacts/real_file_roundtrip_report.json`
- `artifacts/real_file_roundtrip_receipt.json`
- `docs/real_file_roundtrip_report.md`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 scripts/evaluate_real_file_roundtrip.py
~~~

Boundary:

- Real-file roundtrip report only.
- Not a compression benchmark victory.
- Not a claim that `.bog` beats existing formats.
- Not Fourier.
- Not hardware execution.
- Exactness remains verified through BOGVM and SHA-256 checks.

## v1.0.0: Exact File Roundtrip

v1.0.0 adds exact deterministic file reconstruction.

Proof:

- `reconstruct_bog_container_bytes(container)` reconstructs every chunk from basis, start byte, length, and residual patches.
- Reconstruction verifies each `chunk_sha256`.
- Reconstructed chunks are concatenated in deterministic index order.
- The final byte stream is checked against `whole_sha256`.
- `python3 -m bogvm unpack` writes recovered bytes and an unpack receipt.
- A file can complete: `input.bin -> output.bog -> output.bogbin -> verified VM run -> recovered.bin`.

Artifacts:

- `examples/roundtrip_payload.bin`
- `artifacts/roundtrip_payload.bog`
- `artifacts/roundtrip_payload.bogasm`
- `artifacts/roundtrip_payload.bogbin`
- `artifacts/roundtrip_payload_pack_receipt.json`
- `artifacts/roundtrip_payload_run_receipt.json`
- `artifacts/roundtrip_payload_unpack_receipt.json`
- `artifacts/roundtrip_payload_recovered.bin`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm pack examples/roundtrip_payload.bin artifacts/roundtrip_payload.bog --chunk-size 64 --receipt artifacts/roundtrip_payload_pack_receipt.json
python3 -m bogvm compile artifacts/roundtrip_payload.bog artifacts/roundtrip_payload.bogbin --bogasm artifacts/roundtrip_payload.bogasm
python3 -m bogvm run artifacts/roundtrip_payload.bogbin --receipt artifacts/roundtrip_payload_run_receipt.json
python3 -m bogvm unpack artifacts/roundtrip_payload.bog artifacts/roundtrip_payload_recovered.bin --receipt artifacts/roundtrip_payload_unpack_receipt.json
sha256sum examples/roundtrip_payload.bin artifacts/roundtrip_payload_recovered.bin
~~~

Boundary:

- Exact deterministic file roundtrip.
- Not compression victory.
- Not Fourier.
- Not hardware execution.
- VM verification remains proof authority.

## v0.9.0: .bog Container Compiler

v0.9.0 adds a deterministic `.bog` container format and compiler.

Proof:

- `build_bog_container(data, chunk_size=64)` creates a deterministic `BOG-0.9` JSON-compatible container.
- The container stores chunk names, offsets, lengths, basis choices, start bytes, residuals, per-chunk SHA-256 hashes, total residual count, and whole-file SHA-256.
- `write_bog_container()` writes canonical JSON with sorted keys and stable separators.
- `read_bog_container()` validates required fields and schema constraints.
- `compile_bog_container_to_bogasm()` deterministically compiles container plans into ordinary `.bogasm`.
- `python3 -m bogvm compile` assembles that `.bogasm` into `.bogbin`.
- Running the compiled `.bogbin` verifies and accepts each chunk through VM `VERIFY_HASH` + `ACCEPT_DATA`.

Artifacts:

- `examples/container_payload.bin`
- `artifacts/container_payload.bog`
- `artifacts/container_payload.bogasm`
- `artifacts/container_payload.bogbin`
- `artifacts/container_payload_pack_receipt.json`
- `artifacts/container_payload_run_receipt.json`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm pack examples/container_payload.bin artifacts/container_payload.bog --chunk-size 64 --receipt artifacts/container_payload_pack_receipt.json
python3 -m bogvm compile artifacts/container_payload.bog artifacts/container_payload.bogbin --bogasm artifacts/container_payload.bogasm
python3 -m bogvm run artifacts/container_payload.bogbin --receipt artifacts/container_payload_run_receipt.json
~~~

Boundary:

- `.bog` container compiler only.
- `.bog` is a deterministic storage/manifest container.
- `.bog` is not proof authority.
- VM verification remains proof authority.
- Not compression victory.
- Not Fourier.
- Not hardware execution.

## v0.8.0: Chunked Auto Pack

v0.8.0 adds deterministic chunked automatic packing.

Proof:

- `optimize_chunked_residual_plan(data, chunk_size=64)` splits input bytes into sequential chunks.
- Each chunk is optimized independently with the existing residual optimizer and deterministic tie-breaking.
- `pack_chunked_bytes_to_bogasm()` emits one data block per chunk: `payload_chunk_0000`, `payload_chunk_0001`, and so on.
- Every chunk is synthesized, residual-patched, `VERIFY_HASH` checked, and `ACCEPT_DATA` accepted independently by the VM.
- `python3 -m bogvm pack` defaults to chunked mode when input length is greater than `--chunk-size`.
- `--single-block` preserves the v0.7 one-block `payload` behavior.
- The pack receipt includes deterministic `chunk_count`, `chunk_size`, `total_residual_count`, and `whole_sha256`.

Whole-payload boundary:

- v0.8 does not add a whole-payload VM opcode.
- The VM verifies chunks.
- The pack receipt records the whole input SHA-256 deterministically as `whole_sha256`.
- The verifier boundary remains authoritative for accepted chunk data through `VERIFY_HASH` + `ACCEPT_DATA`.

Artifacts:

- `examples/chunked_payload.bin`
- `artifacts/chunked_payload.bogasm`
- `artifacts/chunked_payload.bogbin`
- `artifacts/chunked_payload_receipt.json`
- `artifacts/chunked_payload_run_receipt.json`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm pack examples/chunked_payload.bin artifacts/chunked_payload.bogbin --chunk-size 64 --bogasm artifacts/chunked_payload.bogasm --receipt artifacts/chunked_payload_receipt.json
python3 -m bogvm run artifacts/chunked_payload.bogbin --receipt artifacts/chunked_payload_run_receipt.json
~~~

Boundary:

- Chunked deterministic auto-pack only.
- Not a `.bog` container compiler yet.
- Not compression victory.
- Not Fourier.
- Not hardware execution.

## v0.7.0: Automatic Residual Optimizer

v0.7.0 adds a deterministic automatic pack pipeline.

Public wording:

BOGBIN v0.7 adds automatic residual optimization: arbitrary bytes can be represented as deterministic generated base + exact residual patches, then verified by SHA-256 before acceptance.

Proof:

- `bogvm.bases.synthesize_basis()` is the shared deterministic basis implementation for `repeat_byte`, `ramp_u8`, `triangle_u8`, and `sine8_u8`.
- `bogvm.optimizer.optimize_residual_plan()` exhaustively tests every existing basis and every start byte `0..255`.
- The optimizer chooses by smallest residual count, then basis order, then lowest start byte.
- `bogvm.packer.pack_bytes_to_bogasm()` emits deterministic `.bogasm` with `STORE_RESIDUAL` patches, `VERIFY_HASH`, and `ACCEPT_DATA`.
- `python3 -m bogvm pack` reads bytes, emits `.bogasm`, assembles `.bogbin`, runs BOGVM, checks the receipt accepted `payload`, and writes the receipt.

Artifacts:

- `examples/auto_pack_payload.bin`
- `artifacts/auto_pack_payload.bogasm`
- `artifacts/auto_pack_payload.bogbin`
- `artifacts/auto_pack_payload_receipt.json`
- `artifacts/auto_pack_payload_run_receipt.json`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm pack examples/auto_pack_payload.bin artifacts/auto_pack_payload.bogbin --bogasm artifacts/auto_pack_payload.bogasm --receipt artifacts/auto_pack_payload_receipt.json
python3 -m bogvm run artifacts/auto_pack_payload.bogbin --receipt artifacts/auto_pack_payload_run_receipt.json
~~~

Boundary:

- Automatic residual optimization only.
- Not a compression victory claim.
- Not Fourier yet.
- Not a `.bog` container compiler yet.
- Not hardware/laptop execution yet.
- Exactness comes from `VERIFY_HASH` + `ACCEPT_DATA` gate.

## v0.1.1: Blocked Execution Receipts

v0.1.1 makes blocked VM-law failures auditable. Contradictory programs now emit blocked receipts instead of only tracebacking.

Proof:

- `examples/contradiction.bogasm` creates support and conflict pressure on the same claim.
- `INTERFERE` reports support pressure, conflict pressure, net pressure, and tension.
- `VERIFY` rejects the claim.
- `ACCEPT` is blocked because the claim is not verified.
- The CLI writes `artifacts/contradiction_receipt.json`.

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm assemble examples/contradiction.bogasm artifacts/contradiction.bogbin
python3 -m bogvm run artifacts/contradiction.bogbin --receipt artifacts/contradiction_receipt.json || echo "blocked receipt emitted"
~~~

Boundary:

- Blocked execution is not success.
- Blocked execution is still auditable.
- No `ACCEPT` without `VERIFY`.
- Candidate graph contamination remains zero.

## v0.1.0: Minimal Wave-State Binary VM

v0.1.0 creates the first minimal BOGVM.

Proof:

- `.bogasm` source assembles into `.bogbin`.
- BOGVM executes fixed-point sparse graph-state propagation.
- `examples/proof_chain.bogasm` verifies `A -> B -> C`, then accepts `claim_A_C`.
- The VM emits `artifacts/proof_chain_receipt.json`.

Boundary:

- This is a toy VM proof, not a full operating system.
- No Fourier/generative storage yet.
- No laptop port yet.
- No direct hardware execution yet.

## v0.2.0: Hash-Gated Generative Storage Opcodes

v0.2.0 adds the first deterministic generative storage surface to BOGVM.

Proof:

- `DECLARE_BASIS repeat_byte` declares a deterministic generator basis.
- `LOAD_COEFFICIENTS` stores generation parameters instead of raw output bytes.
- `SYNTHESIZE` reconstructs a generated data block.
- `VERIFY_HASH` checks the regenerated bytes against an expected SHA-256 hash.
- `ACCEPT_DATA` only accepts generated data after hash verification.
- Bad generated data/hash paths emit blocked receipts.

Artifacts:

- `examples/repeat_byte_storage.bogasm`
- `examples/repeat_byte_bad_hash.bogasm`
- `artifacts/repeat_byte_storage.bogbin`
- `artifacts/repeat_byte_storage_receipt.json`
- `artifacts/repeat_byte_bad_hash.bogbin`
- `artifacts/repeat_byte_bad_hash_receipt.json`

Verification:

~~~bash
python3 -m unittest discover -s tests -p "test_*.py" -q
python3 -m bogvm assemble examples/repeat_byte_storage.bogasm artifacts/repeat_byte_storage.bogbin
python3 -m bogvm run artifacts/repeat_byte_storage.bogbin --receipt artifacts/repeat_byte_storage_receipt.json
python3 -m bogvm assemble examples/repeat_byte_bad_hash.bogasm artifacts/repeat_byte_bad_hash.bogbin
python3 -m bogvm run artifacts/repeat_byte_bad_hash.bogbin --receipt artifacts/repeat_byte_bad_hash_receipt.json || echo "bad hash correctly blocked"
~~~

Boundary:

- This is a deterministic toy generator, not a compression victory claim.
- Generated data is not accepted without hash verification.
- No Fourier/wave basis yet.
- No `.bog` container compiler yet.
- No laptop port yet.

## v0.3.0: Deterministic Integer Wave Basis

v0.3.0 adds the first position-dependent deterministic generator basis.

Proof:

- `DECLARE_BASIS ramp_u8` declares an integer wave-style basis.
- `LOAD_COEFFICIENTS` stores start byte and length.
- `SYNTHESIZE` reconstructs generated bytes using the rule:
  `byte[i] = (start + i) mod 256`
- `VERIFY_HASH` checks the reconstructed byte field.
- `ACCEPT_DATA` accepts only after hash verification.

Artifacts:

- `examples/ramp_u8_storage.bogasm`
- `artifacts/ramp_u8_storage.bogbin`
- `artifacts/ramp_u8_storage_receipt.json`

Verification:

    python3 -m unittest discover -s tests -p "test_*.py" -q
    python3 -m bogvm assemble examples/ramp_u8_storage.bogasm artifacts/ramp_u8_storage.bogbin
    python3 -m bogvm run artifacts/ramp_u8_storage.bogbin --receipt artifacts/ramp_u8_storage_receipt.json

Boundary:

- Integer deterministic basis only.
- No floating point.
- No Fourier basis yet.
- No compression victory claim.
- No `.bog` container compiler yet.
- No laptop port yet.

## v0.4.0: Triangle Integer Wave Basis

v0.4.0 adds the first periodic deterministic integer wave basis.

Proof:

- `DECLARE_BASIS triangle_u8` declares a periodic integer oscillator basis.
- `LOAD_COEFFICIENTS` stores start byte and length.
- `SYNTHESIZE` reconstructs bytes using a fixed integer triangle wave:
  `offsets = 0, 32, 64, 96, 128, 96, 64, 32`
  `byte[i] = (start + offsets[i mod 8]) mod 256`
- `VERIFY_HASH` gates the reconstructed byte field.
- `ACCEPT_DATA` accepts only after hash verification.
- Bad hash paths emit blocked receipts.

Artifacts:

- `examples/triangle_u8_storage.bogasm`
- `examples/triangle_u8_bad_hash.bogasm`
- `artifacts/triangle_u8_storage.bogbin`
- `artifacts/triangle_u8_storage_receipt.json`
- `artifacts/triangle_u8_bad_hash.bogbin`
- `artifacts/triangle_u8_bad_hash_receipt.json`

Verification:

    python3 -m unittest discover -s tests -p "test_*.py" -q
    python3 -m bogvm assemble examples/triangle_u8_storage.bogasm artifacts/triangle_u8_storage.bogbin
    python3 -m bogvm run artifacts/triangle_u8_storage.bogbin --receipt artifacts/triangle_u8_storage_receipt.json
    python3 -m bogvm assemble examples/triangle_u8_bad_hash.bogasm artifacts/triangle_u8_bad_hash.bogbin
    python3 -m bogvm run artifacts/triangle_u8_bad_hash.bogbin --receipt artifacts/triangle_u8_bad_hash_receipt.json || echo "triangle bad hash correctly blocked"

Boundary:

- Toy-scale integer oscillator only.
- No floating point.
- No sine/cosine lookup table yet.
- No Fourier basis yet.
- No compression victory claim.
- No `.bog` container compiler yet.
- No laptop port yet.

## v0.5.0: Fixed Integer Sine Lookup Basis

v0.5.0 adds the first sine-like deterministic lookup-table basis.

Proof:

- `DECLARE_BASIS sine8_u8` declares a fixed integer sine-like oscillator.
- `LOAD_COEFFICIENTS` stores start byte and length.
- `SYNTHESIZE` reconstructs bytes using a fixed 8-step integer sine lookup table:
  `offsets = 0, 90, 127, 90, 0, -90, -127, -90`
  `byte[i] = (start + offsets[i mod 8]) mod 256`
- `VERIFY_HASH` gates the reconstructed byte field.
- `ACCEPT_DATA` accepts only after hash verification.
- Bad hash paths emit blocked receipts.

Artifacts:

- `examples/sine8_u8_storage.bogasm`
- `examples/sine8_u8_bad_hash.bogasm`
- `artifacts/sine8_u8_storage.bogbin`
- `artifacts/sine8_u8_storage_receipt.json`
- `artifacts/sine8_u8_bad_hash.bogbin`
- `artifacts/sine8_u8_bad_hash_receipt.json`

Verification:

    python3 -m unittest discover -s tests -p "test_*.py" -q
    python3 -m bogvm assemble examples/sine8_u8_storage.bogasm artifacts/sine8_u8_storage.bogbin
    python3 -m bogvm run artifacts/sine8_u8_storage.bogbin --receipt artifacts/sine8_u8_storage_receipt.json
    python3 -m bogvm assemble examples/sine8_u8_bad_hash.bogasm artifacts/sine8_u8_bad_hash.bogbin
    python3 -m bogvm run artifacts/sine8_u8_bad_hash.bogbin --receipt artifacts/sine8_u8_bad_hash_receipt.json || echo "sine8 bad hash correctly blocked"

Boundary:

- Fixed integer lookup table only.
- No floating point.
- No runtime sine/cosine.
- No FFT yet.
- No Fourier basis yet.
- No compression victory claim.
- No `.bog` container compiler yet.
- No laptop port yet.

## v0.6.0: Residual Patching for Exact Reconstruction

v0.6.0 adds deterministic residual patching.

Proof:

- A generator can synthesize a base byte field.
- `STORE_RESIDUAL` stores deterministic byte corrections.
- `APPLY_RESIDUAL` applies corrections to the generated byte field.
- `VERIFY_HASH` gates the exact reconstructed bytes.
- `ACCEPT_DATA` accepts only after hash verification.
- Bad hash paths emit blocked receipts.

Artifacts:

- `examples/residual_patch_storage.bogasm`
- `examples/residual_patch_bad_hash.bogasm`
- `artifacts/residual_patch_storage.bogbin`
- `artifacts/residual_patch_storage_receipt.json`
- `artifacts/residual_patch_bad_hash.bogbin`
- `artifacts/residual_patch_bad_hash_receipt.json`

Verification:

    python3 -m unittest discover -s tests -p "test_*.py" -q
    python3 -m bogvm assemble examples/residual_patch_storage.bogasm artifacts/residual_patch_storage.bogbin
    python3 -m bogvm run artifacts/residual_patch_storage.bogbin --receipt artifacts/residual_patch_storage_receipt.json
    python3 -m bogvm assemble examples/residual_patch_bad_hash.bogasm artifacts/residual_patch_bad_hash.bogbin
    python3 -m bogvm run artifacts/residual_patch_bad_hash.bogbin --receipt artifacts/residual_patch_bad_hash_receipt.json || echo "residual bad hash correctly blocked"

Boundary:

- Deterministic byte residuals only.
- No automatic residual optimization yet.
- No compression victory claim.
- No Fourier basis yet.
- No `.bog` container compiler yet.
- No laptop port yet.
