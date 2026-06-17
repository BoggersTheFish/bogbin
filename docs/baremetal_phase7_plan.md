# Bare-Metal Phase 7: Advanced Features (x86_64, Networking, BogVM)

## Claim And Dependency

x86_64 port for modern UEFI laptops, minimal networking, BogVM native integration,
self-host bootstrap path. Depends on Phases 1–6 on i686.

## Technical Scope

- `x86_64-unknown-none` target, long mode, new paging, syscall convention
- GRUB x86_64 EFI boot path
- Minimal Ethernet: ARP/IP/UDP or TCP subset; receipt per policy decision
- BogVM/TS-Lang as verified `.bogapp` on native substrate
- Self-hosting bootstrap documentation

## Minimum Components

- `kernel/x86_64-unknown-none.json`, new linker script
- `scripts/evaluate_phase7_x86_64_net.py`
- `docs/self_hosting_bootstrap.md`, `docs/ts_graph_native_vision.md`

## Receipts

`BOGBIN_PHASE7_ARCH_BEGIN/END`: `ARCH=x86_64`, `NET_STACK=minimal`.

## Note

i686-only is insufficient for most 2020+ laptops. Phase 7 x86_64 is effectively
required for the end-state dual-boot vision.

## Explicit Non-Goals

Full network stack, WiFi, production package manager, complete self-hosting.

## Done When

Boots on x86_64 UEFI laptop; basic UDP echo or ping; one TS-Lang `.bogapp` runs
with receipts.