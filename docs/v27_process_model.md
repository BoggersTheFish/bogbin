# BogOS v27 Verified Process Model

BogOS v27 inserts an explicit kernel process record between the shell `run <app>` command and Ring 3 execution. It does not add scheduling or multitasking.

## Process Lifecycle

Each run request receives a monotonic `ProcessId` and starts in `CREATED`.

- A BogFS-backed app advances to `VERIFIED` only after the existing BogFS hash gate admits it.
- A verified app advances to `RUNNING` immediately before entering Ring 3.
- A normal zero-code return advances to `EXITED`.
- A Ring 3 exception or nonzero return advances to `BLOCKED`.
- A missing or unverified app advances to `REJECTED`.
- `PANICKED` is represented for process-owned panic termination, but v27 kernel panics remain system-wide.

Records retain transition-history flags so receipts prove which lifecycle stages occurred.

## Receipts

Each run emits a deterministic block between `BOGOS_PROCESS_BEGIN` and `BOGOS_PROCESS_END`. It includes PID, app path, app SHA-256 or `none`, lifecycle flags, exit code, block reason, and terminal execution status.

The v26 `BOGOS_APP_RUN_BEGIN` / `BOGOS_APP_RUN_END` markers remain in place for compatibility. User receipt emission rejects both app-run and process receipt sentinels.

## Process Table

`bogk-core` provides a fixed-capacity 16-record `ProcessTable`. PIDs begin at 1 and increase monotonically. The read-only `/system/processes` pseudo-file renders records in PID insertion order.

## Verification

```bash
python3 scripts/evaluate_v27_process_model.py
cd kernel && cargo test -p bogk-core
```

The evaluator builds a verified BogFS initrd, boots QEMU, and checks completed, blocked, rejected, spoof-protected, and pseudo-file-visible process outcomes.

## Boundaries

- No scheduler.
- No multitasking or concurrent Ring 3 execution.
- No persistent process database.
- No real disk filesystem.
- QEMU-only prototype.
