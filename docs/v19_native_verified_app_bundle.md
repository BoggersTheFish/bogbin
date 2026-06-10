# BOGBIN v19: Native Verified Embedded App Bundle

v19 implements native verified embedded app bundle verification and execution inside the BogKernel/BOGVM executor, gating program execution behind a cryptographic integrity check on the bare metal.

## Objective
Extend the native Rust BogKernel to support:
- **Embedded App Bundles:** Define structured metadata including name, version, expected hash, manifest, and program bytecode compiled directly into the kernel.
- **Native Hash Verification:** Compute the SHA-256 hash of the app bytecode natively and assert equality with the expected hash before execution.
- **Gated VM Execution:** If verification succeeds, execute the app bytecode. If it fails, block execution and reject the app.
- **Deterministic Receipt Markers:** Emit structured output for both the positive (accepted/executed) and negative (rejected/blocked) paths to COM1.

## Implementation Details

### Data Structures
The following structures are introduced in `bogk-core`:
- `AppManifest`: Minimal manifest metadata defining format version.
- `AppBundle`: Holds static application data (`name`, `version`, `bytecode`, `expected_hash`, `manifest`).
- `AppBundleResult`: Records verification results (`hash_match`, `accepted`, `rejected`) and execution metrics (`execution_started`, `execution_status`, `halted`).

### Verification & Execution Flow
1. **Hash Verification:** The kernel invokes `AppBundle::verify_and_execute()`, which calculates the SHA-256 hash of the `bytecode` field.
2. **Acceptance Gate:** The computed hash is compared to `expected_hash`. If they match, `accepted = true` and the bytecode is executed using `MinimalExecutor::execute`. Otherwise, `rejected = true` and execution is blocked.
3. **Receipt Emission:** The results are printed to COM1 serial console.

### Receipt Format
The results are outputted with the following serial markers:
```text
BOGKERNEL_APP_BUNDLE_BEGIN
APP_NAME=<app_name>
APP_VERSION=19.0.0
APP_PRESENT=true
APP_HASH_EXPECTED=<expected_hash_hex>
APP_HASH_ACTUAL=<actual_hash_hex>
APP_HASH_MATCH=true/false
APP_ACCEPTED=true/false
APP_REJECTED=true/false
APP_EXECUTION_STARTED=true/false
APP_EXECUTION_STATUS=completed/rejected/failed
APP_HALTED=true/false
BOGKERNEL_APP_BUNDLE_END
```

## Boundaries
- **Static App Bundles:** Bundles are statically compiled into the kernel image; no general or dynamic app loader exists.
- **No full OS:** No filesystem, scheduler, interrupts, BIOS, or general hardware drivers are implemented. This remains a bare-metal embedded VM proof.

## Verification
- Host-side validation and execution via `scripts/evaluate_bogkernel_app_bundle.py`.
- Rust unit tests in `kernel/bogk-core` covering app bundle acceptance, rejection, execution gating, and receipt determinism.
