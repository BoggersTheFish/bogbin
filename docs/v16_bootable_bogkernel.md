# Plan: v16 Bootable BogKernel in QEMU

## Objective
Establish a bootable native kernel proof in QEMU that emits a verifier-checkable serial receipt.

## Chosen Boot Route
- **Architecture:** i686 (32-bit x86)
- **Protocol:** Multiboot1
- **Format:** ELF32

### Why i686 Multiboot1?
Multiboot1 is the standard for minimal "no-std" kernels in QEMU. By using the `i686-unknown-linux-musl` target with `#![no_std]`, `#![no_main]`, and explicit linker flags (`-nostdlib`, `-e rust_start`), we can produce a bare-metal 32-bit ELF that QEMU loads and executes directly. This establishes the "boots and writes to serial" proof with the simplest possible handover.

## Build and Run
1. **Build:**
   ```bash
   cd kernel
   cargo build -p bogk-kernel --target i686-unknown-linux-musl
   ```
2. **Run:**
   ```bash
   qemu-system-i386 -kernel target/i686-unknown-linux-musl/debug/bogk-kernel -serial stdio -display none
   ```

## What Counts as Proof
The v16 milestone is successful when the kernel boots and writes the following deterministic markers to the serial port (COM1):

```text
BOGKERNEL_BOOT_BEGIN
BOGKERNEL_FORMAT=BOGKERNEL-boot-receipt-16.0
PLATFORM=qemu
EXECUTION_STATUS=completed
BOGKERNEL_BOOT_END
```

## What is Not Proven Yet
- **VM Execution:** No BOGVM opcodes are executed in this first spike.
- **Interrupts/Memory:** Hardware IRQs and dynamic memory allocation are reserved for v17/v18.
- **Drivers:** No real hardware drivers besides a minimal UART write stub.
- **Filesystem:** No BogFS or archive access.

## Separation from BogOS
The native Rust kernel lives entirely within the `kernel/` directory. It shares no code with the Python `bogvm/` implementation. The two stacks are connected only by the shared specification in `docs/bogvm_bytecode_contract.md`.

## Boundaries
- **QEMU only:** No physical hardware support or BIOS/UEFI boot paths.
- **Reference only:** This does not replace the Python/user-space BogOS stack; it provides a native alternative for the BOGVM execution layer.
