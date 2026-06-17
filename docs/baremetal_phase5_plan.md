# Bare-Metal Phase 5: Userspace Foundation (Init, Shell, Runtime)

## Claim And Dependency

Minimal interactive environment: init, shell, userspace syscall library. Depends
on Phase 3–4 and v33 syscall ABI. Implements deferred shell work from
[v40_tiny_os_demo_plan.md](v40_tiny_os_demo_plan.md).

## Technical Scope

- Init as first Ring 3 process
- `userspace/bogsh/` — bounded 256-byte command lines
- `userspace/boglibc/` — syscall ABI v2 wrapper
- Builtins: `help`, `ls`, `stat`, `cat`, `write`, `run`, `receipt`
- Console via keyboard + screen (not serial-only)

## Minimum Components

- `scripts/evaluate_phase5_userspace_shell.py`
- Shell negative matrix (protected paths, overflow, invalid commands)

## Receipts

`BOGBIN_PHASE5_USERSPACE_BEGIN/END`, per-command `BOGBIN_SHELL_CMD` blocks.

## Explicit Non-Goals

Full POSIX shell, scripting, pipes, job control, networking.

## Done When

Init → shell → `run hello.bogapp` on real hardware with keyboard + screen;
negatives reject deterministically.