# Bare-Metal Phase 3: Hardware Abstraction Layer & Core Drivers

## Claim And Dependency

Robust timer, interrupts, keyboard, and display on real laptop hardware via HAL
traits. Depends on Phase 1; Phase 2 optional for USB-boot-only path.

## Technical Scope

- `platform/hal/{serial,timer,irq,keyboard,display}.rs`
- APIC/IOAPIC with 8259 PIC fallback
- LAPIC timer with PIT fallback
- PS/2 keyboard (USB fallback documented as stretch)
- VESA framebuffer optional; VGA text fallback
- ACPI: FADT shutdown, MADT for APIC

## Minimum Components

- `scripts/evaluate_phase3_hal_smoke.py`
- Hardware matrix updates for 2+ machines

## Receipts

`BOGBIN_PHASE3_HAL_BEGIN/END`: `TIMER`, `IRQ_MODEL`, `KEYBOARD`, `DISPLAY`.

## Explicit Non-Goals

USB keyboard driver (unless stretch), full ACPI power management, networking.

## Done When

Timer preempt + keyboard on 2+ real machines; v30/v31 QEMU proofs pass; `main.rs`
device code reduced per ADR-003.