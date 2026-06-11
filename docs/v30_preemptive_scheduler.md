# BogOS v30: Timer-Preemptive Verified Scheduler

BogOS v30 implements timer-preemptive scheduling on top of the v29 saved-user-context system. A user-mode Ring 3 process is preempted when its quantum expires, saving its context and resuming other processes in a round-robin fashion.

## Process State Extension

`ProcessState` has been extended with the `PREEMPTED` state. When a running process's quantum expires, it is marked as `PREEMPTED`, then transitioned back to `READY` to be rescheduled.

## Scheduler Quantum Tracking

The scheduler tracks execution statistics to enforce quantum limits:
- `timer_ticks`: Total number of timer interrupts since boot.
- `quantum_ticks`: Number of timer interrupts accumulated by the currently running process.
- `preemption_count`: Total number of preemptions across all processes.
- `current_pid`: PID of the currently running process.
- `last_preempted_pid`: PID of the last process that was preempted by the timer.

## Preemption Mechanism

On each IRQ0 timer interrupt, the kernel checks:
1. If a process is currently running (`current_pid` is not `None`).
2. If the interrupted context is in Ring 3 (user-mode). This is verified by checking the low two bits of the CS selector: `(cs & 3) == 3`.

If both conditions are met, `quantum_ticks` is incremented. When `quantum_ticks` reaches the quantum threshold (`SCHEDULER_QUANTUM = 2` ticks):
- The interrupted Ring 3 context is saved from the timer interrupt stack frame into the process's `SavedContext`.
- The process state is transitioned: `RUNNING` -> `PREEMPTED` -> `READY`.
- A deterministic `BOGOS_PREEMPT` receipt is emitted.
- `quantum_ticks` is reset.
- `preemption_count` is incremented.
- `last_preempted_pid` is updated.
- The kernel returns directly to the scheduler loop to select the next READY process.

Non-preemptable processes (kernel, internal, terminal, or demo processes running in Ring 0) are never preempted.

## Context Restore Reuse

The preemption model fully reuses the v29 context restore path. A preempted process resumed by the scheduler has its saved registers and CPU state restored via an `iretd` frame, resuming execution exactly at the interrupted EIP and ESP.

## Receipts

### Preemption Receipt

When a process is preempted, the kernel emits a deterministic preemption receipt:

```text
BOGOS_PREEMPT_BEGIN
TICK=<n>
PID=<pid>
EIP=<hex>
ESP=<hex>
STATE_BEFORE=RUNNING
STATE_AFTER=READY
REASON=timer_irq
PREEMPTION_COUNT=<n>
BOGOS_PREEMPT_END
```

### Extended Scheduler Receipt

Scheduler receipts are extended to identify the reason selection follows:
- `spawn`: Selection after a new process is spawned.
- `yield`: Selection after a process cooperatively yields via `sys_yield`.
- `preemption`: Selection after a process is preempted by the timer.
- `exit`: Selection after a process exits.
- `block`: Selection after a process blocks (e.g. page fault or GPF).

## System Information

The `/system/scheduler` pseudo-file has been extended to expose:
- `quantum_ticks`
- `timer_ticks`
- `preemption_count`
- `current_pid`
- `last_preempted_pid`

## Assembly Interleaving

Native assembly apps `preempt_a.s` and `preempt_b.s` run a CPU-burning loop to verify timer preemption. Using QEMU's instruction-accurate counting (`-icount shift=3,align=off`), preemption occurs at completely deterministic instruction boundaries, resulting in the interleaved output:

```text
A1
B1
A2
B2
```

## Verification

To run the preemptive scheduler validation and unit tests:

```bash
python3 scripts/evaluate_v30_preemptive_scheduler.py
cd kernel && cargo test -p bogk-core
```

## Boundaries

- QEMU-only prototype.
- No priority scheduling; simple round-robin FIFO.
- No IPC or networking.
- No writable persistent BogFS.
- No threads or multicore.
