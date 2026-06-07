# Bog App ABI and Capability Runtime

Bog-native v8 apps import:

```python
from bog_runtime import bog_dependency, bog_env, bog_read, bog_receipt, bog_write
```

- `bog_read(path)` requests package-file bytes.
- `bog_write(path, data)` requests an appdata write.
- `bog_env(name)` requests a declared environment value.
- `bog_dependency(package)` requests verified dependency evidence.
- `bog_receipt()` requests the process's current capability receipt nodes.

`bog kernel run --brokered <app>` starts a mode-`0600` local Unix-socket broker and gives the app a short-lived capability token. The app manifest must use `BOGOS-app-manifest-8.0` and declare:

```json
{
  "capabilities": {
    "read": ["README.txt"],
    "write": ["run.log"],
    "env": ["BOG_PROOF_DEMO"],
    "dependencies": ["proof-lib-1.0.0"]
  }
}
```

BogK re-verifies the app package and authorizes each request before performing it. Allowed and blocked requests both become `BOGK-capability-syscall-receipt-8.0` nodes. The final `BOGK-brokered-process-receipt-8.0` links package verification, dependency verification, app policy, ordered syscall evidence, process outputs, and a final proof hash.

`bog kernel replay <receipt.json>` does not rerun arbitrary app code. It replays the declared proof chain against current verified state and confirms the same syscall sequence/evidence and final proof hash.

Brokered mode is the official I/O contract for Bog-native apps, not a host-kernel sandbox. Direct native syscalls are outside the ABI.

## Reference Proof

Run:

```bash
python3 scripts/evaluate_bogk_capability_runtime.py
```

The demo installs a signed dependency and signed app, validates the capability manifest, completes allowed read/write operations, blocks a read of an existing but ungranted file, blocks a forbidden write without creating it, replays the process proof, blocks tampered-package execution before any broker call, and emits `artifacts/bogk_capability_proof_receipt.json`.
