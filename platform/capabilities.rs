//! Reference capability types for bare-metal transition.
//!
//! Not yet wired into the kernel workspace. Copy or move into `bogk-core` or
//! `bogk-platform` crate during Phase 1. See ADR-003.

#![allow(dead_code)]

/// How the kernel was loaded.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BootPath {
    QemuDirect,
    GrubMultiboot1,
    GrubMultiboot2,
    EfiHandoff,
}

/// Host firmware class.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BootFirmware {
    Bios,
    Uefi,
    Unknown,
}

/// Block storage backend.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StorageBackend {
    None,
    QemuIdeAtaPio,
    Ahci,
}

/// Early console availability.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum EarlyConsole {
    Serial,
    Vga,
    Both,
}

/// Platform capabilities detected or declared at boot.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PlatformCaps {
    pub boot_path: BootPath,
    pub firmware: BootFirmware,
    pub storage: StorageBackend,
    pub early_console: EarlyConsole,
    pub arch_i686: bool,
}

impl PlatformCaps {
    pub const fn qemu_default() -> Self {
        Self {
            boot_path: BootPath::QemuDirect,
            firmware: BootFirmware::Unknown,
            storage: StorageBackend::QemuIdeAtaPio,
            early_console: EarlyConsole::Both,
            arch_i686: true,
        }
    }
}

/// Serialize caps as receipt key=value lines (no heap).
pub fn emit_caps_receipt_lines(caps: &PlatformCaps, out: &mut dyn FnMut(&str)) {
    let boot_path = match caps.boot_path {
        BootPath::QemuDirect => "qemu_direct",
        BootPath::GrubMultiboot1 => "grub_multiboot1",
        BootPath::GrubMultiboot2 => "grub_multiboot2",
        BootPath::EfiHandoff => "efi_handoff",
    };
    let firmware = match caps.firmware {
        BootFirmware::Bios => "bios",
        BootFirmware::Uefi => "uefi",
        BootFirmware::Unknown => "unknown",
    };
    let storage = match caps.storage {
        StorageBackend::None => "none",
        StorageBackend::QemuIdeAtaPio => "qemu_ide",
        StorageBackend::Ahci => "ahci",
    };
    out(&format!("BOOT_PATH={boot_path}"));
    out(&format!("BOOT_FIRMWARE={firmware}"));
    out(&format!("STORAGE_BACKEND={storage}"));
    out(if caps.arch_i686 {
        "ARCH=i686"
    } else {
        "ARCH=x86_64"
    });
}