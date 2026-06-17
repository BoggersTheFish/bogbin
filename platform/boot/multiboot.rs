//! Reference: Multiboot1 boot detection lives in the kernel crate.
//!
//! Canonical implementation: `kernel/bogk-kernel/src/boot.rs`
//!
//! Build for real-hardware USB images:
//!   cd kernel && cargo build -p bogk-kernel --target i686-unknown-linux-musl --features baremetal