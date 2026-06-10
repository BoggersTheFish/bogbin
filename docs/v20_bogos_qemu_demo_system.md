# BOGOS v20.0.0: BogOS QEMU Demo System

This document outlines the architecture, features, and scope of the v20.0.0 milestone.

## Demo Claim

> BOGBIN v20.0.0 boots a visible BogOS QEMU demo system with VGA output, shell or auto-demo commands, embedded pseudo-files/apps, verified app execution, rejected bad-app blocking, and serial proof receipts.

---

## Architecture & Features

### 1. VGA Text UI
The system initializes standard VGA text-mode memory at `0xb8000`. Upon booting, a vibrant status screen is drawn for visual inspection.

```text
BOGOS v20.0.0
Self-verifying QEMU demo system

boot: verified
kernel: online
trust rule: verify-before-accept
apps: 1 accepted / 1 rejected
storage: embedded readonly table
shell: online
```

### 2. PS/2 Keyboard Input & Auto-Demo Fallback
* A polling-based PS/2 keyboard controller receives scan codes from port `0x60` and translates them into ASCII characters.
* If no keyboard activity is detected on boot, the kernel triggers an **Auto-Demo Mode** that walks through a sequence of commands to verify system correctness deterministically.

### 3. Read-Only Pseudo-Filesystem
A static, embedded entry table provides file metadata and lookup paths for:
* `/system/status` (Readable system state)
* `/receipts/last` (Last app run receipt details)
* `/apps/hello.bogapp` (Valid embedded BOGVM bytecode app)
* `/apps/bad-hello.bogapp` (Tampered BOGVM bytecode app)

### 4. Verified App Loader
App execution is completely mediated by the Kernel-level loader:
1. Lookup app path.
2. Read bytecode and calculate SHA-256 hash.
3. Compare against the expected manifest hash.
4. If it matches: accept and execute the program.
5. If mismatch: reject, prevent execution, and display a visual block screen.

### 5. Kernel-Controlled App Output
The app cannot write directly to memory or hardware. Execution returns a descriptor to the kernel, which prints the output event:
* Accepted hello app: `hello_from_verified_bogos_app` (VGA: "hello from verified BogOS app")
* Rejected/unverified app: `none` (No output)

---

## Scope Boundaries

### In-Scope (v20 is):
* QEMU-only execution.
* Static embedded table representing pseudo-files.
* A visible, interactive OS prototype / demo system.
* Verified app loader proof of concept.
* Kernel-controlled app output.

### Out-of-Scope (v20 is NOT):
* A production-ready operating system.
* Physical hardware support (runs only under QEMU).
* A BIOS or bootloader (relies on GRUB/Multiboot).
* A real storage/disk driver or filesystem.
* A scheduler/multitasking/multi-core execution.
* Network stack or drivers.
* A replacement for Linux.
