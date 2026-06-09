# BogKernel

This directory contains the native Rust implementation of the BogKernel and BOGVM core.

## Components

- **bogk-core:** A `no-std` Rust library containing the BOGVM bytecode executor and receipt models.
- **bogk-kernel:** A bare-metal i686 32-bit x86 kernel that boots via Multiboot1 and provides the runtime for `bogk-core`.

## Design Principles

1. **Deterministic Execution:** The native VM must produce identical results to the Python reference implementation.
2. **Minimal TCB:** Avoid dependencies and dynamic allocation in the core execution path.
3. **Receipt-Oriented:** Every boot and execution emits signed/deterministic evidence.

## Getting Started

See [docs/v16_bootable_bogkernel.md](../docs/v16_bootable_bogkernel.md) for build and run instructions.
