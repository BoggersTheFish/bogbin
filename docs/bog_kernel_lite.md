# BogK User-Space Kernel Contract

BogK is the v8.0.0 user-space kernel contract and capability runtime for verified workspace operations in BogOS Lite.

v8 adds brokered Bog-native execution and current BogK state/operation formats use the `8.0` suffix. Existing `BOGK-state-7.0` workspaces are migrated when opened.

It is not a real operating system kernel. It does not boot hardware, manage drivers, run bare metal, intercept syscalls, or provide kernel sandboxing.

## Commands

```bash
bog kernel boot
bog kernel status
bog kernel run demo-app
bog kernel run --brokered capability-app
bog kernel replay receipt.json
bog kernel syscall read demo README.txt
bog kernel syscall write demo-app run.log "kernel write"
```

## State Layout

`bog kernel boot` creates:

```text
.bogos/kernel/
  state.json
  syscall_log.jsonl
  mounts/
  processes/
  receipts/
```

- `state.json` uses `BOGK-state-8.0` and tracks boot state, deterministic process/receipt sequences, process records, syscall count, and the latest kernel receipt.
- `processes/` stores deterministic `p0001`, `p0002`, and later process records.
- `mounts/` stores kernel-visible mount records synchronized from verified workspace mounts.
- `receipts/` stores a receipt for every kernel operation.
- `syscall_log.jsonl` records each syscall-style action and result.

## Kernel Laws

- No unverified app execution.
- Every kernel operation emits a receipt.
- Unknown apps, mounts, and syscalls are blocked.
- Unsafe relative paths are blocked.
- Installed package verification remains proof authority.
- Existing v6 runtime policy remains proof authority for app execution.
- Kernel app runs delegate to `Workspace.run_app` and wrap its receipt with `BOGK-process-receipt-8.0`.
- Kernel reads delegate to the existing BogFS-backed workspace mount read path.
- Kernel writes stay inside `.bogos/appdata/<app>/` and require the path in the app manifest `write_policy.allow` list.
- Brokered reads/writes/env/dependencies require explicit v8 capabilities and are authorized before BogK performs access.
- Brokered process proof requires ordered syscall evidence and supports replay against current verified state.

## Receipts

- Boot: `BOGK-boot-receipt-8.0`
- Status: `BOGK-status-receipt-8.0`
- Process run: `BOGK-process-receipt-8.0`
- Syscall-style read/write: `BOGK-syscall-receipt-8.0`
- Brokered process: `BOGK-brokered-process-receipt-8.0`
- Brokered syscall node: `BOGK-capability-syscall-receipt-8.0`
- Replay: `BOGK-replay-receipt-8.0`
- Current common kernel receipt metadata: `BOGK-receipt-8.0`

The evaluator writes:

- `artifacts/bog_kernel_lite_report.json`
- `artifacts/bog_kernel_lite_receipt.json`

Run it with:

```bash
python3 scripts/evaluate_bog_kernel_lite.py
python3 scripts/evaluate_bogk_capability_runtime.py
```

## Boundary

BogK is a deterministic control and audit contract over existing BogOS Lite authorities. It does not claim to prevent a native process from making arbitrary host syscalls. It does not syscall-trace reads or writes. Its app-run proof authority is trusted package signature and dependency verification plus the v6 runtime policy receipt. See `THREAT_MODEL.md`.

In brokered mode, the `bog_runtime` ABI requests official I/O from BogK. BogK checks the signed package, dependencies, app policy, and explicit v8 capabilities before performing reads/writes or returning environment/dependency data. Each request becomes an ordered receipt node. Replay re-verifies those nodes and the final proof hash. Direct native syscalls remain outside this broker contract.
