# BogK User-Space Kernel Contract

BogK is the v7.0 deterministic workspace-local authority layer for BogOS Lite.

It is kernel-shaped, not a real operating system kernel. It does not boot hardware, manage drivers, run bare metal, intercept syscalls, or provide kernel sandboxing.

## Commands

```bash
bog kernel boot
bog kernel status
bog kernel run demo-app
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

- `state.json` uses `BOGK-state-7.0` and tracks boot state, deterministic process/receipt sequences, process records, syscall count, and the latest kernel receipt.
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
- Kernel app runs delegate to `Workspace.run_app` and wrap its receipt with `BOGK-process-receipt-7.0`.
- Kernel reads delegate to the existing BogFS-backed workspace mount read path.
- Kernel writes stay inside `.bogos/appdata/<app>/` and require the path in the app manifest `write_policy.allow` list.

## Receipts

- Boot: `BOGK-boot-receipt-7.0`
- Status: `BOGK-status-receipt-7.0`
- Process run: `BOGK-process-receipt-7.0`
- Syscall-style read/write: `BOGK-syscall-receipt-7.0`
- Common kernel receipt metadata: `BOGK-receipt-7.0`

The evaluator writes:

- `artifacts/bog_kernel_lite_report.json`
- `artifacts/bog_kernel_lite_receipt.json`

Run it with:

```bash
python3 scripts/evaluate_bog_kernel_lite.py
```

## Boundary

BogK is a deterministic control and audit contract over existing BogOS Lite authorities. It does not claim to prevent a native process from making arbitrary host syscalls. It does not syscall-trace reads or writes. Its app-run proof authority remains installed package verification plus the v6 runtime policy receipt.
