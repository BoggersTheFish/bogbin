//! Multiboot1/Multiboot2 boot context detection and Phase 1 bare-metal receipts.

use crate::multiboot2;

const MULTIBOOT_BOOTLOADER_MAGIC: u32 = 0x2BADB002;
const MULTIBOOT_INFO_CMDLINE: u32 = 1 << 2;
const MULTIBOOT_INFO_MEM_MAP: u32 = 1 << 6;
const MULTIBOOT_INFO_BOOT_LOADER_NAME: u32 = 1 << 9;

#[repr(C)]
struct MultibootInfo {
    flags: u32,
    mem_lower: u32,
    mem_upper: u32,
    boot_device: u32,
    cmdline: u32,
    mods_count: u32,
    mods_addr: u32,
    _syms: [u32; 4],
    mmap_length: u32,
    mmap_addr: u32,
    drives_length: u32,
    drives_addr: u32,
    config_table: u32,
    boot_loader_name: u32,
}

/// Detected boot environment for receipt emission.
#[derive(Clone, Copy)]
pub struct BootContext {
    pub platform: &'static str,
    pub boot_firmware: &'static str,
    pub boot_loader: &'static str,
    pub boot_path: &'static str,
    pub early_console: &'static str,
    pub memory_map_source: &'static str,
    /// Stop after Phase 1 receipt (for laptops without serial capture).
    pub halt_after_phase1: bool,
}

impl BootContext {
    pub fn detect(magic: u32, info_addr: u32) -> Self {
        let mut boot_path = "qemu_direct";
        let mut boot_loader = "qemu";
        let mut boot_firmware = "unknown";
        let mut memory_map_source = "none";
        let mut cmdline_has_platform_baremetal = false;
        let mut cmdline_has_platform_qemu = false;
        let mut halt_after_phase1 = false;

        if multiboot2::is_multiboot2(magic) && info_addr != 0 {
            boot_path = "grub_multiboot2";
            boot_loader = "grub2";
            if multiboot2::has_memory_map(info_addr) {
                memory_map_source = "multiboot";
            }
            if multiboot2::boot_loader_name_contains(info_addr, b"GRUB") {
                boot_loader = "grub2";
            }
            if multiboot2::cmdline_contains(info_addr, b"platform=baremetal") {
                cmdline_has_platform_baremetal = true;
            }
            if multiboot2::cmdline_contains(info_addr, b"platform=qemu") {
                cmdline_has_platform_qemu = true;
            }
            if multiboot2::cmdline_contains(info_addr, b"firmware=uefi") {
                boot_firmware = "uefi";
            } else if multiboot2::cmdline_contains(info_addr, b"firmware=bios") {
                boot_firmware = "bios";
            }
            if multiboot2::cmdline_contains(info_addr, b"halt_after_phase1") {
                halt_after_phase1 = true;
            }
        } else if magic == MULTIBOOT_BOOTLOADER_MAGIC && info_addr != 0 {
            let info = unsafe { &*(info_addr as *const MultibootInfo) };

            if (info.flags & MULTIBOOT_INFO_MEM_MAP) != 0 && info.mmap_addr != 0 {
                memory_map_source = "multiboot";
            } else if (info.flags & 1) != 0 {
                memory_map_source = "multiboot_memsize";
            }

            if (info.flags & MULTIBOOT_INFO_BOOT_LOADER_NAME) != 0 && info.boot_loader_name != 0 {
                if unsafe { cstr_contains(info.boot_loader_name, b"GRUB") } {
                    boot_path = "grub_multiboot1";
                    boot_loader = "grub2";
                } else if unsafe { cstr_contains(info.boot_loader_name, b"QEMU") } {
                    boot_path = "qemu_direct";
                    boot_loader = "qemu";
                } else {
                    boot_loader = "unknown";
                }
            }

            if (info.flags & MULTIBOOT_INFO_CMDLINE) != 0 && info.cmdline != 0 {
                if unsafe { cstr_contains(info.cmdline, b"platform=baremetal") } {
                    cmdline_has_platform_baremetal = true;
                }
                if unsafe { cstr_contains(info.cmdline, b"platform=qemu") } {
                    cmdline_has_platform_qemu = true;
                }
                if unsafe { cstr_contains(info.cmdline, b"firmware=uefi") } {
                    boot_firmware = "uefi";
                } else if unsafe { cstr_contains(info.cmdline, b"firmware=bios") } {
                    boot_firmware = "bios";
                }
                if unsafe { cstr_contains(info.cmdline, b"halt_after_phase1") } {
                    halt_after_phase1 = true;
                }
            }
        }

        let platform = resolve_platform(cmdline_has_platform_baremetal, cmdline_has_platform_qemu);

        Self {
            platform,
            boot_firmware,
            boot_loader,
            boot_path,
            early_console: "both",
            memory_map_source,
            halt_after_phase1,
        }
    }
}

fn resolve_platform(cmdline_baremetal: bool, cmdline_qemu: bool) -> &'static str {
    if cmdline_qemu {
        return "qemu";
    }
    if cmdline_baremetal {
        return "baremetal";
    }
    #[cfg(feature = "baremetal")]
    {
        return "baremetal";
    }
    #[cfg(not(feature = "baremetal"))]
    {
        "qemu"
    }
}

unsafe fn cstr_contains(ptr: u32, needle: &[u8]) -> bool {
    if ptr == 0 || needle.is_empty() {
        return false;
    }
    let base = ptr as *const u8;
    let mut i = 0usize;
    while i < 512 {
        let ch = core::ptr::read(base.add(i));
        if ch == 0 {
            break;
        }
        if i + needle.len() <= 512 {
            let mut matched = true;
            for (j, &n) in needle.iter().enumerate() {
                let c = core::ptr::read(base.add(i + j));
                if c == 0 || c != n {
                    matched = false;
                    break;
                }
            }
            if matched {
                return true;
            }
        }
        i += 1;
    }
    false
}

pub fn emit_phase1_receipt(ctx: &BootContext, write: &mut dyn FnMut(&str)) {
    write("BOGBIN_PHASE1_BOOT_BEGIN\n");
    write("PLATFORM=");
    write(ctx.platform);
    write("\n");
    write("BOOT_FIRMWARE=");
    write(ctx.boot_firmware);
    write("\n");
    write("BOOT_LOADER=");
    write(ctx.boot_loader);
    write("\n");
    write("BOOT_PATH=");
    write(ctx.boot_path);
    write("\n");
    write("EARLY_CONSOLE=");
    write(ctx.early_console);
    write("\n");
    write("MEMORY_MAP_SOURCE=");
    write(ctx.memory_map_source);
    write("\n");
    write("EXECUTION_STATUS=completed\n");
    write("BOGBIN_PHASE1_BOOT_END\n");
}