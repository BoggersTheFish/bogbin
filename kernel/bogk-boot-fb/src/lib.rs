//! Minimal framebuffer handoff proof — bootloader contract only, no GOP discovery.

#![no_std]

const MULTIBOOT_BOOTLOADER_MAGIC: u32 = 0x2BADB002;
const MULTIBOOT_INFO_FRAMEBUFFER: u32 = 1 << 12;

const MULTIBOOT2_BOOTLOADER_MAGIC: u32 = 0x36D7_6289;

const MAGENTA: u32 = 0x00FF_00FF;

pub struct FramebufferHandoff {
    pub addr: usize,
    pub pitch: u32,
    pub width: u32,
    pub height: u32,
    pub bpp: u8,
}

#[repr(C)]
struct MultibootInfoVideo {
    flags: u32,
    mem_lower: u32,
    mem_upper: u32,
    boot_device: u32,
    cmdline: u32,
    mods_count: u32,
    mods_addr: u32,
    syms: [u32; 4],
    mmap_length: u32,
    mmap_addr: u32,
    drives_length: u32,
    drives_addr: u32,
    config_table: u32,
    boot_loader_name: u32,
    apm_table: u32,
    vbe_control_info: u32,
    vbe_mode_info: u32,
    vbe_mode: u16,
    vbe_interface_seg: u16,
    vbe_interface_off: u16,
    vbe_interface_len: u16,
    framebuffer_addr: u32,
    framebuffer_pitch: u32,
    framebuffer_width: u32,
    framebuffer_height: u32,
    framebuffer_bpp: u8,
    _framebuffer_type: u8,
}

pub fn pc_speaker_beep_hz(hz: u32) {
    const PIT_FREQ: u32 = 1_193_180;
    let divisor = PIT_FREQ / hz.max(1);
    unsafe {
        core::arch::asm!("out 0x43, al", in("al") 0xB6u8, options(nomem, nostack, preserves_flags));
        core::arch::asm!(
            "out 0x42, al",
            in("al") (divisor & 0xFF) as u8,
            options(nomem, nostack, preserves_flags)
        );
        core::arch::asm!(
            "out 0x42, al",
            in("al") ((divisor >> 8) & 0xFF) as u8,
            options(nomem, nostack, preserves_flags)
        );
        let mut port: u8;
        core::arch::asm!("in al, 0x61", out("al") port, options(nomem, nostack, preserves_flags));
        port |= 3;
        core::arch::asm!("out 0x61, al", in("al") port, options(nomem, nostack, preserves_flags));
        for _ in 0..8_000_000u32 {
            core::arch::asm!("nop", options(nomem, nostack, preserves_flags));
        }
        port &= !3;
        core::arch::asm!("out 0x61, al", in("al") port, options(nomem, nostack, preserves_flags));
    }
}

fn halt_forever() -> ! {
    loop {
        unsafe {
            core::arch::asm!("cli");
            core::arch::asm!("hlt");
        }
    }
}

pub fn fill_magenta(fb: &FramebufferHandoff) {
    for y in 0..fb.height {
        let row = fb.addr + (y as usize) * (fb.pitch as usize);
        for x in 0..fb.width {
            unsafe {
                core::ptr::write_volatile((row + (x as usize) * 4) as *mut u32, MAGENTA);
            }
        }
    }
}

pub fn multiboot1_framebuffer(info_addr: u32) -> Option<FramebufferHandoff> {
    if info_addr == 0 {
        return None;
    }
    let info = unsafe { &*(info_addr as *const MultibootInfoVideo) };
    if (info.flags & MULTIBOOT_INFO_FRAMEBUFFER) == 0 {
        return None;
    }
    handoff_from_fields(
        info.framebuffer_addr as usize,
        info.framebuffer_pitch,
        info.framebuffer_width,
        info.framebuffer_height,
        info.framebuffer_bpp,
    )
}

enum Mb2FbLookup {
    Missing,
    Invalid,
    Valid(FramebufferHandoff),
}

fn multiboot2_framebuffer_lookup(info_addr: u32) -> Mb2FbLookup {
    if info_addr == 0 {
        return Mb2FbLookup::Missing;
    }
    let base = info_addr as usize;
    let total = unsafe { (base as *const u32).read_volatile() } as usize;
    let mut cursor = base + 8;
    let end = base + total;
    while cursor + 8 <= end {
        let typ = unsafe { (cursor as *const u16).read_volatile() };
        let size = unsafe { (cursor as *const u32).add(1).read_volatile() } as usize;
        if size < 8 {
            break;
        }
        if typ == 0 {
            break;
        }
        if typ == 8 {
            if size < 28 {
                return Mb2FbLookup::Invalid;
            }
            let payload = cursor + 8;
            let addr = unsafe { (payload as *const u64).read_volatile() };
            let pitch = unsafe { (payload as *const u32).add(2).read_volatile() };
            let width = unsafe { (payload as *const u32).add(3).read_volatile() };
            let height = unsafe { (payload as *const u32).add(4).read_volatile() };
            let bpp = unsafe { (payload as *const u8).add(20).read_volatile() };
            return match handoff_from_fields(addr as usize, pitch, width, height, bpp) {
                Some(h) => Mb2FbLookup::Valid(h),
                None => Mb2FbLookup::Invalid,
            };
        }
        cursor += (size + 7) & !7;
    }
    Mb2FbLookup::Missing
}

fn handoff_from_fields(
    addr: usize,
    pitch: u32,
    width: u32,
    height: u32,
    bpp: u8,
) -> Option<FramebufferHandoff> {
    if addr == 0 || pitch == 0 || width == 0 || height == 0 || bpp != 32 {
        return None;
    }
    Some(FramebufferHandoff {
        addr,
        pitch,
        width,
        height,
        bpp,
    })
}

/// MB1 magenta proof: 440 entered, 220 no fb, 220×2 invalid, 880×2 success.
pub fn run_magenta_proof_mb1(mboot_magic: u32, info_addr: u32) -> ! {
    pc_speaker_beep_hz(440);

    if mboot_magic != MULTIBOOT_BOOTLOADER_MAGIC || info_addr == 0 {
        pc_speaker_beep_hz(220);
        halt_forever();
    }

    let info = unsafe { &*(info_addr as *const MultibootInfoVideo) };
    if (info.flags & MULTIBOOT_INFO_FRAMEBUFFER) == 0 {
        pc_speaker_beep_hz(220);
        halt_forever();
    }

    let fb = multiboot1_framebuffer(info_addr);
    if fb.is_none() {
        pc_speaker_beep_hz(220);
        pc_speaker_beep_hz(220);
        halt_forever();
    }

    fill_magenta(&fb.unwrap());
    pc_speaker_beep_hz(880);
    pc_speaker_beep_hz(880);
    halt_forever();
}

/// MB2 magenta proof — same beep contract, separate boot-info parser.
pub fn run_magenta_proof_mb2(mboot_magic: u32, info_addr: u32) -> ! {
    pc_speaker_beep_hz(440);

    if mboot_magic != MULTIBOOT2_BOOTLOADER_MAGIC || info_addr == 0 {
        pc_speaker_beep_hz(220);
        halt_forever();
    }

    match multiboot2_framebuffer_lookup(info_addr) {
        Mb2FbLookup::Missing => {
            pc_speaker_beep_hz(220);
            halt_forever();
        }
        Mb2FbLookup::Invalid => {
            pc_speaker_beep_hz(220);
            pc_speaker_beep_hz(220);
            halt_forever();
        }
        Mb2FbLookup::Valid(fb) => fill_magenta(&fb),
    }
    pc_speaker_beep_hz(880);
    pc_speaker_beep_hz(880);
    halt_forever();
}