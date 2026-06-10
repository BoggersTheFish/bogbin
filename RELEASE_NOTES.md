# BOGBIN / BOGVM Release Notes

## v17.0.0: Native Minimal BOGVM Execution

BOGBIN v17.0.0 introduces the first native BOGVM execution path inside BogKernel.

This release adds a minimal native Rust executor that decodes and executes embedded bytecode (NOOP/HALT) and emits execution receipts over serial.

### Implementation
- **Instruction Decoder:** Decodes 8-byte big-endian instructions (`>BBHHH`).
- **Minimal Executor:** Supports `NOOP (0x00)` and `HALT (0x01)`.
- **Execution Receipt:** Emits instruction count, PC advancement, and status markers to COM1.
- **Embedded Program:** The kernel now executes a static NOOP + HALT program upon boot.

### Verification
Validated with:
- `python3 -m unittest discover -v`
- `python3 scripts/evaluate_verifier_first_vertical.py`
- `python3 scripts/evaluate_bogkernel_boot.py`
- `python3 scripts/evaluate_bogkernel_vm_exec.py`
- `cd kernel && cargo test -p bogk-core`

### Boundaries
This is a narrow native VM spike:
- QEMU only
- minimal NOOP/HALT executor only
- no full VM yet
- no `VERIFY_HASH` / `ACCEPT_DATA` yet
- no interrupts yet
- no filesystem yet
- no scheduler yet
- no physical hardware support yet
- Existing Python/user-space BogOS stack remains the primary implementation.

## v16.0.0: Bootable BogKernel QEMU Spike

BOGBIN v16.0.0 introduces the first native bootable BogKernel proof.

This release adds an i686/ELF32 Multiboot1 kernel that boots under x86 QEMU and emits deterministic serial receipt markers.

### Verification
Validated with:
- `python3 -m unittest discover -v`
- `python3 scripts/evaluate_verifier_first_vertical.py`
- `python3 scripts/evaluate_bogkernel_boot.py`

### Kernel artifact audit
The v16 host-side evaluator (`scripts/evaluate_bogkernel_boot.py`) verifies:
- ELF class: ELF32
- machine: Intel 80386 / i686
- entry point: 0x100150
- no dynamic interpreter
- no dynamic section
- no undefined symbols
- QEMU boot success
- serial markers from `BOGKERNEL_BOOT_BEGIN` to `BOGKERNEL_BOOT_END` on COM1

### Boundaries
This is a narrow native kernel spike:
- QEMU only
- not a full OS
- not physical hardware support
- not a BIOS
- not a real driver stack
- not interrupt admission yet
- not VM opcode execution yet
- Existing Python/user-space BogOS stack remains the primary reference implementation.

## v15.0.0: Verifier-First Vertical Expansion

- Adds BogMesh signed claims, peer trust, deterministic conflict pressure, quarantine, winner, convergence, and context-split receipts.
- Adds BogPilot Swarm budgeted candidate tournaments, deterministic best-path selection, Genesis-only admission, and replay verification.
- Adds BogBoot QEMU-reference device/memory manifests and signed boot receipts.
- Adds BogIRQ device-boundary claim gating with monotonic ticks, capabilities, quarantine, hardware state roots, and verification.
- Adds `bog vertical demo` and `scripts/evaluate_verifier_first_vertical.py` for the complete signed vertical proof.

### Boundary

BogBoot and BogIRQ model QEMU/device-boundary behavior in user space. They are not a physical bootloader, driver stack, pin-level verifier, or bare-metal kernel. BogMesh is a signed local-first reference transport, not Byzantine consensus.
