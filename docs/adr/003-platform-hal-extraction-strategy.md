# ADR-003: Platform HAL Extraction Strategy

## Status

Accepted — Phase 0 (strategy); implementation Phases 1–3.

## Context

All device I/O lives in `kernel/bogk-kernel/src/main.rs` (~6.7k lines). Bare-metal
requires AHCI, APIC, and real-hardware console without rewriting BogFS, process
model, or verification logic.

## Decision

Extract hardware behind traits in `platform/` incrementally. One subsystem per
change set with full QEMU evaluator regression. Higher layers (BogFS, scheduler,
loader, IPC) remain unchanged.

## Extraction Order

```
Phase 1: boot/multiboot.rs     — Multiboot parse, early serial
Phase 2: block/{mod,qemu_ide,ahci}.rs — block trait + backends
Phase 3: hal/{serial,timer,irq,keyboard,display}.rs
Phase 3: acpi/tables.rs        — shutdown, MADT
Phase 4: mm/{frame_allocator,buddy,demand_load}.rs
```

## Trait Boundaries

### BlockDevice (Phase 2)

```rust
trait BlockDevice {
    fn probe(&self) -> ProbeStatus;
    fn read_sector(&self, lba: u32, buf: &mut [u8; 512]) -> Result<(), BlockError>;
    fn write_sector_verified(...) -> Result<WriteReceipt, BlockError>;
    fn flush(&self) -> Result<(), BlockError>;
}
```

Preserves v36 semantics: SHA-256 gates, protected LBAs, read-back verification,
`MUTATED_TRUSTED_STATE` distinction.

### HalSerial (Phase 1/3)

```rust
trait HalSerial {
    fn init(&mut self);
    fn write_byte(&mut self, b: u8);
    fn write_str(&mut self, s: &str);
}
```

Default: COM1 @ `0x3F8`. Receipt channel remains serial-first.

### HalTimer (Phase 3)

```rust
trait HalTimer {
    fn init(&mut self);
    fn ticks(&self) -> u64;
}
```

LAPIC preferred; PIT fallback. Preserve v30 preempt receipt format.

### HalKeyboard, HalDisplay (Phase 3)

Extract PS/2 and VGA/VESA without changing shell command parsing.

## Integration Path

1. **Phase 0:** `platform/` reference stubs; no kernel `mod platform`
2. **Phase 1:** `bogk-kernel` adds optional `baremetal` feature; `platform` as submodule or `bogk-platform` crate
3. **Phase 2:** Block trait; `main.rs` calls `block.read_sector` instead of inline ATA
4. **Phase 3:** Remaining HAL; `main.rs` becomes orchestration + proof paths

## Non-Goals

- Full driver framework with async I/O
- Plugin/dynamic driver loading
- Rewriting `bogk-core` filesystem logic

## Regression Requirement

After each extraction step:

```bash
python3 scripts/evaluate_v36_block_device.py   # through v41 as applicable
python3 scripts/evaluate_phase0_grub_hello.py  # after Phase 0
```

## Consequences

- `main.rs` shrinks over Phases 2–3 but proof functions (`run_v38_*`, etc.) stay
  until Phase 6 consolidation.
- QEMU IDE backend remains for CI; AHCI added as second backend.