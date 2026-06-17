# Bare-Metal Phase 4: Memory Management & Kernel Robustness

## Claim And Dependency

Physical memory manager scales to laptop RAM; demand paging foundation loads
verified pages from storage on fault. Depends on Phase 1–2.

## Technical Scope

- Full Multiboot mmap parsing; reserved/ACPI region handling
- Buddy or equivalent frame allocator
- Demand paging with verified hash check on fault
- Guard pages on kernel heap
- Memory pressure negatives: OOM, invalid mappings

## Minimum Components

- `platform/mm/{frame_allocator,buddy,demand_load}.rs`
- `docs/baremetal_memory_layout.md`
- `scripts/evaluate_phase4_memory_stress.py`

## Receipts

`BOGBIN_PHASE4_MEMORY_BEGIN/END`: `PHYS_MEM_MIB`, `PHYS_FRAMES`, `HEAP_BYTES`,
`DEMAND_PAGE_FAULTS`, `OOM_REJECTIONS`.

## Explicit Non-Goals

Swapping, ASLR, SMP, full virtual memory POSIX semantics.

## Done When

Demand paging loads from BogFS on fault; v31 paging negative matrix passes on
QEMU and sampled hardware.