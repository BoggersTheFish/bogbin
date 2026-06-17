//! Multiboot2 header (UEFI GOP framebuffer) and boot-info tag parsing.

pub const MULTIBOOT2_BOOTLOADER_MAGIC: u32 = 0x36D7_6289;
pub const MULTIBOOT2_HEADER_MAGIC: u32 = 0xE852_50D6;

const TAG_END: u16 = 0;
const TAG_INFORMATION_REQUEST: u16 = 1;
const TAG_FRAMEBUFFER: u16 = 5;

const REQUEST_MEMORY_MAP: u32 = 1 << 1;
const REQUEST_CMDLINE: u32 = 1 << 2;
const REQUEST_FRAMEBUFFER: u32 = 1 << 5;

pub fn is_multiboot2(magic: u32) -> bool {
    magic == MULTIBOOT2_BOOTLOADER_MAGIC
}

pub fn cmdline_contains(info_addr: u32, needle: &[u8]) -> bool {
    if info_addr == 0 {
        return false;
    }
    for tag in iter_tags(info_addr) {
        if tag.typ == 1 && tag.payload_len > 0 {
            return cstr_contains(tag.payload_addr, tag.payload_len, needle);
        }
    }
    false
}

pub fn boot_loader_name_contains(info_addr: u32, needle: &[u8]) -> bool {
    if info_addr == 0 {
        return false;
    }
    for tag in iter_tags(info_addr) {
        if tag.typ == 2 && tag.payload_len > 0 {
            return cstr_contains(tag.payload_addr, tag.payload_len, needle);
        }
    }
    false
}

pub fn has_memory_map(info_addr: u32) -> bool {
    if info_addr == 0 {
        return false;
    }
    for tag in iter_tags(info_addr) {
        if tag.typ == 6 {
            return true;
        }
    }
    false
}

pub struct FramebufferInfo {
    pub addr: u64,
    pub pitch: u32,
    pub width: u32,
    pub height: u32,
    pub bpp: u8,
}

#[repr(C)]
struct Multiboot2FramebufferInfo {
    addr: u64,
    pitch: u32,
    width: u32,
    height: u32,
    bpp: u8,
    fb_type: u8,
    reserved: u16,
}

pub fn framebuffer_info(info_addr: u32) -> Option<FramebufferInfo> {
    if info_addr == 0 {
        return None;
    }
    for tag in iter_tags(info_addr) {
        if tag.typ != 8 || tag.payload_len < core::mem::size_of::<Multiboot2FramebufferInfo>() {
            continue;
        }
        let fb = unsafe { &*(tag.payload_addr as *const Multiboot2FramebufferInfo) };
        if fb.width == 0
            || fb.height == 0
            || fb.addr == 0
            || fb.width > 7680
            || fb.height > 4320
            || fb.pitch == 0
            || fb.pitch > 65536
        {
            return None;
        }
        return Some(FramebufferInfo {
            addr: fb.addr,
            pitch: fb.pitch,
            width: fb.width,
            height: fb.height,
            bpp: fb.bpp,
        });
    }
    None
}

struct ParsedTag {
    typ: u16,
    payload_addr: u32,
    payload_len: usize,
}

fn iter_tags(info_addr: u32) -> TagIter {
    let base = info_addr as usize;
    let total = unsafe { (base as *const u32).read_volatile() } as usize;
    TagIter {
        cursor: base + 8,
        end: base + total,
    }
}

struct TagIter {
    cursor: usize,
    end: usize,
}

impl Iterator for TagIter {
    type Item = ParsedTag;

    fn next(&mut self) -> Option<Self::Item> {
        if self.cursor + 8 > self.end {
            return None;
        }
        let typ = unsafe { (self.cursor as *const u16).read_volatile() };
        let size = unsafe { (self.cursor as *const u32).add(1).read_volatile() } as usize;
        if size < 8 {
            return None;
        }
        if typ == TAG_END {
            return None;
        }
        let payload_addr = (self.cursor + 8) as u32;
        let payload_len = size.saturating_sub(8);
        let tag = ParsedTag {
            typ,
            payload_addr,
            payload_len,
        };
        let step = (size + 7) & !7;
        if self.cursor + step > self.end {
            self.cursor = self.end;
        } else {
            self.cursor += step;
        }
        Some(tag)
    }
}

fn cstr_contains(ptr: u32, max_len: usize, needle: &[u8]) -> bool {
    if ptr == 0 || needle.is_empty() || max_len == 0 {
        return false;
    }
    let base = ptr as *const u8;
    let scan_limit = max_len.min(512);
    let mut i = 0usize;
    while i < scan_limit {
        let ch = unsafe { core::ptr::read(base.add(i)) };
        if ch == 0 {
            break;
        }
        if i + needle.len() <= scan_limit {
            let mut matched = true;
            for (j, &n) in needle.iter().enumerate() {
                let c = unsafe { core::ptr::read(base.add(i + j)) };
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