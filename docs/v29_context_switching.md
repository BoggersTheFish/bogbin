# BogOS v29 Saved User Contexts

BogOS v29 makes the cooperative v28 scheduler resumable. A Ring 3 process that calls `sys_yield` later continues at the instruction after `int 0x80` instead of restarting at its entrypoint.

## Saved Context

Each `ProcessRecord` contains a `SavedContext` with EIP, ESP, EFLAGS, EAX, EBX, ECX, EDX, ESI, EDI, EBP, and a validity flag. It also records the process execution-memory slot.

On yield, the syscall handler copies the user return state from the syscall interrupt frame, sets resumed EAX to zero, transitions `RUNNING -> YIELDED -> READY`, emits a context-save receipt, and returns to the scheduler.

When the scheduler selects a READY process with a valid context and assigned execution memory, it emits a context-restore receipt, transitions to RUNNING, reconstructs the user `iretd` frame, restores general-purpose registers, and resumes Ring 3.

## Execution Storage

Scheduler-owned processes receive one fixed 64 KiB code/data slot and one fixed 4 KiB stack slot. Slots are indexed by process-table position and remain stable across yields.

This prevents resumable processes from overwriting each other's execution images or stacks. It is bounded static separation, not paging-based security isolation; all slots still exist in the current flat address space.

The synchronous legacy `run <app>` path keeps its shared buffer because it cannot yield into the scheduler and has no resumable lifetime.

## Context Receipts

Yield emits `BOGOS_CONTEXT_SAVE_BEGIN` / `BOGOS_CONTEXT_SAVE_END` with PID, EIP, ESP, lifecycle states, and reason. Resume emits `BOGOS_CONTEXT_RESTORE_BEGIN` / `BOGOS_CONTEXT_RESTORE_END` with the restored PID and addresses.

Context receipt markers are protected from user receipt spoofing alongside process and scheduler markers.

## TS-Lang Interleaving

The v29 examples [v29_ctx_a.ts](../examples/v29_ctx_a.ts) and [v29_ctx_b.ts](../examples/v29_ctx_b.ts) emit first output, yield, resume, emit second output, and exit. The evaluator proves deterministic output order:

```text
A1
B1
A2
B2
```

## PID Numbering

PIDs are monotonic for the entire kernel boot. The auto-demo runs legacy process and scheduler checks before v28/v29 proofs, so evaluator proof PIDs may begin above 1. This is expected: earlier internal/demo processes consumed lower PIDs, and IDs are never reused.

## Verification

```bash
python3 scripts/evaluate_v29_context_switch.py
cd kernel && cargo test -p bogk-core
```

## Boundaries

- Cooperative scheduling only; no timer preemption.
- No IPC or networking.
- No real disk persistence.
- No paging-based process memory protection.
- QEMU-only prototype.
