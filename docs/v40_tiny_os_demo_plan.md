# BogOS v40 Plan: Usable Persistent Shell Milestone (DEFERRED)

**Note:** This document described the pre-v40 "usable persistent shell / two-boot demo" framing. Per the locked v40 alignment (see docs/roadmap_v36_to_v40_tiny_os.md and the canonical [docs/v40_genesis_workspace_root.md](v40_genesis_workspace_root.md)), v40 is now the Genesis Workspace Root model. The shell/demo work is deferred to v41+. This file is retained for historical context; do not treat its claims as the current v40 plan.

## Claim And Dependency

BogOS v40 is a tiny QEMU-only i686 research OS prototype. It combines the
v36-v39 verified block, persistent filesystem, lifecycle, and disk-loaded app
proofs into one visible two-boot demo. It is not production-ready.

## Shell And Demo Scope

Extend the existing bounded BogKernel shell with:

| Command | Behavior |
| --- | --- |
| `fs ls <path>` | List deterministic immediate children |
| `fs cat <path>` | Read and display bounded verified file bytes |
| `fs write <path> <text>` | Commit bounded bytes to an existing file |
| `fs touch <path>` | Create an empty file |
| `fs rm <path>` | Delete a file under policy |
| `run <app> [args]` | Verify and run a persistent `.bogapp` v2 |
| `receipts` | Show bounded latest receipt/root summaries |

Commands use existing kernel verification and syscalls; the shell must not
gain a raw block bypass or silently normalize invalid paths.
Shell command lines are bounded to 256 bytes. `fs cat` and `fs write` operate
on at most 256 bytes in the v40 demo even if the underlying filesystem permits
larger files. `run` accepts at most four arguments and 128 argument bytes,
matching the v39 launch contract.

The deterministic demo has two phases:

1. Boot the canonical seeded disk, mount the verified root, list and read
   files, create/write/delete a proof file, run a disk-loaded verified app,
   display receipts, and cleanly stop QEMU with the mutated image preserved.
2. Boot that image again, mount the new root, prove the surviving file bytes,
   version, and root, prove deletion survived, rerun the disk-loaded app, and
   display prior/current root evidence.

## Evaluator, Script, And Expected Evidence

- `scripts/demo_v40_tiny_os.py` runs the visible or serial-driven two-boot
  demonstration without claiming success itself.
- `scripts/evaluate_v40_tiny_os_demo.py` runs prerequisite v36-v39 evaluators,
  executes both boots, parses all evidence, and emits the final chain receipt.
- Expected visible output includes mount status, current root prefix, sorted
  `/data` and `/apps` entries, accepted write/create/delete summaries,
  disk-loaded app output, and reboot-persistence confirmation.
- Expected serial output includes v36 block receipts, v37 mount/commit roots,
  v38 lifecycle receipts, v39 load/admit/process receipts, shell-command
  receipts, and `BOGOS_V40_CHAIN_BEGIN/END`.

Checked artifacts:

- `artifacts/bogos_v40_initial.img`
- `artifacts/bogos_v40_persisted.img`
- `artifacts/bogos_v40_boot1_serial.log`
- `artifacts/bogos_v40_boot2_serial.log`
- `artifacts/bogos_v40_tiny_os_demo_report.json`
- `artifacts/bogos_v40_tiny_os_chain_receipt.json`

The final receipt binds both image hashes, both serial hashes, both mounted
roots, lifecycle evidence, app admission/execution evidence, prerequisite
receipt hashes, evaluator hash, and boundary flags.

## Negative Matrix

The final evaluator must include or verify prerequisite evidence for mount
rejection, corrupt persisted content, protected-path mutation, invalid shell
path/traversal, duplicate create, missing delete, malformed disk-loaded app,
unsupported app capability, stale app source, and failure of any prerequisite
evaluator. Rejected commands must display a reason and preserve the trusted
root.

## Public Claim And Non-Goals

README and PROJECT_STATUS may say:

> BogOS v40 is a tiny QEMU-only i686 research OS prototype.

They must also state that it is not production-ready, POSIX-compatible,
physical-hardware-capable, or a general-purpose filesystem/OS.

No networking, production userland, POSIX shell, users/accounts, general
permissions, package manager, demand paging, swapping, ASLR, full ELF,
dynamic linking, SMP, physical hardware, or production reliability.

## Done

v40 is done only when the two-boot demo visibly works, the final evaluator
proves the complete v36-v40 evidence chain, all negative evidence remains
valid, and public documentation uses the bounded claim above.
