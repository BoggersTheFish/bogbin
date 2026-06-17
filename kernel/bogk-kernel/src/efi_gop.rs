//! UEFI GOP framebuffer discovery for Multiboot1 + UEFI GRUB handoff.

const MULTIBOOT_INFO_CONFIG_TABLE: u32 = 1 << 3;
const MULTIBOOT_INFO_MEM_MAP: u32 = 1 << 6;

/// Correct LE signature for EFI system table header: "IBI SYST".
const EFI_SYSTEM_TABLE_SIGNATURE: u64 = 0x5453_5953_2049_4249;

#[repr(C)]
struct EfiGuid {
    data1: u32,
    data2: u16,
    data3: u16,
    data4: [u8; 8],
}

const EFI_GOP_GUID: EfiGuid = EfiGuid {
    data1: 0x7739_F6EF,
    data2: 0x75D2,
    data3: 0x4B93,
    data4: [0x82, 0x99, 0x98, 0xD9, 0x83, 0xBB, 0x04, 0xFC],
};

#[repr(C)]
struct MultibootInfoEfi {
    flags: u32,
    _skip: [u32; 10],
    mmap_length: u32,
    mmap_addr: u32,
    _drives: [u32; 2],
    config_table: u32,
}

#[repr(C)]
struct MultibootMmapEntry {
    size: u32,
    addr_low: u32,
    addr_high: u32,
    len_low: u32,
    len_high: u32,
    type_attr: u32,
}

pub struct GopFramebuffer {
    pub addr: u64,
    pub pitch: u32,
    pub width: u32,
    pub height: u32,
    pub bpp: u8,
}

pub fn from_multiboot(info_addr: u32) -> Option<GopFramebuffer> {
    if info_addr == 0 {
        return None;
    }
    let info = unsafe { &*(info_addr as *const MultibootInfoEfi) };

    if info.config_table != 0 {
        if let Some(fb) = try_config_table(info.config_table as usize) {
            return Some(fb);
        }
    }

    if (info.flags & MULTIBOOT_INFO_MEM_MAP) != 0
        && info.mmap_addr != 0
        && info.mmap_length > 0
    {
        if let Some(fb) = scan_mmap_for_gop_guid(info.mmap_addr, info.mmap_length) {
            return Some(fb);
        }
        if let Some(fb) = scan_mmap_for_gop(info.mmap_addr, info.mmap_length) {
            return Some(fb);
        }
    }

    None
}

fn scan_mmap_for_gop_guid(mmap_addr: u32, mmap_length: u32) -> Option<GopFramebuffer> {
    let mut offset = 0u32;
    let mut scans = 0u32;
    while offset < mmap_length && scans < 96 {
        let entry = unsafe { &*((mmap_addr + offset) as *const MultibootMmapEntry) };
        if entry.size < 20 {
            break;
        }
        if entry.addr_high == 0 && entry.len_high == 0 && entry.addr_low >= 0x100000 {
            let base = entry.addr_low as usize;
            let limit = (entry.len_low as usize).min(262144);
            let mut off = 0usize;
            while off + 24 < limit && scans < 96 {
                if guid_eq(base + off, &EFI_GOP_GUID) {
                    let gop64 = read_u64(base + off + 16) as usize;
                    if let Some(fb) = gop_framebuffer64(gop64) {
                        return Some(fb);
                    }
                    let gop32 = read_u32(base + off + 16) as usize;
                    if let Some(fb) = gop_framebuffer32(gop32) {
                        return Some(fb);
                    }
                }
                off += 16;
                scans += 1;
            }
        }
        offset += entry.size + 4;
    }
    None
}

fn try_config_table(ptr: usize) -> Option<GopFramebuffer> {
    let candidates = [
        ptr,
        read_u32(ptr) as usize,
        read_u64(ptr) as usize,
        read_u32(ptr + 4) as usize,
        read_u64(ptr + 8) as usize,
    ];
    for cand in candidates {
        if cand == 0 {
            continue;
        }
        if let Some(fb) = from_efi_system_table64(cand) {
            return Some(fb);
        }
        if let Some(fb) = from_efi_system_table32(cand) {
            return Some(fb);
        }
    }
    None
}

fn scan_mmap_for_gop(mmap_addr: u32, mmap_length: u32) -> Option<GopFramebuffer> {
    let mut offset = 0u32;
    let mut scans = 0u32;
    while offset < mmap_length && scans < 48 {
        let entry = unsafe { &*((mmap_addr + offset) as *const MultibootMmapEntry) };
        if entry.size < 20 {
            break;
        }
        if entry.addr_high == 0 && entry.len_high == 0 && entry.addr_low != 0 {
            let base = entry.addr_low as usize;
            let len = entry.len_low as usize;
            let limit = len.min(65536);
            let mut off = 0usize;
            while off + 112 < limit && scans < 48 {
                let addr = base + off;
                if let Some(fb) = from_efi_system_table64(addr) {
                    return Some(fb);
                }
                if let Some(fb) = from_efi_system_table32(addr) {
                    return Some(fb);
                }
                off += 4096;
                scans += 1;
            }
        }
        offset += entry.size + 4;
    }
    None
}

fn from_efi_system_table64(st_addr: usize) -> Option<GopFramebuffer> {
    if st_addr == 0 || read_u64(st_addr) != EFI_SYSTEM_TABLE_SIGNATURE {
        return None;
    }
    let table_count = read_u64(st_addr + 104) as usize;
    let table_ptr = read_u64(st_addr + 112) as usize;
    if table_ptr == 0 || table_count == 0 || table_count > 64 {
        return None;
    }
    for i in 0..table_count {
        let entry = table_ptr + i * 24;
        if !guid_eq(entry, &EFI_GOP_GUID) {
            continue;
        }
        let gop = read_u64(entry + 16) as usize;
        if let Some(fb) = gop_framebuffer64(gop) {
            return Some(fb);
        }
    }
    None
}

fn from_efi_system_table32(st_addr: usize) -> Option<GopFramebuffer> {
    if st_addr == 0 || read_u64(st_addr) != EFI_SYSTEM_TABLE_SIGNATURE {
        return None;
    }
    let table_count = read_u32(st_addr + 56) as usize;
    let table_ptr = read_u32(st_addr + 60) as usize;
    if table_ptr == 0 || table_count == 0 || table_count > 64 {
        return None;
    }
    for i in 0..table_count {
        let entry = table_ptr + i * 20;
        if !guid_eq(entry, &EFI_GOP_GUID) {
            continue;
        }
        let gop = read_u32(entry + 16) as usize;
        if let Some(fb) = gop_framebuffer32(gop) {
            return Some(fb);
        }
    }
    None
}

fn gop_framebuffer64(gop: usize) -> Option<GopFramebuffer> {
    if gop == 0 {
        return None;
    }
    let mode_ptr = read_u64(gop + 24) as usize;
    gop_mode64(mode_ptr)
}

fn gop_framebuffer32(gop: usize) -> Option<GopFramebuffer> {
    if gop == 0 {
        return None;
    }
    let mode_ptr = read_u32(gop + 12) as usize;
    gop_mode32(mode_ptr)
}

fn gop_mode64(mode_ptr: usize) -> Option<GopFramebuffer> {
    if mode_ptr == 0 {
        return None;
    }
    let info_ptr = read_u64(mode_ptr + 8) as usize;
    let fb_base = read_u64(mode_ptr + 24);
    gop_mode_common(info_ptr, fb_base)
}

fn gop_mode32(mode_ptr: usize) -> Option<GopFramebuffer> {
    if mode_ptr == 0 {
        return None;
    }
    let info_ptr = read_u32(mode_ptr + 8) as usize;
    let fb_base = read_u32(mode_ptr + 16) as u64;
    gop_mode_common(info_ptr, fb_base)
}

fn gop_mode_common(info_ptr: usize, fb_base: u64) -> Option<GopFramebuffer> {
    if info_ptr == 0 || fb_base == 0 {
        return None;
    }
    let width = read_u32(info_ptr + 4);
    let height = read_u32(info_ptr + 8);
    let ppsl = read_u32(info_ptr + 32);
    let pitch = if ppsl != 0 { ppsl * 4 } else { width * 4 };
    if width == 0 || height == 0 || width > 7680 || height > 4320 {
        return None;
    }
    if fb_base > u32::MAX as u64 {
        return None;
    }
    Some(GopFramebuffer {
        addr: fb_base,
        pitch,
        width,
        height,
        bpp: 32,
    })
}

fn guid_eq(addr: usize, expected: &EfiGuid) -> bool {
    read_u32(addr) == expected.data1
        && read_u16(addr + 4) == expected.data2
        && read_u16(addr + 6) == expected.data3
        && read_bytes(addr + 8) == expected.data4
}

fn read_bytes(addr: usize) -> [u8; 8] {
    let mut out = [0u8; 8];
    let mut i = 0usize;
    while i < 8 {
        out[i] = unsafe { (addr as *const u8).add(i).read_volatile() };
        i += 1;
    }
    out
}

fn read_u16(addr: usize) -> u16 {
    unsafe { (addr as *const u16).read_volatile() }
}

fn read_u32(addr: usize) -> u32 {
    unsafe { (addr as *const u32).read_volatile() }
}

fn read_u64(addr: usize) -> u64 {
    unsafe { (addr as *const u64).read_volatile() }
}