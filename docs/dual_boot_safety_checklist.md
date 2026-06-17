# Dual-Boot Safety Checklist

Use this checklist before any bare-metal storage test (Phase 2+) or installation
(Phase 8). Phase 0–1 USB boot tests do not require disk modification but still
benefit from the recovery section.

## Pre-Flight (Required)

- [ ] **Full backup** of important data on the target machine
- [ ] **Partition map documented** (`lsblk -f`, `fdisk -l`, or disk utility screenshot)
- [ ] **ESP/EFI partition identified** and marked do-not-modify without backup
- [ ] **Recovery USB prepared** (host OS live USB with GRUB repair tools)
- [ ] **Bogbin test media is USB or spare partition** — not the host OS root partition
- [ ] **Serial capture plan** (USB-serial adapter, built-in UART, or netconsole fallback documented)
- [ ] **Rollback plan written** before first boot attempt

## Partition Rules

| Rule | Rationale |
| --- | --- |
| Bogbin gets a **dedicated partition** or separate USB disk | Isolates BogFS from host filesystem |
| Never overwrite ESP without **ESP backup** | Bricks UEFI boot for all OSes |
| Never reuse host swap or recovery partitions | Data loss risk |
| Phase 2–7 tests use **USB or labeled spare partition** only | Per ADR-002 |
| Phase 8 install follows [baremetal_phase8_plan.md](baremetal_phase8_plan.md) layout | Guided sizing and labeling |

## GRUB Safety

- [ ] Existing GRUB config **backed up** (`/boot/grub/grub.cfg` or EFI path)
- [ ] New menuentry is **additive** — does not remove Linux/Windows entries
- [ ] `grub-install` target device **triple-checked** (not whole-disk overwrite mistake)
- [ ] `os-prober` behavior understood before enabling
- [ ] Test **fallback boot** to host OS before relying on Bogbin partition

## Bogbin-Specific

- [ ] Bogbin partition labeled/GUID documented (`BOGBIN` or project GUID in Phase 2 plan)
- [ ] BogFS images flashed only to Bogbin partition via `scripts/flash_bogbin_partition.sh`
- [ ] Receipt logs saved to `artifacts/` after each hardware boot
- [ ] Corruption/negative tests use **disposable** images only

## Recovery Procedures

### Host OS still boots

1. Select host OS from GRUB menu
2. Inspect `/boot/grub/grub.cfg`; restore from backup if needed
3. Run `sudo grub-install` + `sudo update-grub` (Linux) from host OS

### Host OS does not boot

1. Boot from recovery/live USB
2. Mount EFI System Partition and root partition
3. Restore GRUB config from backup
4. Re-run `grub-install` to correct disk
5. Verify host OS boots before any further Bogbin experiments

### Bogbin partition corrupt

1. Re-flash from known-good image (`scripts/make_baremetal_disk_image.py`)
2. Verify receipt chain from host with `scripts/inspect_bogfs_partition.py` (Phase 6)
3. Host OS partition must remain untouched

## Sign-Off Template

```
Machine: _______________
Date: _______________
Firmware: BIOS / UEFI (circle one)
Test scope: USB boot only / spare partition / dual-boot install
Backup verified: YES / NO
Recovery USB ready: YES / NO
Signed: _______________
```

Required for Phase 2+ internal disk tests and all Phase 8 installations.