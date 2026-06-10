# BogOS v20 Visible QEMU Demo Guide

BOGBIN v20.0.0 is the first visible BogOS QEMU demo system.

It boots BogKernel into a VGA text-mode screen, exposes a small shell or auto-demo command flow, lists embedded pseudo-files/apps, verifies a valid app before execution, blocks an invalid app, and emits serial proof receipts.

## Build the kernel

```bash
cd kernel
cargo build -p bogk-kernel --target i686-unknown-linux-musl
cd ..
```

## Run the visible QEMU demo

```bash
qemu-system-i386 \
  -kernel kernel/target/i686-unknown-linux-musl/debug/bogk-kernel \
  -serial file:artifacts/bogos_v20_visible_serial.log \
  -display gtk
```

Expected visible screen:

```text
BOGOS v20.0.0
Self-verifying QEMU demo system

boot: verified
kernel: online
trust rule: verify-before-accept
apps: 1 accepted / 1 rejected
storage: embedded readonly table
shell: online

bogos>
```

## Verify the serial proof

After closing QEMU:

```bash
grep -E "BOGOS_V20|BOGOS_APP_RUN|APP_ACCEPTED|APP_REJECTED|APP_OUTPUT_EVENT" artifacts/bogos_v20_visible_serial.log
```

Expected proof:

* BogOS v20 boot markers are present.
* VGA text mode is online.
* Shell or auto-demo support is online.
* Embedded pseudo-file table is present.
* `run hello` is accepted and executed.
* `run bad-hello` is rejected and not executed.
* Rejected app emits no output event.

## Boundary

This is a QEMU-only visible demo system. It is not a production OS, not physical hardware support, not a real disk filesystem, not a scheduler, and not a Linux replacement.

Serial receipts remain proof authority.
