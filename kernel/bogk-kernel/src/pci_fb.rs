//! Intel IGD linear framebuffer via PCI BAR (UEFI GOP fallback).

const PCI_CONFIG_ADDR: u16 = 0xCF8;
const PCI_CONFIG_DATA: u16 = 0xCFC;

const INTEL_VENDOR: u32 = 0x8086;
const CLASS_DISPLAY_VGA: u32 = 0x030000;

/// Common panel sizes on Acer Spin-class laptops (try in order).
const GUESS_RESOLUTIONS: [(u32, u32); 4] = [(1920, 1080), (1366, 768), (1280, 720), (1536, 864)];

pub struct PciFramebuffer {
    pub addr: usize,
    pub pitch: u32,
    pub width: u32,
    pub height: u32,
    pub bpp: u8,
}

pub fn probe() -> Option<PciFramebuffer> {
    // Intel IGD is almost always 00:02.0 on laptops.
    let mut bars = [0usize; 8];
    let mut n = 0usize;
    for bar_off in [0x10u8, 0x18u8, 0x20u8] {
        if let Some(addr) = pci_memory_bar(0, 2, 0, bar_off) {
            if addr >= 0x100000 && n < 8 {
                bars[n] = addr;
                n += 1;
            }
        }
    }
    for bar in bars.into_iter().chain(intel_igd_bars().into_iter()) {
        if bar == 0 {
            continue;
        }
        for &(width, height) in &GUESS_RESOLUTIONS {
            let pitch = width * 4;
            if verify_write_read(bar, pitch, width, height) {
                return Some(PciFramebuffer {
                    addr: bar,
                    pitch,
                    width,
                    height,
                    bpp: 32,
                });
            }
        }
    }
    None
}

fn intel_igd_bars() -> [usize; 4] {
    let mut out = [0usize; 4];
    let mut n = 0usize;
    for dev in 0u8..32 {
        let vendor = pci_read32(0, dev, 0, 0x00);
        if vendor == 0xFFFF_FFFF {
            continue;
        }
        let class = pci_read32(0, dev, 0, 0x08) >> 8;
        let ven = vendor & 0xFFFF;
        if class != CLASS_DISPLAY_VGA {
            continue;
        }
        if ven != INTEL_VENDOR && n == 0 {
            // Still collect any VGA device BARs as fallback.
        }
        for bar_off in [0x10u8, 0x18u8, 0x20u8] {
            if let Some(addr) = pci_memory_bar(0, dev, 0, bar_off) {
                if addr >= 0x100000 && n < 4 {
                    out[n] = addr;
                    n += 1;
                }
            }
        }
    }
    out
}

fn pci_memory_bar(bus: u8, dev: u8, func: u8, offset: u8) -> Option<usize> {
    let lo = pci_read32(bus, dev, func, offset);
    if lo == 0 || lo == 0xFFFF_FFFF || (lo & 1) != 0 {
        return None;
    }
    let typ = (lo >> 1) & 0x3;
    if typ == 0x02 {
        let hi = pci_read32(bus, dev, func, offset + 4);
        let addr = ((hi as u64) << 32) | (lo as u64 & 0xFFFF_FFF0);
        if addr == 0 || addr > u32::MAX as u64 {
            return None;
        }
        return Some(addr as usize);
    }
    Some((lo & 0xFFFF_FFF0) as usize)
}

fn verify_write_read(base: usize, pitch: u32, width: u32, height: u32) -> bool {
    if base == 0 || width == 0 || height == 0 {
        return false;
    }
    let size = pitch as u64 * height as u64;
    if size > 32 * 1024 * 1024 {
        return false;
    }
    let probe_off = base + (pitch as usize / 2);
    let ptr = probe_off as *mut u32;
    unsafe {
        let before = ptr.read_volatile();
        ptr.write_volatile(0x00FF_00FF);
        let after = ptr.read_volatile();
        ptr.write_volatile(before);
        after == 0x00FF_00FF
    }
}

fn pci_read32(bus: u8, dev: u8, func: u8, offset: u8) -> u32 {
    let addr = 0x8000_0000u32
        | ((bus as u32) << 16)
        | ((dev as u32) << 11)
        | ((func as u32) << 8)
        | ((offset as u32) & 0xFC);
    unsafe {
        core::arch::asm!(
            "out dx, eax",
            in("dx") PCI_CONFIG_ADDR,
            in("eax") addr,
            options(nomem, nostack, preserves_flags)
        );
        let mut val: u32;
        core::arch::asm!(
            "in eax, dx",
            out("eax") val,
            in("dx") PCI_CONFIG_DATA,
            options(nomem, nostack, preserves_flags)
        );
        val
    }
}