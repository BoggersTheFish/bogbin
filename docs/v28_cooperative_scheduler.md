# BogOS v28 Cooperative Verified Scheduler

BogOS v28 adds deterministic cooperative scheduling on top of the v27 verified process table. It does not add preemption, threads, or saved Ring 3 CPU contexts.

## Policy

The scheduler policy is `fifo_round_robin_ready`.

`spawn <app>` creates and verifies a process. Accepted processes transition through `CREATED -> VERIFIED -> READY` and are appended to the run queue. `sched step` removes the first READY PID, marks it `SCHEDULED`, emits a scheduler receipt, and enters Ring 3.

Exited, blocked, rejected, and panicked records are never enqueued or selected. A yielded process transitions `RUNNING -> YIELDED -> READY` and is appended to the queue tail.

## Cooperative Yield

Syscall 7 is `sys_yield()`. TS-Lang apps can request it with:

```ts
yield();
```

The syscall returns control to the kernel and requeues a scheduler-owned process. v28 does not save the user CPU context, so selecting that PID again restarts the app at its entrypoint.

## Shell

- `ps`: render `/system/processes`.
- `spawn <app>`: create, verify, and enqueue an app.
- `runq`: render scheduler state.
- `sched step`: select and execute one READY process.
- `sched demo`: perform four deterministic scheduler steps.
- `run <app>`: preserve the direct v27 execution path.

## Scheduler State And Receipts

`/system/scheduler` reports `current_pid`, deterministic `run_queue`, `selected_policy`, `schedule_step`, and `last_selected_pid`.

Each explicit step emits:

```text
BOGOS_SCHED_BEGIN
SCHED_STEP=<n>
POLICY=fifo_round_robin_ready
PREVIOUS_PID=<pid or none>
SELECTED_PID=<pid or none>
RUN_QUEUE=[comma-separated pids]
SELECTED_STATE=<SCHEDULED or none>
BOGOS_SCHED_END
```

Existing v27 process receipts remain authoritative for each process lifecycle.

## Verification

```bash
python3 scripts/evaluate_v28_scheduler.py
cd kernel && cargo test -p bogk-core
```

The evaluator proves deterministic selection of two runnable apps, cooperative requeue after yield, a Ring 3 block, terminal-process exclusion, and both scheduler/process pseudo-files.

## Boundaries

- QEMU-only.
- No timer-driven preemption.
- No saved CPU contexts or true concurrent multitasking.
- No threads, IPC, networking, or real disk persistence.
