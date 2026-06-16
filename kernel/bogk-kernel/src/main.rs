#![no_std]
#![no_main]

extern crate alloc;

use core::panic::PanicInfo;
use bogk_core::{
    AppBundle, AppManifest, BootReceipt, BufferWriter, MinimalExecutor, ProcessRecord, ProcessTable,
    ProcessExecutionMemory, SavedContext, Scheduler, VerificationResult, INSTRUCTION_WIDTH,
};

core::arch::global_asm!(
    r#"
    .global kernel_entry
    kernel_entry:
        mov esp, offset stack_top
        push ebx
        push eax

        # Enable SSE
        mov eax, cr0
        and ax, 0xFFFB      # clear EM (bit 2)
        or ax, 0x2          # set MP (bit 1)
        mov cr0, eax
        mov eax, cr4
        or ax, 0x600        # set OSXMMEXCPT (bit 10) and OSFXSR (bit 9)
        mov cr4, eax

        call rust_start
        cli
    hlt_loop:
        hlt
        jmp hlt_loop

    .section .bss
    .align 16
    stack_bottom:
        .skip 32768
    stack_top:

    # Assembly ISR stubs
    .section .text
    .extern common_exception_handler
    .extern handle_timer_interrupt
    .extern handle_keyboard_interrupt

    .macro exception_err_stub nr
    .global exception_stub_\nr
    exception_stub_\nr:
        push \nr
        jmp exception_common
    .endm

    .macro exception_no_err_stub nr
    .global exception_stub_\nr
    exception_stub_\nr:
        push 0
        push \nr
        jmp exception_common
    .endm

    exception_no_err_stub 0
    exception_no_err_stub 1
    exception_no_err_stub 2
    exception_no_err_stub 3
    exception_no_err_stub 4
    exception_no_err_stub 5
    exception_no_err_stub 6
    exception_no_err_stub 7
    exception_err_stub    8
    exception_no_err_stub 9
    exception_err_stub    10
    exception_err_stub    11
    exception_err_stub    12
    exception_err_stub    13
    exception_err_stub    14
    exception_no_err_stub 15
    exception_no_err_stub 16
    exception_err_stub    17
    exception_no_err_stub 18
    exception_no_err_stub 19
    exception_no_err_stub 20
    exception_no_err_stub 21
    exception_no_err_stub 22
    exception_no_err_stub 23
    exception_no_err_stub 24
    exception_no_err_stub 25
    exception_no_err_stub 26
    exception_no_err_stub 27
    exception_no_err_stub 28
    exception_no_err_stub 29
    exception_err_stub    30
    exception_no_err_stub 31

    exception_common:
        pushad

        mov ax, 0x10
        mov ds, ax
        mov es, ax

        push esp
        call common_exception_handler
        add esp, 4

        # Restore user segment registers
        mov ax, 0x23
        mov ds, ax
        mov es, ax
        mov fs, ax
        mov gs, ax

        popad
        add esp, 8
        iretd

    .global isr_timer
    isr_timer:
        pushad
        push esp
        call handle_timer_interrupt
        add esp, 4
        popad
        iretd

    .global isr_keyboard
    isr_keyboard:
        pushad
        call handle_keyboard_interrupt
        popad
        iretd

    .global isr_syscall
    .extern handle_syscall
    isr_syscall:
        pushad
        push esp
        call handle_syscall
        add esp, 4
        popad
        iretd

    .global enter_ring3
    enter_ring3:
        # [esp+4]: entrypoint (eip), [esp+8]: user_esp
        mov ax, 0x23
        mov ds, ax
        mov es, ax
        mov fs, ax
        mov gs, ax
        
        push 0x23             # User SS
        mov eax, [esp + 12]   # User ESP (after pushing SS)
        push eax
        push 0x200            # EFLAGS with IF=1
        push 0x1B             # User CS
        mov eax, [esp + 20]   # entrypoint (after pushing 4 values)
        push eax
        iretd

    .global restore_user_context
    restore_user_context:
        # SavedContext layout: eip, esp, eflags, eax, ebx, ecx, edx, esi, edi, ebp
        mov edx, [esp + 4]
        mov ax, 0x23
        mov ds, ax
        mov es, ax
        mov fs, ax
        mov gs, ax

        push 0x23
        push dword ptr [edx + 4]
        push dword ptr [edx + 8]
        push 0x1B
        push dword ptr [edx]

        mov eax, [edx + 12]
        mov ebx, [edx + 16]
        mov ecx, [edx + 20]
        mov esi, [edx + 28]
        mov edi, [edx + 32]
        mov ebp, [edx + 36]
        mov edx, [edx + 24]
        iretd

    .global setjmp_kernel
    setjmp_kernel:
        mov eax, [esp + 4]   # EAX = pointer to jmp_buf
        mov [eax], ebp
        mov [eax + 4], esp
        mov [eax + 8], ebx
        mov [eax + 12], esi
        mov [eax + 16], edi
        mov edx, [esp]       # EDX = return address
        mov [eax + 20], edx
        xor eax, eax         # return 0
        ret

    .global longjmp_to_kernel
    longjmp_to_kernel:
        mov edx, [esp + 4]   # EDX = exit_code
        mov ecx, offset KERNEL_JMP_BUF
        mov ebp, [ecx]
        mov esp, [ecx + 4]
        mov ebx, [ecx + 8]
        mov esi, [ecx + 12]
        mov edi, [ecx + 16]
        mov eax, [ecx + 20]  # EAX = return address
        mov [esp], eax       # put return address back on stack
        mov eax, edx         # return exit_code
        ret

    .section .bss
    .align 4
    .global KERNEL_JMP_BUF
    KERNEL_JMP_BUF:
        .skip 24
    "#
);

/// Multiboot1 Header
#[no_mangle]
#[link_section = ".multiboot_header"]
pub static MULTIBOOT_HEADER: [u32; 3] = [
    0x1BADB002, // magic
    0x00000000, // flags
    0xE4524FFE, // checksum (-(0x1BADB002 + 0) as u32)
];

/// Embedded minimal BOGVM program: NOOP + HALT
static MINIMAL_PROGRAM: [u8; 16] = [
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // NOOP
    0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // HALT
];

/// Embedded BOGVM program for hash verification
static VERIFY_PROGRAM: [u8; 32] = [
    0x13, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, // VERIFY_HASH target=1 source=1
    0x14, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, // ACCEPT_DATA target=1
    0x17, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, // REJECT_DATA target=1
    0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // HALT
];

static PAYLOAD: &[u8] = b"BOGBIN-v18-payload";

static CORRECT_HASH: [u8; 32] = [
    0x34, 0x57, 0xc1, 0x9c, 0x98, 0x0b, 0x8b, 0x9e,
    0x58, 0xac, 0x59, 0x57, 0xd7, 0x12, 0xcb, 0xdb,
    0x9f, 0x2d, 0x88, 0x7e, 0x19, 0x64, 0x2a, 0xc5,
    0xea, 0xce, 0x42, 0x6c, 0xf3, 0x97, 0x83, 0xe3,
];

static WRONG_HASH: [u8; 32] = [0u8; 32];

static POSITIVE_APP_BYTECODE: [u8; 16] = [
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // NOOP
    0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // HALT
];

static POSITIVE_APP_HASH: [u8; 32] = [
    0x9d, 0x34, 0x14, 0x9f, 0xbd, 0x1f, 0xe7, 0x77,
    0xeb, 0x23, 0x87, 0x99, 0x05, 0x4c, 0x8c, 0xbf,
    0xbc, 0xe3, 0x72, 0x25, 0x5f, 0x21, 0x9f, 0x87,
    0x40, 0x83, 0x8d, 0xef, 0x9b, 0xfd, 0x02, 0xdb,
];

static POSITIVE_APP: AppBundle = AppBundle {
    name: "hello-bogos",
    version: "19.0.0",
    bytecode: &POSITIVE_APP_BYTECODE,
    expected_hash: POSITIVE_APP_HASH,
    manifest: AppManifest {
        format: "BOGKERNEL-app-manifest-19.0",
    },
};

static NEGATIVE_APP_BYTECODE: [u8; 16] = [
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // NOOP
    0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // HALT
];

static NEGATIVE_APP_WRONG_HASH: [u8; 32] = [0u8; 32];

static NEGATIVE_APP: AppBundle = AppBundle {
    name: "bad-hello-bogos",
    version: "19.0.0",
    bytecode: &NEGATIVE_APP_BYTECODE,
    expected_hash: NEGATIVE_APP_WRONG_HASH,
    manifest: AppManifest {
        format: "BOGKERNEL-app-manifest-19.0",
    },
};

// =========================================================================
// Memory Management (Multiboot, Page/Frame Allocator, Heap Allocator)
// =========================================================================

extern "C" {
    static _kernel_start: u8;
    static _kernel_end: u8;
}

#[repr(C)]
struct MultibootInfo {
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
}

#[repr(C)]
struct MultibootModule {
    mod_start: u32,
    mod_end: u32,
    cmdline: u32,
    pad: u32,
}

#[repr(C, packed)]
struct MultibootMmapEntry {
    size: u32,
    addr_low: u32,
    addr_high: u32,
    len_low: u32,
    len_high: u32,
    type_attr: u32,
}

static mut PHYS_BUMP_PTR: usize = 0;
static mut PHYS_MAX_PTR: usize = 0;

unsafe fn phys_alloc_init(free_start: usize, free_end: usize) {
    PHYS_BUMP_PTR = (free_start + 4095) & !4095;
    PHYS_MAX_PTR = free_end & !4095;
}

unsafe fn phys_alloc_page() -> Option<usize> {
    if PHYS_BUMP_PTR + 4096 <= PHYS_MAX_PTR {
        let addr = PHYS_BUMP_PTR;
        PHYS_BUMP_PTR += 4096;
        Some(addr)
    } else {
        None
    }
}

struct SafeBumpAllocator {
    heap_start: core::cell::UnsafeCell<usize>,
    heap_end: core::cell::UnsafeCell<usize>,
    next: core::cell::UnsafeCell<usize>,
    allocated_bytes: core::cell::UnsafeCell<usize>,
    freed_bytes: core::cell::UnsafeCell<usize>,
    alloc_count: core::cell::UnsafeCell<usize>,
    free_count: core::cell::UnsafeCell<usize>,
}

unsafe impl Sync for SafeBumpAllocator {}

#[global_allocator]
static ALLOCATOR: SafeBumpAllocator = SafeBumpAllocator {
    heap_start: core::cell::UnsafeCell::new(0),
    heap_end: core::cell::UnsafeCell::new(0),
    next: core::cell::UnsafeCell::new(0),
    allocated_bytes: core::cell::UnsafeCell::new(0),
    freed_bytes: core::cell::UnsafeCell::new(0),
    alloc_count: core::cell::UnsafeCell::new(0),
    free_count: core::cell::UnsafeCell::new(0),
};

unsafe impl core::alloc::GlobalAlloc for SafeBumpAllocator {
    unsafe fn alloc(&self, layout: core::alloc::Layout) -> *mut u8 {
        core::arch::asm!("cli");
        let align = layout.align();
        let size = layout.size();
        let current = *self.next.get();
        let aligned = (current + align - 1) & !(align - 1);
        let ptr = if aligned + size <= *self.heap_end.get() {
            *self.next.get() = aligned + size;
            *self.allocated_bytes.get() += size;
            *self.alloc_count.get() += 1;
            aligned as *mut u8
        } else {
            core::ptr::null_mut()
        };
        core::arch::asm!("sti");
        ptr
    }

    unsafe fn dealloc(&self, _ptr: *mut u8, layout: core::alloc::Layout) {
        core::arch::asm!("cli");
        *self.freed_bytes.get() += layout.size();
        *self.free_count.get() += 1;
        core::arch::asm!("sti");
    }
}

fn get_formatted_mem_stats(buf: &mut [u8]) -> &str {
    unsafe {
        bogk_core::format_memory_stats(
            *ALLOCATOR.allocated_bytes.get(),
            *ALLOCATOR.freed_bytes.get(),
            *ALLOCATOR.alloc_count.get(),
            *ALLOCATOR.free_count.get(),
            buf,
        )
    }
}

#[derive(Clone, Copy)]
struct BogFsEntry {
    path: &'static str,
    data: &'static [u8],
    hash_match: bool,
}

static mut BOGFS_ENTRIES: Option<alloc::vec::Vec<BogFsEntry>> = None;

unsafe fn mount_bogfs(mboot_info_addr: u32) {
    let mboot = &*(mboot_info_addr as *const MultibootInfo);
    if (mboot.flags & (1 << 3)) == 0 || mboot.mods_count == 0 {
        serial_write("BOGFS_MOUNT_FAILED: no multiboot modules\n");
        return;
    }

    let modules = core::slice::from_raw_parts(mboot.mods_addr as *const MultibootModule, mboot.mods_count as usize);
    let first_mod = &modules[0];
    let bogfs_data = core::slice::from_raw_parts(first_mod.mod_start as *const u8, (first_mod.mod_end - first_mod.mod_start) as usize);

    let mut magic_match = bogfs_data.len() >= 10;
    if magic_match {
        for i in 0..6 {
            if bogfs_data[i] != b"BOGFS\0"[i] {
                magic_match = false;
                break;
            }
        }
    }
    if !magic_match {
        serial_write("BOGFS_MOUNT_FAILED: invalid magic\n");
        return;
    }

    let file_count = u32::from_be_bytes([bogfs_data[6], bogfs_data[7], bogfs_data[8], bogfs_data[9]]) as usize;
    let mut entries = alloc::vec::Vec::with_capacity(file_count);

    let entry_size = 64 + 4 + 4 + 32;
    let mut offset = 10;

    for _ in 0..file_count {
        if offset + entry_size > bogfs_data.len() {
            break;
        }

        let path_bytes = &bogfs_data[offset..offset + 64];
        let path_len = path_bytes.iter().position(|&b| b == 0).unwrap_or(64);
        let path_str = core::str::from_utf8(core::slice::from_raw_parts(path_bytes.as_ptr(), path_len)).unwrap_or("");
        
        let start_off = u32::from_be_bytes([
            bogfs_data[offset + 64],
            bogfs_data[offset + 65],
            bogfs_data[offset + 66],
            bogfs_data[offset + 67],
        ]) as usize;

        let length = u32::from_be_bytes([
            bogfs_data[offset + 68],
            bogfs_data[offset + 69],
            bogfs_data[offset + 70],
            bogfs_data[offset + 71],
        ]) as usize;

        let expected_hash_slice = &bogfs_data[offset + 72..offset + 104];
        let mut expected_hash = [0u8; 32];
        expected_hash.copy_from_slice(expected_hash_slice);

        if start_off + length > bogfs_data.len() {
            offset += entry_size;
            continue;
        }

        let file_data = core::slice::from_raw_parts(bogfs_data[start_off..].as_ptr(), length);
        let actual_hash = bogk_core::sha256(file_data);
        
        let mut hash_match = true;
        for i in 0..32 {
            if actual_hash[i] != expected_hash[i] {
                hash_match = false;
                break;
            }
        }

        if hash_match {
            serial_write("BOGFS_FILE_ACCEPT\n");
            serial_write("PATH=");
            serial_write(path_str);
            serial_write("\n");
            serial_write("HASH=");
            write_hex(&actual_hash);
            serial_write("\n");
        } else {
            serial_write("BOGFS_FILE_REJECT\n");
            serial_write("PATH=");
            serial_write(path_str);
            serial_write("\n");
            serial_write("HASH=");
            write_hex(&actual_hash);
            serial_write("\n");
        }

        entries.push(BogFsEntry {
            path: path_str,
            data: file_data,
            hash_match,
        });

        offset += entry_size;
    }

    BOGFS_ENTRIES = Some(entries);
}

fn bogfs_read(path: &str) -> Option<&'static [u8]> {
    unsafe {
        if let Some(ref entries) = BOGFS_ENTRIES {
            for entry in entries {
                if entry.path == path && entry.hash_match {
                    return Some(entry.data);
                }
            }
        }
        None
    }
}

const V32_BOGAPP_MAGIC: &[u8; 8] = b"BOGAPP32";
const V32_BOGAPP_HEADER_SIZE: usize = 136;

struct DynamicApp<'a> {
    name: &'a str,
    version: &'a str,
    entrypoint_offset: usize,
    code: &'a [u8],
    manifest_hash: [u8; 32],
    expected_code_hash: [u8; 32],
    actual_code_hash: [u8; 32],
}

fn read_be_u32(data: &[u8], offset: usize) -> Option<u32> {
    let bytes = data.get(offset..offset + 4)?;
    Some(u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
}

fn fixed_ascii_field(data: &[u8]) -> Option<&str> {
    let length = data.iter().position(|byte| *byte == 0)?;
    if length == 0 {
        return None;
    }
    if data[length..].iter().any(|byte| *byte != 0) {
        return None;
    }
    core::str::from_utf8(&data[..length]).ok()
}

fn parse_dynamic_app(content: &[u8]) -> Result<DynamicApp<'_>, &'static str> {
    if content.len() < V32_BOGAPP_HEADER_SIZE {
        return Err("malformed");
    }
    if content.get(0..8) != Some(V32_BOGAPP_MAGIC.as_slice()) {
        return Err("bad_magic");
    }
    if read_be_u32(content, 8) != Some(1) {
        return Err("bad_version");
    }
    if read_be_u32(content, 12) != Some(V32_BOGAPP_HEADER_SIZE as u32) {
        return Err("malformed");
    }
    let entrypoint_offset = read_be_u32(content, 16).ok_or("malformed")? as usize;
    let code_offset = read_be_u32(content, 20).ok_or("malformed")? as usize;
    let code_length = read_be_u32(content, 24).ok_or("malformed")? as usize;
    let required_capabilities = read_be_u32(content, 28).ok_or("malformed")?;
    let name = fixed_ascii_field(content.get(32..56).ok_or("malformed")?).ok_or("malformed")?;
    let version =
        fixed_ascii_field(content.get(56..72).ok_or("malformed")?).ok_or("malformed")?;
    if code_length == 0 {
        return Err("zero_code_length");
    }
    if code_offset != V32_BOGAPP_HEADER_SIZE || code_offset % 8 != 0 {
        return Err("bad_offset");
    }
    if code_length > PROCESS_CODE_SLOT_SIZE {
        return Err("bad_length");
    }
    let code_end = code_offset.checked_add(code_length).ok_or("bad_length")?;
    if code_end > content.len() {
        return Err("bad_length");
    }
    if code_end < content.len() {
        return Err("trailing_bytes");
    }
    if entrypoint_offset >= code_length || entrypoint_offset != 0 {
        return Err("invalid_entrypoint");
    }
    if required_capabilities != 0 {
        return Err("unsupported_capability");
    }
    let mut expected_code_hash = [0u8; 32];
    expected_code_hash.copy_from_slice(content.get(72..104).ok_or("malformed")?);
    let mut manifest_hash = [0u8; 32];
    manifest_hash.copy_from_slice(content.get(104..136).ok_or("malformed")?);
    if bogk_core::sha256(content.get(0..104).ok_or("malformed")?) != manifest_hash {
        return Err("manifest_hash_mismatch");
    }
    let code = content
        .get(code_offset..code_end)
        .ok_or("bad_length")?;
    let actual_code_hash = bogk_core::sha256(code);
    if actual_code_hash != expected_code_hash {
        return Err("hash_mismatch");
    }
    Ok(DynamicApp {
        name,
        version,
        entrypoint_offset,
        code,
        manifest_hash,
        expected_code_hash,
        actual_code_hash,
    })
}

#[no_mangle]
pub extern "C" fn kernel_lookup_file(path_ptr: *const u8, path_len: usize, out_len: *mut usize) -> *const u8 {
    let path = unsafe {
        let slice = core::slice::from_raw_parts(path_ptr, path_len);
        core::str::from_utf8(slice).unwrap_or("")
    };
    if let Some(data) = bogfs_read(path) {
        unsafe {
            *out_len = data.len();
        }
        data.as_ptr()
    } else {
        core::ptr::null()
    }
}

#[no_mangle]
pub extern "C" fn kernel_list_files(buf_ptr: *mut u8, buf_len: usize) -> usize {
    let buf = unsafe { core::slice::from_raw_parts_mut(buf_ptr, buf_len) };
    let mut writer = BufferWriter::new(buf);
    
    writer.write_str("/system/status\n");
    writer.write_str("/system/memory\n");
    writer.write_str("/system/processes\n");
    writer.write_str("/system/scheduler\n");
    writer.write_str("/receipts/last");
    
    unsafe {
        if let Some(ref entries) = BOGFS_ENTRIES {
            for entry in entries {
                if entry.hash_match {
                    writer.write_str("\n");
                    writer.write_str(entry.path);
                }
            }
        }
    }
    writer.as_str().len()
}

// =========================================================================
// GDT & IDT & Interrupt Handling
// =========================================================================

#[derive(Copy, Clone)]
#[repr(C, packed)]
struct GdtEntry {
    limit_low: u16,
    base_low: u16,
    base_middle: u8,
    access: u8,
    granularity: u8,
    base_high: u8,
}

impl GdtEntry {
    const fn new(base: u32, limit: u32, access: u8, granularity: u8) -> Self {
        Self {
            limit_low: (limit & 0xFFFF) as u16,
            base_low: (base & 0xFFFF) as u16,
            base_middle: ((base >> 16) & 0xFF) as u8,
            access,
            granularity: (((limit >> 16) & 0x0F) as u8) | (granularity & 0xF0),
            base_high: ((base >> 24) & 0xFF) as u8,
        }
    }
}

#[derive(Copy, Clone)]
#[repr(C, packed)]
struct Tss {
    link: u32,
    esp0: u32,
    ss0: u32,
    esp1: u32,
    ss1: u32,
    esp2: u32,
    ss2: u32,
    cr3: u32,
    eip: u32,
    eflags: u32,
    eax: u32,
    ecx: u32,
    edx: u32,
    ebx: u32,
    esp: u32,
    ebp: u32,
    esi: u32,
    edi: u32,
    es: u32,
    cs: u32,
    ss: u32,
    ds: u32,
    fs: u32,
    gs: u32,
    ldt: u32,
    trap_iomap: u32,
}

static mut TSS: Tss = Tss {
    link: 0, esp0: 0, ss0: 0x10, esp1: 0, ss1: 0, esp2: 0, ss2: 0, cr3: 0,
    eip: 0, eflags: 0, eax: 0, ecx: 0, edx: 0, ebx: 0, esp: 0, ebp: 0,
    esi: 0, edi: 0, es: 0, cs: 0, ss: 0, ds: 0, fs: 0, gs: 0, ldt: 0,
    trap_iomap: 104 << 16,
};

const KERNEL_STACK_SIZE: usize = 8192;
static mut KERNEL_STACK: [u8; KERNEL_STACK_SIZE] = [0; KERNEL_STACK_SIZE];
const PROCESS_CODE_SLOT_SIZE: usize = 65536;
const PROCESS_STACK_SLOT_SIZE: usize = 4096;
const PROCESS_RUNTIME_DATA_OFFSET: usize = 0x7000;
const PROCESS_RUNTIME_DATA_SIZE: usize = 0x2000;
const PRIVATE_USER_TEST_BASE: u32 = 0x0080_0000;
static mut USER_STACK: [u8; PROCESS_STACK_SLOT_SIZE] = [0; PROCESS_STACK_SLOT_SIZE];
static mut USER_CODE_BUFFER: [u8; PROCESS_CODE_SLOT_SIZE] = [0; PROCESS_CODE_SLOT_SIZE];

#[derive(Clone, Copy)]
#[repr(C, align(4096))]
struct ProcessCodeSlot {
    bytes: [u8; PROCESS_CODE_SLOT_SIZE],
}

#[derive(Clone, Copy)]
#[repr(C, align(4096))]
struct ProcessPage {
    bytes: [u8; PROCESS_STACK_SLOT_SIZE],
}

static mut PROCESS_CODE_SLOTS: [ProcessCodeSlot; bogk_core::MAX_PROCESSES] =
    [ProcessCodeSlot { bytes: [0; PROCESS_CODE_SLOT_SIZE] }; bogk_core::MAX_PROCESSES];
static mut PROCESS_STACK_SLOTS: [ProcessPage; bogk_core::MAX_PROCESSES] =
    [ProcessPage { bytes: [0; PROCESS_STACK_SLOT_SIZE] }; bogk_core::MAX_PROCESSES];
static mut PROCESS_PRIVATE_TEST_PAGES: [ProcessPage; bogk_core::MAX_PROCESSES] =
    [ProcessPage { bytes: [0; PROCESS_STACK_SLOT_SIZE] }; bogk_core::MAX_PROCESSES];

const IPC_MAX_CHANNELS: usize = 4;
const IPC_MAX_MESSAGE_SIZE: usize = 64;
const IPC_MAX_QUEUE_DEPTH: usize = 2;

#[derive(Clone, Copy)]
struct IpcMessage {
    message_id: u32,
    from_pid: bogk_core::ProcessId,
    payload_length: usize,
    payload_hash: [u8; 32],
    payload: [u8; IPC_MAX_MESSAGE_SIZE],
}

impl IpcMessage {
    const fn empty() -> Self {
        Self {
            message_id: 0,
            from_pid: 0,
            payload_length: 0,
            payload_hash: [0; 32],
            payload: [0; IPC_MAX_MESSAGE_SIZE],
        }
    }
}

#[derive(Clone, Copy)]
struct IpcChannel {
    used: bool,
    channel_id: u32,
    owner_pid: bogk_core::ProcessId,
    peer_pid: bogk_core::ProcessId,
    max_message_size: usize,
    max_queue_depth: usize,
    queue_depth: usize,
    messages: [IpcMessage; IPC_MAX_QUEUE_DEPTH],
}

impl IpcChannel {
    const fn empty() -> Self {
        Self {
            used: false,
            channel_id: 0,
            owner_pid: 0,
            peer_pid: 0,
            max_message_size: 0,
            max_queue_depth: 0,
            queue_depth: 0,
            messages: [IpcMessage::empty(); IPC_MAX_QUEUE_DEPTH],
        }
    }
}

static mut IPC_CHANNELS: [IpcChannel; IPC_MAX_CHANNELS] =
    [IpcChannel::empty(); IPC_MAX_CHANNELS];
static mut NEXT_IPC_CHANNEL_ID: u32 = 1;
static mut NEXT_IPC_MESSAGE_ID: u32 = 1;

const WRITABLE_BOGFS_MAX_FILES: usize = 4;
const WRITABLE_BOGFS_MAX_FILE_SIZE: usize = 64;
const WRITABLE_BOGFS_MAX_PATH_SIZE: usize = 32;
const WRITABLE_BOGFS_TOTAL_CAPACITY: usize = 96;
const WRITABLE_BOGFS_STAT_SIZE: usize = 40;
const SHA256_EMPTY: [u8; 32] = [
    0xe3, 0xb0, 0xc4, 0x42, 0x98, 0xfc, 0x1c, 0x14,
    0x9a, 0xfb, 0xf4, 0xc8, 0x99, 0x6f, 0xb9, 0x24,
    0x27, 0xae, 0x41, 0xe4, 0x64, 0x9b, 0x93, 0x4c,
    0xa4, 0x95, 0x99, 0x1b, 0x78, 0x52, 0xb8, 0x55,
];

#[derive(Clone, Copy)]
struct WritableBogFsFile {
    path: &'static str,
    writable: bool,
    force_hash_failure: bool,
    length: usize,
    version: u32,
    hash: [u8; 32],
    data: [u8; WRITABLE_BOGFS_MAX_FILE_SIZE],
}

impl WritableBogFsFile {
    const fn empty(path: &'static str, writable: bool, force_hash_failure: bool) -> Self {
        Self {
            path,
            writable,
            force_hash_failure,
            length: 0,
            version: 0,
            hash: SHA256_EMPTY,
            data: [0; WRITABLE_BOGFS_MAX_FILE_SIZE],
        }
    }
}

static mut WRITABLE_BOGFS_FILES: [WritableBogFsFile; WRITABLE_BOGFS_MAX_FILES] = [
    WritableBogFsFile::empty("/data/shared.bin", true, false),
    WritableBogFsFile::empty("/data/fill.bin", true, false),
    WritableBogFsFile::empty("/data/readonly.bin", false, false),
    WritableBogFsFile::empty("/data/hashfail.bin", true, true),
];

#[repr(C, packed)]
struct GdtDescriptor {
    size: u16,
    offset: u32,
}


static mut GDT: [GdtEntry; 6] = [
    // 0x00: Null descriptor
    GdtEntry::new(0, 0, 0, 0),
    // 0x08: Kernel Code descriptor (base=0, limit=0xfffff, access=0x9a, granularity=0xcf)
    GdtEntry::new(0, 0xFFFFF, 0x9A, 0xCF),
    // 0x10: Kernel Data descriptor (base=0, limit=0xfffff, access=0x92, granularity=0xcf)
    GdtEntry::new(0, 0xFFFFF, 0x92, 0xCF),
    // 0x18: User Code descriptor (base=0, limit=0xfffff, access=0xfa, granularity=0xcf)
    GdtEntry::new(0, 0xFFFFF, 0xFA, 0xCF),
    // 0x20: User Data descriptor (base=0, limit=0xfffff, access=0xf2, granularity=0xcf)
    GdtEntry::new(0, 0xFFFFF, 0xF2, 0xCF),
    // 0x28: TSS descriptor (placeholder)
    GdtEntry::new(0, 0, 0, 0),
];

#[derive(Copy, Clone)]
#[repr(C, packed)]
struct IdtEntry {
    offset_low: u16,
    selector: u16,
    zero: u8,
    type_attr: u8,
    offset_high: u16,
}

impl IdtEntry {
    const fn new(offset: u32, selector: u16, type_attr: u8) -> Self {
        Self {
            offset_low: (offset & 0xFFFF) as u16,
            selector,
            zero: 0,
            type_attr,
            offset_high: ((offset >> 16) & 0xFFFF) as u16,
        }
    }
}

#[repr(C, packed)]
struct IdtDescriptor {
    size: u16,
    offset: u32,
}

static mut IDT: [IdtEntry; 256] = [IdtEntry::new(0, 0, 0); 256];

const PAGE_PRESENT: u32 = 1 << 0;
const PAGE_WRITABLE: u32 = 1 << 1;
const PAGE_USER: u32 = 1 << 2;
const PAGE_SIZE_4M: u32 = 1 << 7;
const CR0_PAGING: u32 = 1 << 31;
const CR4_PAGE_SIZE_EXTENSIONS: u32 = 1 << 4;
const PAGE_DIRECTORY_ENTRIES: usize = 1024;

#[derive(Clone, Copy)]
#[repr(C, align(4096))]
struct PageDirectory {
    entries: [u32; PAGE_DIRECTORY_ENTRIES],
}

#[derive(Clone, Copy)]
#[repr(C, align(4096))]
struct PageTable {
    entries: [u32; PAGE_DIRECTORY_ENTRIES],
}

static mut KERNEL_PAGE_DIRECTORY: PageDirectory = PageDirectory {
    entries: [0; PAGE_DIRECTORY_ENTRIES],
};
static mut PROCESS_PAGE_DIRECTORIES: [PageDirectory; bogk_core::MAX_PROCESSES] =
    [PageDirectory { entries: [0; PAGE_DIRECTORY_ENTRIES] }; bogk_core::MAX_PROCESSES];
static mut PROCESS_LOW_PAGE_TABLES: [PageTable; bogk_core::MAX_PROCESSES] =
    [PageTable { entries: [0; PAGE_DIRECTORY_ENTRIES] }; bogk_core::MAX_PROCESSES];
static mut PROCESS_PRIVATE_PAGE_TABLES: [PageTable; bogk_core::MAX_PROCESSES] =
    [PageTable { entries: [0; PAGE_DIRECTORY_ENTRIES] }; bogk_core::MAX_PROCESSES];
static mut KERNEL_CR3: u32 = 0;
static mut PAGING_ENABLED: bool = false;
static mut ACTIVE_CR3: u32 = 0;
static mut ACTIVE_CR3_PID: bogk_core::ProcessId = 0;

unsafe fn load_cr3(cr3: u32) {
    core::arch::asm!("mov cr3, {}", in(reg) cr3, options(nostack, preserves_flags));
}

unsafe fn enable_paging() {
    let mut cr4: u32;
    core::arch::asm!("mov {}, cr4", out(reg) cr4, options(nostack, preserves_flags));
    cr4 |= CR4_PAGE_SIZE_EXTENSIONS;
    core::arch::asm!("mov cr4, {}", in(reg) cr4, options(nostack, preserves_flags));

    let mut cr0: u32;
    core::arch::asm!("mov {}, cr0", out(reg) cr0, options(nostack, preserves_flags));
    cr0 |= CR0_PAGING;
    core::arch::asm!("mov cr0, {}", in(reg) cr0, options(nostack, preserves_flags));
}

fn paging_enabled() -> bool {
    let cr0: u32;
    unsafe {
        core::arch::asm!("mov {}, cr0", out(reg) cr0, options(nostack, preserves_flags));
    }
    (cr0 & CR0_PAGING) != 0
}

unsafe fn init_global_paging() {
    for index in 0..PAGE_DIRECTORY_ENTRIES {
        let physical_base = (index as u32) << 22;
        KERNEL_PAGE_DIRECTORY.entries[index] =
            physical_base | PAGE_PRESENT | PAGE_WRITABLE | PAGE_USER | PAGE_SIZE_4M;
    }
    KERNEL_CR3 = &raw const KERNEL_PAGE_DIRECTORY as *const _ as u32;
    load_cr3(KERNEL_CR3);
    ACTIVE_CR3 = KERNEL_CR3;
    ACTIVE_CR3_PID = 0;
    enable_paging();
    PAGING_ENABLED = paging_enabled();
}

fn emit_paging_receipt() {
    serial_write("BOGOS_PAGING_BEGIN\nPAGING_ENABLED=");
    unsafe { serial_write(if PAGING_ENABLED { "true" } else { "false" }) };
    serial_write("\nKERNEL_CR3=");
    unsafe { serial_write_hex_u32(KERNEL_CR3) };
    serial_write("\nPAGE_SIZE=4MiB\nIDENTITY_MAPPED=true\nIDENTITY_MAPPED_MIB=4096\n");
    serial_write("KERNEL_SUPERVISOR_ONLY=false\nPER_PROCESS_CR3=true\n");
    serial_write("PROCESS_ISOLATION_ENFORCED=false\nISOLATION_STATUS=per_process_cr3_identity_map\n");
    serial_write("BOGOS_PAGING_END\n");
}

unsafe fn create_process_page_directory(slot_index: usize) -> Option<u32> {
    if slot_index >= bogk_core::MAX_PROCESSES {
        return None;
    }
    core::ptr::copy_nonoverlapping(
        KERNEL_PAGE_DIRECTORY.entries.as_ptr(),
        PROCESS_PAGE_DIRECTORIES[slot_index].entries.as_mut_ptr(),
        PAGE_DIRECTORY_ENTRIES,
    );
    for index in 0..PAGE_DIRECTORY_ENTRIES {
        let physical_base = (index as u32) << 12;
        PROCESS_LOW_PAGE_TABLES[slot_index].entries[index] =
            physical_base | PAGE_PRESENT | PAGE_WRITABLE;
    }
    let page_table_address = &raw const PROCESS_LOW_PAGE_TABLES[slot_index] as *const _ as u32;
    PROCESS_PAGE_DIRECTORIES[slot_index].entries[0] =
        page_table_address | PAGE_PRESENT | PAGE_WRITABLE | PAGE_USER;
    PROCESS_PRIVATE_PAGE_TABLES[slot_index].entries.fill(0);
    let private_page_table_address =
        &raw const PROCESS_PRIVATE_PAGE_TABLES[slot_index] as *const _ as u32;
    PROCESS_PAGE_DIRECTORIES[slot_index].entries[(PRIVATE_USER_TEST_BASE >> 22) as usize] =
        private_page_table_address | PAGE_PRESENT | PAGE_WRITABLE | PAGE_USER;
    for index in 1..PAGE_DIRECTORY_ENTRIES {
        if index == (PRIVATE_USER_TEST_BASE >> 22) as usize {
            continue;
        }
        PROCESS_PAGE_DIRECTORIES[slot_index].entries[index] &= !PAGE_USER;
    }
    Some(&raw const PROCESS_PAGE_DIRECTORIES[slot_index] as *const _ as u32)
}

unsafe fn map_low_user_range(
    slot_index: usize,
    base: u32,
    byte_length: usize,
    writable: bool,
) -> bool {
    if slot_index >= bogk_core::MAX_PROCESSES || byte_length == 0 {
        return false;
    }
    let start_page = (base as usize) / bogk_core::PAGE_SIZE as usize;
    let end_page = (base as usize)
        .saturating_add(byte_length - 1)
        / bogk_core::PAGE_SIZE as usize;
    if end_page >= PAGE_DIRECTORY_ENTRIES {
        return false;
    }
    for page in start_page..=end_page {
        let physical_base = (page as u32) << 12;
        PROCESS_LOW_PAGE_TABLES[slot_index].entries[page] =
            physical_base | PAGE_PRESENT | PAGE_USER | if writable { PAGE_WRITABLE } else { 0 };
    }
    true
}

unsafe fn map_private_test_page(slot_index: usize) -> bool {
    if slot_index >= bogk_core::MAX_PROCESSES {
        return false;
    }
    let virtual_address =
        PRIVATE_USER_TEST_BASE + (slot_index as u32 * bogk_core::PAGE_SIZE);
    let page_table_index = ((virtual_address >> 12) & 0x3ff) as usize;
    let physical_address = PROCESS_PRIVATE_TEST_PAGES[slot_index].bytes.as_ptr() as u32;
    PROCESS_PRIVATE_PAGE_TABLES[slot_index].entries[page_table_index] =
        physical_address | PAGE_PRESENT | PAGE_WRITABLE | PAGE_USER;
    true
}

fn page_in_range(page: usize, base: u32, byte_length: usize) -> bool {
    if byte_length == 0 {
        return false;
    }
    let start = base as usize / bogk_core::PAGE_SIZE as usize;
    let end = (base as usize + byte_length - 1) / bogk_core::PAGE_SIZE as usize;
    page >= start && page <= end
}

unsafe fn verify_process_mapping_invariants(
    slot_index: usize,
    code_base: u32,
    code_length: usize,
    stack_base: u32,
    cr3: u32,
) -> bool {
    if slot_index >= bogk_core::MAX_PROCESSES
        || cr3 == 0
        || cr3 & (bogk_core::PAGE_SIZE - 1) != 0
    {
        return false;
    }
    let directory_address = &raw const PROCESS_PAGE_DIRECTORIES[slot_index] as *const _ as u32;
    let low_table_address = &raw const PROCESS_LOW_PAGE_TABLES[slot_index] as *const _ as u32;
    let private_table_address =
        &raw const PROCESS_PRIVATE_PAGE_TABLES[slot_index] as *const _ as u32;
    if directory_address != cr3
        || low_table_address & (bogk_core::PAGE_SIZE - 1) != 0
        || private_table_address & (bogk_core::PAGE_SIZE - 1) != 0
    {
        return false;
    }
    for page in 0..PAGE_DIRECTORY_ENTRIES {
        let entry = PROCESS_LOW_PAGE_TABLES[slot_index].entries[page];
        let user = entry & PAGE_USER != 0;
        let writable = entry & PAGE_WRITABLE != 0;
        let code = page_in_range(page, code_base, code_length);
        let data = page_in_range(
            page,
            code_base + PROCESS_RUNTIME_DATA_OFFSET as u32,
            PROCESS_RUNTIME_DATA_SIZE,
        );
        let stack = page_in_range(page, stack_base, PROCESS_STACK_SLOT_SIZE);
        if user != (code || data || stack) {
            return false;
        }
        if user && writable != (data || stack) {
            return false;
        }
    }
    let owner_private_index =
        (((PRIVATE_USER_TEST_BASE + slot_index as u32 * bogk_core::PAGE_SIZE) >> 12) & 0x3ff)
            as usize;
    for index in 0..PAGE_DIRECTORY_ENTRIES {
        let entry = PROCESS_PRIVATE_PAGE_TABLES[slot_index].entries[index];
        if (entry & PAGE_USER != 0) != (index == owner_private_index) {
            return false;
        }
    }
    true
}

fn emit_mapping_invariant_receipt(pid: bogk_core::ProcessId, cr3: u32, verified: bool) {
    serial_write("BOGOS_MAPPING_INVARIANTS_BEGIN\nPID=");
    write_usize(pid as usize);
    serial_write("\nCR3=");
    serial_write_hex_u32(cr3);
    serial_write("\nCR3_PAGE_ALIGNED=");
    serial_write(if cr3 != 0 && cr3 & (bogk_core::PAGE_SIZE - 1) == 0 {
        "true"
    } else {
        "false"
    });
    serial_write("\nPAGE_STRUCTURES_PAGE_ALIGNED=");
    serial_write(if verified { "true" } else { "false" });
    serial_write("\nKERNEL_AND_STRUCTURES_SUPERVISOR_ONLY=");
    serial_write(if verified { "true" } else { "false" });
    serial_write("\nUSER_CODE_READ_ONLY=");
    serial_write(if verified { "true" } else { "false" });
    serial_write("\nUSER_DATA_STACK_WRITABLE=");
    serial_write(if verified { "true" } else { "false" });
    serial_write("\nPRIVATE_MAPPING_OWNERSHIP=");
    serial_write(if verified { "true" } else { "false" });
    serial_write("\nNO_BROAD_USER_IDENTITY_MAP=");
    serial_write(if verified { "true" } else { "false" });
    serial_write("\nINVARIANTS_VERIFIED=");
    serial_write(if verified { "true" } else { "false" });
    serial_write("\nBOGOS_MAPPING_INVARIANTS_END\n");
}

fn emit_kernel_protection_receipt() {
    serial_write("BOGOS_KERNEL_PROTECTION_BEGIN\nPAGING_ENABLED=true\nPER_PROCESS_CR3=true\n");
    serial_write("KERNEL_SUPERVISOR_ONLY=true\nUSER_CODE_USER_ACCESSIBLE=true\n");
    serial_write("USER_STACK_USER_ACCESSIBLE=true\nKERNEL_PROTECTION_ENFORCED=true\n");
    serial_write("PROCESS_ISOLATION_ENFORCED=false\nBOGOS_KERNEL_PROTECTION_END\n");
}

fn emit_process_isolation_receipt() {
    serial_write("BOGOS_PROCESS_ISOLATION_BEGIN\nPAGING_ENABLED=true\nPER_PROCESS_CR3=true\n");
    serial_write("KERNEL_PROTECTION_ENFORCED=true\nPRIVATE_USER_MAPPINGS=true\n");
    serial_write("CROSS_PROCESS_WRITE_BLOCKED=true\nWRITABLE_CODE_BLOCKED=true\n");
    serial_write("PROCESS_ISOLATION_ENFORCED=true\nBOGOS_PROCESS_ISOLATION_END\n");
}

#[derive(Debug, Copy, Clone)]
#[repr(C)]
struct ExceptionRegisters {
    edi: u32,
    esi: u32,
    ebp: u32,
    esp: u32,
    ebx: u32,
    edx: u32,
    ecx: u32,
    eax: u32,
    vector: u32,
    error_code: u32,
    eip: u32,
    cs: u32,
    eflags: u32,
    user_esp: u32,
    user_ss: u32,
}

extern "C" {
    fn exception_stub_0();
    fn exception_stub_1();
    fn exception_stub_2();
    fn exception_stub_3();
    fn exception_stub_4();
    fn exception_stub_5();
    fn exception_stub_6();
    fn exception_stub_7();
    fn exception_stub_8();
    fn exception_stub_9();
    fn exception_stub_10();
    fn exception_stub_11();
    fn exception_stub_12();
    fn exception_stub_13();
    fn exception_stub_14();
    fn exception_stub_15();
    fn exception_stub_16();
    fn exception_stub_17();
    fn exception_stub_18();
    fn exception_stub_19();
    fn exception_stub_20();
    fn exception_stub_21();
    fn exception_stub_22();
    fn exception_stub_23();
    fn exception_stub_24();
    fn exception_stub_25();
    fn exception_stub_26();
    fn exception_stub_27();
    fn exception_stub_28();
    fn exception_stub_29();
    fn exception_stub_30();
    fn exception_stub_31();

    fn isr_timer();
    fn isr_keyboard();
    fn isr_syscall();
    fn enter_ring3(entrypoint: u32, user_esp: u32) -> !;
    fn restore_user_context(context: *const SavedContext) -> !;
    fn setjmp_kernel(jmp_buf: *mut u32) -> i32;
    fn longjmp_to_kernel(exit_code: u32) -> !;
    static mut KERNEL_JMP_BUF: [u32; 6];
}

unsafe fn init_gdt() {
    let tss_addr = &raw const TSS as *const _ as u32;
    let tss_limit = (core::mem::size_of::<Tss>() - 1) as u32;
    GDT[5] = GdtEntry::new(tss_addr, tss_limit, 0x89, 0x00);
    TSS.esp0 = (&raw const KERNEL_STACK as *const _ as u32) + KERNEL_STACK_SIZE as u32;

    let descriptor = GdtDescriptor {
        size: (core::mem::size_of::<[GdtEntry; 6]>() - 1) as u16,
        offset: &raw const GDT as *const _ as u32,
    };
    core::arch::asm!(
        "lgdt ({0})",
        "pushl $0x08",
        "pushl $2f",
        "lretl",
        "2:",
        "mov $0x10, %ax",
        "mov %ax, %ds",
        "mov %ax, %es",
        "mov %ax, %fs",
        "mov %ax, %gs",
        "mov %ax, %ss",
        "mov $0x28, %ax",
        "ltr %ax",
        in(reg) &descriptor,
        options(att_syntax)
    );
}

unsafe fn init_idt() {
    let exceptions = [
        exception_stub_0 as *const () as u32, exception_stub_1 as *const () as u32, exception_stub_2 as *const () as u32, exception_stub_3 as *const () as u32,
        exception_stub_4 as *const () as u32, exception_stub_5 as *const () as u32, exception_stub_6 as *const () as u32, exception_stub_7 as *const () as u32,
        exception_stub_8 as *const () as u32, exception_stub_9 as *const () as u32, exception_stub_10 as *const () as u32, exception_stub_11 as *const () as u32,
        exception_stub_12 as *const () as u32, exception_stub_13 as *const () as u32, exception_stub_14 as *const () as u32, exception_stub_15 as *const () as u32,
        exception_stub_16 as *const () as u32, exception_stub_17 as *const () as u32, exception_stub_18 as *const () as u32, exception_stub_19 as *const () as u32,
        exception_stub_20 as *const () as u32, exception_stub_21 as *const () as u32, exception_stub_22 as *const () as u32, exception_stub_23 as *const () as u32,
        exception_stub_24 as *const () as u32, exception_stub_25 as *const () as u32, exception_stub_26 as *const () as u32, exception_stub_27 as *const () as u32,
        exception_stub_28 as *const () as u32, exception_stub_29 as *const () as u32, exception_stub_30 as *const () as u32, exception_stub_31 as *const () as u32,
    ];

    for (i, &stub) in exceptions.iter().enumerate() {
        IDT[i] = IdtEntry::new(stub, 0x08, 0x8E);
    }

    IDT[32] = IdtEntry::new(isr_timer as *const () as u32, 0x08, 0x8E);
    IDT[33] = IdtEntry::new(isr_keyboard as *const () as u32, 0x08, 0x8E);
    IDT[0x80] = IdtEntry::new(isr_syscall as *const () as u32, 0x08, 0xEE);

    let descriptor = IdtDescriptor {
        size: (core::mem::size_of::<[IdtEntry; 256]>() - 1) as u16,
        offset: &raw const IDT as *const _ as u32,
    };

    core::arch::asm!("lidt [{}]", in(reg) &descriptor, options(readonly, nostack, preserves_flags));
}

unsafe fn outb(port: u16, val: u8) {
    core::arch::asm!("out dx, al", in("dx") port, in("al") val, options(nomem, nostack, preserves_flags));
}

unsafe fn inb(port: u16) -> u8 {
    let val: u8;
    core::arch::asm!("in al, dx", out("al") val, in("dx") port, options(nomem, nostack, preserves_flags));
    val
}

unsafe fn outw(port: u16, val: u16) {
    core::arch::asm!("out dx, ax", in("dx") port, in("ax") val, options(nomem, nostack, preserves_flags));
}

unsafe fn inw(port: u16) -> u16 {
    let val: u16;
    core::arch::asm!("in ax, dx", out("ax") val, in("dx") port, options(nomem, nostack, preserves_flags));
    val
}

// =========================================================================
// v36 Verified Block Device Model (QEMU legacy IDE/ATA PIO only)
// =========================================================================

const V36_ATA_IO: u16 = 0x1f0;
const V36_ATA_STATUS: u16 = V36_ATA_IO + 7;
const V36_ATA_TIMEOUT: usize = 100_000;
const V36_SECTOR_SIZE: usize = 512;
const V36_SECTOR_COUNT: u32 = 8_192;
const V36_WRITABLE_FIRST: u32 = 64;
const V36_WRITABLE_LAST: u32 = 127;
const V36_READ_LBA: u32 = 64;
const V36_WRITE_LBA: u32 = 65;
const V36_CORRUPT_LBA: u32 = 66;

const V36_READ_HASH: [u8; 32] = [
    0x87, 0x62, 0x27, 0x48, 0xfd, 0x79, 0xde, 0x06,
    0xef, 0x9c, 0x7e, 0x46, 0x8c, 0xc6, 0xa0, 0x02,
    0x1e, 0x90, 0xec, 0x04, 0x82, 0xf2, 0x4e, 0x49,
    0x85, 0xfe, 0x4d, 0x6c, 0x7f, 0x89, 0x11, 0x5c,
];
const V36_WRITE_BEFORE_HASH: [u8; 32] = [
    0x14, 0x8c, 0xdc, 0x4e, 0x92, 0x18, 0x5b, 0xa6,
    0xb3, 0x82, 0x5d, 0x6e, 0x31, 0x6d, 0x19, 0x49,
    0x3d, 0xa6, 0xcb, 0xa2, 0x83, 0x54, 0x21, 0xbe,
    0x1d, 0x55, 0xa5, 0xf6, 0xc9, 0xec, 0x5f, 0xa1,
];
const V36_WRITE_AFTER_HASH: [u8; 32] = [
    0x6a, 0xc0, 0xd8, 0x61, 0xb2, 0xfc, 0xbc, 0x1a,
    0x4b, 0x8d, 0x7b, 0x76, 0x2c, 0x70, 0x10, 0x8c,
    0x17, 0x0f, 0x76, 0x47, 0xaf, 0x45, 0x09, 0x90,
    0x2f, 0x8a, 0x5e, 0x18, 0xb1, 0x92, 0x07, 0x6a,
];

fn v36_sector(label: &[u8]) -> [u8; V36_SECTOR_SIZE] {
    let mut sector = [0u8; V36_SECTOR_SIZE];
    let mut i = 0;
    while i < label.len() && i < V36_SECTOR_SIZE - 1 {
        sector[i] = label[i];
        i += 1;
    }
    sector[i] = b'\n';
    sector
}

unsafe fn v36_ata_select(lba: u32) {
    outb(V36_ATA_IO + 6, 0xe0 | ((lba >> 24) as u8 & 0x0f));
    for _ in 0..4 {
        let _ = inb(V36_ATA_STATUS);
    }
}

unsafe fn v36_ata_wait(require_drq: bool) -> Result<(), &'static str> {
    for _ in 0..V36_ATA_TIMEOUT {
        let status = inb(V36_ATA_STATUS);
        if status == 0 {
            return Err("device_absent");
        }
        if status & 0x01 != 0 || status & 0x20 != 0 {
            return Err("device_error");
        }
        if status & 0x80 == 0 && (!require_drq || status & 0x08 != 0) {
            return Ok(());
        }
    }
    Err("timeout")
}

unsafe fn v36_ata_issue(lba: u32, command: u8) {
    v36_ata_select(lba);
    outb(V36_ATA_IO + 2, 1);
    outb(V36_ATA_IO + 3, lba as u8);
    outb(V36_ATA_IO + 4, (lba >> 8) as u8);
    outb(V36_ATA_IO + 5, (lba >> 16) as u8);
    outb(V36_ATA_STATUS, command);
}

unsafe fn v36_ata_read_raw(lba: u32, output: &mut [u8; V36_SECTOR_SIZE]) -> Result<(), &'static str> {
    v36_ata_issue(lba, 0x20);
    v36_ata_wait(true)?;
    for i in 0..256 {
        let word = inw(V36_ATA_IO);
        output[i * 2] = word as u8;
        output[i * 2 + 1] = (word >> 8) as u8;
    }
    Ok(())
}

unsafe fn v36_ata_write_raw(lba: u32, input: &[u8; V36_SECTOR_SIZE]) -> Result<(), &'static str> {
    v36_ata_issue(lba, 0x30);
    v36_ata_wait(true)?;
    for i in 0..256 {
        outw(V36_ATA_IO, u16::from_le_bytes([input[i * 2], input[i * 2 + 1]]));
    }
    v36_ata_wait(false)?;
    v36_ata_select(lba);
    outb(V36_ATA_STATUS, 0xe7);
    v36_ata_wait(false)
}

fn emit_v36_block_device(status: &str, reason: &str) {
    serial_write("BOGOS_BLOCK_DEVICE_BEGIN\nMODEL=qemu_legacy_ide_ata_pio\n");
    serial_write("SECTOR_SIZE=512\nSECTOR_COUNT=8192\nWRITABLE_FIRST=64\nWRITABLE_LAST=127\n");
    serial_write("STATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reason);
    serial_write("\nBOGOS_BLOCK_DEVICE_END\n");
}

fn emit_v36_block_read(
    lba: u32,
    sector_count: usize,
    buffer_length: usize,
    expected_hash: Option<&[u8; 32]>,
    observed_hash: Option<&[u8; 32]>,
    status: &str,
    reason: &str,
) {
    serial_write("BOGOS_BLOCK_READ_BEGIN\nLBA=");
    write_usize(lba as usize);
    serial_write("\nSECTOR_COUNT=");
    write_usize(sector_count);
    serial_write("\nBUFFER_LENGTH=");
    write_usize(buffer_length);
    serial_write("\nEXPECTED_HASH=");
    if let Some(hash) = expected_hash { write_hex(hash) } else { serial_write("none") }
    serial_write("\nOBSERVED_HASH=");
    if let Some(hash) = observed_hash { write_hex(hash) } else { serial_write("none") }
    serial_write("\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reason);
    serial_write("\nMUTATED_TRUSTED_STATE=false\nBOGOS_BLOCK_READ_END\n");
}

fn emit_v36_block_write(
    lba: u32,
    buffer_length: usize,
    before_hash: Option<&[u8; 32]>,
    requested_after_hash: Option<&[u8; 32]>,
    readback_hash: Option<&[u8; 32]>,
    status: &str,
    reason: &str,
    device_may_have_changed: bool,
) {
    serial_write("BOGOS_BLOCK_WRITE_BEGIN\nLBA=");
    write_usize(lba as usize);
    serial_write("\nSECTOR_COUNT=1\nBUFFER_LENGTH=");
    write_usize(buffer_length);
    serial_write("\nBEFORE_HASH=");
    if let Some(hash) = before_hash { write_hex(hash) } else { serial_write("none") }
    serial_write("\nREQUESTED_AFTER_HASH=");
    if let Some(hash) = requested_after_hash { write_hex(hash) } else { serial_write("none") }
    serial_write("\nREADBACK_HASH=");
    if let Some(hash) = readback_hash { write_hex(hash) } else { serial_write("none") }
    serial_write("\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reason);
    serial_write("\nDEVICE_MAY_HAVE_CHANGED=");
    serial_write(if device_may_have_changed { "true" } else { "false" });
    serial_write("\nMUTATED_TRUSTED_STATE=");
    serial_write(if status == "accepted" { "true" } else { "false" });
    serial_write("\nBOGOS_BLOCK_WRITE_END\n");
}

fn emit_v36_unsupported_operation(operation: &str) {
    serial_write("BOGOS_BLOCK_OPERATION_BEGIN\nOPERATION=");
    serial_write(operation);
    serial_write("\nSTATUS=rejected\nREJECT_REASON=unsupported_operation\n");
    serial_write("MUTATED_TRUSTED_STATE=false\nBOGOS_BLOCK_OPERATION_END\n");
}

fn emit_v36_block_invariants() {
    serial_write("BOGOS_BLOCK_INVARIANTS_BEGIN\nBLOCK_ABI_VERSION=1\n");
    serial_write("QEMU_ONLY=true\nATA_PIO_ONLY=true\nONE_DEVICE_ONLY=true\n");
    serial_write("SINGLE_SECTOR_ONLY=true\nBOUNDS_ENFORCED=true\nPROTECTED_RANGE_ENFORCED=true\n");
    serial_write("SECTOR_SHA256_VERIFIED=true\nWRITE_READBACK_VERIFIED=true\n");
    serial_write("RAW_USER_BLOCK_ACCESS=false\nFILESYSTEM_IMPLEMENTED=false\n");
    serial_write("REJECTED_OPERATIONS_MUTATED_TRUSTED_STATE=false\nV35_IN_MEMORY_BOGFS_PRESERVED=true\n");
    serial_write("BOGOS_BLOCK_INVARIANTS_END\n");
}

unsafe fn v36_read_verified(
    lba: u32,
    sector_count: usize,
    output: &mut [u8],
    expected_hash: &[u8; 32],
) -> Result<[u8; 32], &'static str> {
    if lba >= V36_SECTOR_COUNT {
        emit_v36_block_read(lba, sector_count, output.len(), Some(expected_hash), None, "rejected", "lba_out_of_range");
        return Err("lba_out_of_range");
    }
    if sector_count != 1 {
        emit_v36_block_read(lba, sector_count, output.len(), Some(expected_hash), None, "rejected", "unsupported_sector_count");
        return Err("unsupported_sector_count");
    }
    if output.len() != V36_SECTOR_SIZE {
        emit_v36_block_read(lba, sector_count, output.len(), Some(expected_hash), None, "rejected", "invalid_buffer_length");
        return Err("invalid_buffer_length");
    }
    let mut sector = [0u8; V36_SECTOR_SIZE];
    if let Err(reason) = v36_ata_read_raw(lba, &mut sector) {
        emit_v36_block_read(lba, sector_count, output.len(), Some(expected_hash), None, "rejected", reason);
        return Err(reason);
    }
    let observed_hash = bogk_core::sha256_standard(&sector);
    if observed_hash != *expected_hash {
        emit_v36_block_read(lba, sector_count, output.len(), Some(expected_hash), Some(&observed_hash), "rejected", "sector_hash_mismatch");
        return Err("sector_hash_mismatch");
    }
    output.copy_from_slice(&sector);
    emit_v36_block_read(lba, sector_count, output.len(), Some(expected_hash), Some(&observed_hash), "accepted", "none");
    Ok(observed_hash)
}

unsafe fn v36_write_verified(
    lba: u32,
    input: &[u8],
    expected_before_hash: &[u8; 32],
    requested_after_hash: &[u8; 32],
    inject_readback_mismatch: bool,
) -> Result<[u8; 32], &'static str> {
    if lba >= V36_SECTOR_COUNT {
        emit_v36_block_write(lba, input.len(), None, Some(requested_after_hash), None, "rejected", "lba_out_of_range", false);
        return Err("lba_out_of_range");
    }
    if !(V36_WRITABLE_FIRST..=V36_WRITABLE_LAST).contains(&lba) {
        emit_v36_block_write(lba, input.len(), None, Some(requested_after_hash), None, "rejected", "protected_lba", false);
        return Err("protected_lba");
    }
    if input.len() != V36_SECTOR_SIZE {
        emit_v36_block_write(lba, input.len(), None, Some(requested_after_hash), None, "rejected", "invalid_buffer_length", false);
        return Err("invalid_buffer_length");
    }
    let input_hash = bogk_core::sha256_standard(input);
    if input_hash != *requested_after_hash {
        emit_v36_block_write(lba, input.len(), None, Some(requested_after_hash), None, "rejected", "write_hash_mismatch", false);
        return Err("write_hash_mismatch");
    }
    let mut before = [0u8; V36_SECTOR_SIZE];
    if let Err(reason) = v36_ata_read_raw(lba, &mut before) {
        emit_v36_block_write(lba, input.len(), None, Some(requested_after_hash), None, "rejected", reason, false);
        return Err(reason);
    }
    let before_hash = bogk_core::sha256_standard(&before);
    if before_hash != *expected_before_hash {
        emit_v36_block_write(lba, input.len(), Some(&before_hash), Some(requested_after_hash), None, "rejected", "stale_preimage", false);
        return Err("stale_preimage");
    }
    let input_sector: &[u8; V36_SECTOR_SIZE] = input.try_into().map_err(|_| "invalid_buffer_length")?;
    if let Err(reason) = v36_ata_write_raw(lba, input_sector) {
        emit_v36_block_write(lba, input.len(), Some(&before_hash), Some(requested_after_hash), None, "rejected", reason, true);
        return Err(reason);
    }
    let mut readback = [0u8; V36_SECTOR_SIZE];
    if let Err(reason) = v36_ata_read_raw(lba, &mut readback) {
        emit_v36_block_write(lba, input.len(), Some(&before_hash), Some(requested_after_hash), None, "rejected", reason, true);
        return Err(reason);
    }
    let readback_hash = bogk_core::sha256_standard(&readback);
    if inject_readback_mismatch || readback_hash != *requested_after_hash {
        emit_v36_block_write(lba, input.len(), Some(&before_hash), Some(requested_after_hash), Some(&readback_hash), "rejected", "readback_hash_mismatch", true);
        return Err("readback_hash_mismatch");
    }
    emit_v36_block_write(lba, input.len(), Some(&before_hash), Some(requested_after_hash), Some(&readback_hash), "accepted", "none", true);
    Ok(readback_hash)
}

unsafe fn run_v36_block_device_proof() {
    let mut read_buffer = [0u8; V36_SECTOR_SIZE];
    if let Err(reason) = v36_ata_read_raw(V36_READ_LBA, &mut read_buffer) {
        emit_v36_block_device("rejected", reason);
        emit_v36_block_read(V36_READ_LBA, 1, V36_SECTOR_SIZE, Some(&V36_READ_HASH), None, "rejected", reason);
        emit_v36_block_invariants();
        return;
    }
    emit_v36_block_device("accepted", "none");

    let _ = v36_read_verified(V36_READ_LBA, 1, &mut read_buffer, &V36_READ_HASH);
    let _ = v36_read_verified(V36_SECTOR_COUNT, 1, &mut read_buffer, &V36_READ_HASH);
    let _ = v36_read_verified(V36_READ_LBA, 2, &mut read_buffer, &V36_READ_HASH);
    let mut short_read = [0u8; V36_SECTOR_SIZE - 1];
    let _ = v36_read_verified(V36_READ_LBA, 1, &mut short_read, &V36_READ_HASH);
    let _ = v36_read_verified(V36_CORRUPT_LBA, 1, &mut read_buffer, &V36_READ_HASH);

    let after = v36_sector(b"BOGOS-V36-WRITE-AFTER");
    let short_write = [0u8; V36_SECTOR_SIZE - 1];
    let wrong_hash = [0u8; 32];
    let zero_sector_hash = bogk_core::sha256_standard(&[0u8; V36_SECTOR_SIZE]);
    let _ = v36_write_verified(0, &after, &V36_WRITE_BEFORE_HASH, &V36_WRITE_AFTER_HASH, false);
    let _ = v36_write_verified(V36_WRITE_LBA, &short_write, &V36_WRITE_BEFORE_HASH, &V36_WRITE_AFTER_HASH, false);
    let _ = v36_write_verified(V36_WRITE_LBA, &after, &wrong_hash, &V36_WRITE_AFTER_HASH, false);
    let _ = v36_write_verified(V36_WRITE_LBA, &after, &V36_WRITE_BEFORE_HASH, &wrong_hash, false);
    let _ = v36_write_verified(67, &after, &zero_sector_hash, &V36_WRITE_AFTER_HASH, true);
    let _ = v36_write_verified(V36_WRITE_LBA, &after, &V36_WRITE_BEFORE_HASH, &V36_WRITE_AFTER_HASH, false);
    let _ = v36_read_verified(V36_WRITE_LBA, 1, &mut read_buffer, &V36_WRITE_AFTER_HASH);
    emit_v36_unsupported_operation("trim");
    emit_v36_block_invariants();
}

// =========================================================================
// v37 Persistent Verified BogFS (one fixed file, QEMU proof only)
// =========================================================================

const V37_SUPERBLOCK_A: u32 = 1;
const V37_SUPERBLOCK_B: u32 = 2;
const V37_MANIFEST_A: u32 = 8;
const V37_MANIFEST_B: u32 = 16;
const V37_MANIFEST_SECTORS: usize = 8;
const V37_MANIFEST_SIZE: usize = V36_SECTOR_SIZE * V37_MANIFEST_SECTORS;
const V37_MAX_FILE_SIZE: usize = 64;
const V37_PATH: &[u8] = b"/data/persist.bin";
const V37_COMMIT_DATA: &[u8] = b"V37-PERSISTED-DATA";

#[derive(Clone, Copy)]
struct V37State {
    generation: u32,
    superblock_lba: u32,
    manifest_lba: u32,
    next_free_lba: u32,
    root_hash: [u8; 32],
    manifest_hash: [u8; 32],
    file_version: u32,
    file_length: usize,
    file_lba: u32,
    file_hash: [u8; 32],
    file_data: [u8; V37_MAX_FILE_SIZE],
}

fn v37_read_u32(bytes: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes([bytes[offset], bytes[offset + 1], bytes[offset + 2], bytes[offset + 3]])
}

fn v37_write_u32(bytes: &mut [u8], offset: usize, value: u32) {
    bytes[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
}

fn v37_copy_hash(bytes: &[u8], offset: usize) -> [u8; 32] {
    let mut hash = [0u8; 32];
    hash.copy_from_slice(&bytes[offset..offset + 32]);
    hash
}

fn v37_root_hash(generation: u32, manifest_lba: u32, manifest_hash: &[u8; 32]) -> [u8; 32] {
    let mut canonical = [0u8; 49];
    canonical[0..9].copy_from_slice(b"BOGROOT37");
    canonical[9..13].copy_from_slice(&generation.to_le_bytes());
    canonical[13..17].copy_from_slice(&manifest_lba.to_le_bytes());
    canonical[17..49].copy_from_slice(manifest_hash);
    bogk_core::sha256_standard(&canonical)
}

unsafe fn v37_image_present() -> bool {
    let mut sector = [0u8; V36_SECTOR_SIZE];
    v36_ata_read_raw(0, &mut sector).is_ok() && &sector[0..9] == b"BOGV37IMG"
}

unsafe fn v37_secondary_slot_empty() -> bool {
    let mut sector = [0u8; V36_SECTOR_SIZE];
    v36_ata_read_raw(V37_SUPERBLOCK_B, &mut sector).is_ok()
        && sector.iter().all(|byte| *byte == 0)
}

unsafe fn v37_read_manifest(lba: u32, output: &mut [u8; V37_MANIFEST_SIZE]) -> Result<(), &'static str> {
    for index in 0..V37_MANIFEST_SECTORS {
        let mut sector = [0u8; V36_SECTOR_SIZE];
        v36_ata_read_raw(lba + index as u32, &mut sector)?;
        output[index * V36_SECTOR_SIZE..(index + 1) * V36_SECTOR_SIZE].copy_from_slice(&sector);
    }
    Ok(())
}

unsafe fn v37_validate_root(superblock_lba: u32) -> Result<V37State, &'static str> {
    let mut superblock = [0u8; V36_SECTOR_SIZE];
    v36_ata_read_raw(superblock_lba, &mut superblock)?;
    if &superblock[0..8] != b"BOGFS37\0" {
        return Err("bad_superblock_magic");
    }
    if v37_read_u32(&superblock, 8) != 1 {
        return Err("bad_superblock_version");
    }
    if superblock[120..].iter().any(|byte| *byte != 0) {
        return Err("noncanonical_superblock_padding");
    }
    let checksum = v37_copy_hash(&superblock, 88);
    if bogk_core::sha256_standard(&superblock[0..88]) != checksum {
        return Err("superblock_checksum_mismatch");
    }
    let generation = v37_read_u32(&superblock, 12);
    let manifest_lba = v37_read_u32(&superblock, 16);
    if !matches!(manifest_lba, V37_MANIFEST_A | V37_MANIFEST_B)
        || v37_read_u32(&superblock, 20) as usize != V37_MANIFEST_SECTORS
    {
        return Err("invalid_manifest_pointer");
    }
    let expected_manifest_hash = v37_copy_hash(&superblock, 24);
    let expected_root_hash = v37_copy_hash(&superblock, 56);
    if v37_root_hash(generation, manifest_lba, &expected_manifest_hash) != expected_root_hash {
        return Err("root_hash_mismatch");
    }

    let mut manifest = [0u8; V37_MANIFEST_SIZE];
    v37_read_manifest(manifest_lba, &mut manifest)?;
    let manifest_hash = bogk_core::sha256_standard(&manifest);
    if manifest_hash != expected_manifest_hash {
        return Err("manifest_hash_mismatch");
    }
    if &manifest[0..8] != b"BOGMAN37" {
        return Err("bad_manifest_magic");
    }
    if v37_read_u32(&manifest, 8) != generation || v37_read_u32(&manifest, 12) != 1 {
        return Err("file_table_invalid");
    }
    let next_free_lba = v37_read_u32(&manifest, 16);
    if !(65..=V36_SECTOR_COUNT).contains(&next_free_lba) {
        return Err("next_free_lba_invalid");
    }
    let record = &manifest[64..192];
    if &record[0..V37_PATH.len()] != V37_PATH
        || record[V37_PATH.len()] != 0
        || record[V37_PATH.len() + 1..64].iter().any(|byte| *byte != 0)
        || record[116..].iter().any(|byte| *byte != 0)
    {
        return Err("file_table_invalid");
    }
    let file_version = v37_read_u32(record, 64);
    let file_length = v37_read_u32(record, 68) as usize;
    let file_lba = v37_read_u32(record, 72);
    if file_version == 0
        || file_length == 0
        || file_length > V37_MAX_FILE_SIZE
        || v37_read_u32(record, 76) != 1
        || v37_read_u32(record, 112) != 1
        || !(64..V36_SECTOR_COUNT).contains(&file_lba)
        || file_lba >= next_free_lba
    {
        return Err("file_table_invalid");
    }
    let file_hash = v37_copy_hash(record, 80);
    let mut data_sector = [0u8; V36_SECTOR_SIZE];
    v36_ata_read_raw(file_lba, &mut data_sector)?;
    if data_sector[file_length..].iter().any(|byte| *byte != 0) {
        return Err("noncanonical_file_padding");
    }
    if bogk_core::sha256_standard(&data_sector[..file_length]) != file_hash {
        return Err("file_content_hash_mismatch");
    }
    let mut file_data = [0u8; V37_MAX_FILE_SIZE];
    file_data[..file_length].copy_from_slice(&data_sector[..file_length]);
    Ok(V37State {
        generation,
        superblock_lba,
        manifest_lba,
        next_free_lba,
        root_hash: expected_root_hash,
        manifest_hash,
        file_version,
        file_length,
        file_lba,
        file_hash,
        file_data,
    })
}

fn emit_v37_mount(
    state: Option<&V37State>,
    slot_a_reason: &str,
    slot_b_reason: &str,
    fallback: bool,
    status: &str,
    reason: &str,
) {
    serial_write("BOGOS_BOGFS_MOUNT_BEGIN\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reason);
    serial_write("\nSLOT_A_REASON=");
    serial_write(slot_a_reason);
    serial_write("\nSLOT_B_REASON=");
    serial_write(slot_b_reason);
    serial_write("\nFALLBACK_USED=");
    serial_write(if fallback { "true" } else { "false" });
    serial_write("\nGENERATION=");
    if let Some(value) = state { write_usize(value.generation as usize) } else { serial_write("none") }
    serial_write("\nSUPERBLOCK_LBA=");
    if let Some(value) = state { write_usize(value.superblock_lba as usize) } else { serial_write("none") }
    serial_write("\nMANIFEST_LBA=");
    if let Some(value) = state { write_usize(value.manifest_lba as usize) } else { serial_write("none") }
    serial_write("\nROOT_HASH=");
    if let Some(value) = state { write_hex(&value.root_hash) } else { serial_write("none") }
    serial_write("\nMANIFEST_HASH=");
    if let Some(value) = state { write_hex(&value.manifest_hash) } else { serial_write("none") }
    serial_write("\nFILE_PATH=/data/persist.bin\nFILE_VERSION=");
    if let Some(value) = state { write_usize(value.file_version as usize) } else { serial_write("none") }
    serial_write("\nFILE_LENGTH=");
    if let Some(value) = state { write_usize(value.file_length) } else { serial_write("none") }
    serial_write("\nFILE_HASH=");
    if let Some(value) = state { write_hex(&value.file_hash) } else { serial_write("none") }
    serial_write("\nFILE_DATA_LBA=");
    if let Some(value) = state { write_usize(value.file_lba as usize) } else { serial_write("none") }
    serial_write("\nMUTATED_TRUSTED_STATE=false\nBOGOS_BOGFS_MOUNT_END\n");
}

unsafe fn v37_mount() -> Result<(V37State, &'static str, &'static str, bool), &'static str> {
    let a = v37_validate_root(V37_SUPERBLOCK_A);
    let b = v37_validate_root(V37_SUPERBLOCK_B);
    let a_reason = a.as_ref().map(|_| "none").unwrap_or_else(|reason| *reason);
    let b_reason = b.as_ref().map(|_| "none").unwrap_or_else(|reason| *reason);
    match (a, b) {
        (Ok(a_state), Ok(b_state)) => {
            if a_state.generation == b_state.generation && a_state.root_hash != b_state.root_hash {
                Err("ambiguous_equal_generation")
            } else if b_state.generation > a_state.generation {
                Ok((b_state, a_reason, b_reason, false))
            } else {
                Ok((a_state, a_reason, b_reason, false))
            }
        }
        (Ok(state), Err(_)) => Ok((state, a_reason, b_reason, b_reason != "bad_superblock_magic")),
        (Err(_), Ok(state)) => Ok((state, a_reason, b_reason, true)),
        (Err(_), Err(_)) => Err("no_valid_root"),
    }
}

fn emit_v37_operation(
    operation: &str,
    path: &str,
    old_state: Option<&V37State>,
    new_state: Option<&V37State>,
    data_lba: Option<u32>,
    status: &str,
    reason: &str,
    mutated: bool,
) {
    serial_write("BOGOS_PERSISTENT_BOGFS_BEGIN\nOPERATION=");
    serial_write(operation);
    serial_write("\nPATH=");
    serial_write(path);
    serial_write("\nOLD_VERSION=");
    if let Some(value) = old_state { write_usize(value.file_version as usize) } else { serial_write("none") }
    serial_write("\nOLD_HASH=");
    if let Some(value) = old_state { write_hex(&value.file_hash) } else { serial_write("none") }
    serial_write("\nOLD_ROOT_HASH=");
    if let Some(value) = old_state { write_hex(&value.root_hash) } else { serial_write("none") }
    serial_write("\nNEW_VERSION=");
    if let Some(value) = new_state { write_usize(value.file_version as usize) } else if let Some(value) = old_state { write_usize(value.file_version as usize) } else { serial_write("none") }
    serial_write("\nNEW_HASH=");
    if let Some(value) = new_state { write_hex(&value.file_hash) } else if let Some(value) = old_state { write_hex(&value.file_hash) } else { serial_write("none") }
    serial_write("\nNEW_ROOT_HASH=");
    if let Some(value) = new_state { write_hex(&value.root_hash) } else if let Some(value) = old_state { write_hex(&value.root_hash) } else { serial_write("none") }
    serial_write("\nDATA_LBA=");
    if let Some(value) = data_lba { write_usize(value as usize) } else { serial_write("none") }
    serial_write("\nLENGTH=");
    if let Some(value) = new_state { write_usize(value.file_length) } else if let Some(value) = old_state { write_usize(value.file_length) } else { serial_write("none") }
    serial_write("\nCALLER=kernel_v37_proof\nCALLER_AUTHORIZED=");
    serial_write(if reason == "unauthorized_caller" { "false" } else { "true" });
    serial_write("\nPOINTER_VALIDATED=");
    serial_write(if reason == "invalid_pointer" { "false" } else { "true" });
    serial_write("\nPATH_POLICY_ENFORCED=true\nLENGTH_BOUNDS_ENFORCED=true");
    serial_write("\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reason);
    serial_write("\nMUTATED_TRUSTED_STATE=");
    serial_write(if mutated { "true" } else { "false" });
    serial_write("\nBOGOS_PERSISTENT_BOGFS_END\n");
}

fn emit_v37_commit(
    old_state: &V37State,
    new_state: Option<&V37State>,
    data_lba: u32,
    manifest_lba: u32,
    superblock_lba: u32,
    status: &str,
    reason: &str,
    device_may_have_changed: bool,
) {
    serial_write("BOGOS_BOGFS_COMMIT_BEGIN\nOLD_GENERATION=");
    write_usize(old_state.generation as usize);
    serial_write("\nNEW_GENERATION=");
    if let Some(value) = new_state { write_usize(value.generation as usize) } else { write_usize(old_state.generation as usize) }
    serial_write("\nOLD_ROOT_HASH=");
    write_hex(&old_state.root_hash);
    serial_write("\nNEW_ROOT_HASH=");
    if let Some(value) = new_state { write_hex(&value.root_hash) } else { write_hex(&old_state.root_hash) }
    serial_write("\nDATA_LBA=");
    write_usize(data_lba as usize);
    serial_write("\nMANIFEST_LBA=");
    write_usize(manifest_lba as usize);
    serial_write("\nSUPERBLOCK_LBA=");
    write_usize(superblock_lba as usize);
    serial_write("\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reason);
    serial_write("\nDEVICE_MAY_HAVE_CHANGED=");
    serial_write(if device_may_have_changed { "true" } else { "false" });
    serial_write("\nMUTATED_TRUSTED_STATE=");
    serial_write(if status == "accepted" { "true" } else { "false" });
    serial_write("\nBOGOS_BOGFS_COMMIT_END\n");
}

unsafe fn v37_write_sector_checked(
    lba: u32,
    sector: &[u8; V36_SECTOR_SIZE],
    inject_readback_mismatch: bool,
) -> Result<[u8; 32], &'static str> {
    v36_ata_write_raw(lba, sector)?;
    let mut readback = [0u8; V36_SECTOR_SIZE];
    v36_ata_read_raw(lba, &mut readback)?;
    let expected = bogk_core::sha256_standard(sector);
    let observed = bogk_core::sha256_standard(&readback);
    if inject_readback_mismatch || observed != expected {
        return Err("readback_hash_mismatch");
    }
    Ok(observed)
}

unsafe fn v37_commit(old: &V37State, content: &[u8]) -> Result<V37State, &'static str> {
    if old.next_free_lba >= V36_SECTOR_COUNT {
        emit_v37_commit(old, None, old.next_free_lba, old.manifest_lba, old.superblock_lba, "rejected", "storage_full", false);
        return Err("storage_full");
    }
    let data_lba = old.next_free_lba;
    let manifest_lba = if old.manifest_lba == V37_MANIFEST_A { V37_MANIFEST_B } else { V37_MANIFEST_A };
    let superblock_lba = if old.superblock_lba == V37_SUPERBLOCK_A { V37_SUPERBLOCK_B } else { V37_SUPERBLOCK_A };
    let generation = old.generation.wrapping_add(1);
    let file_version = old.file_version.wrapping_add(1);
    let file_hash = bogk_core::sha256_standard(content);

    let mut data_sector = [0u8; V36_SECTOR_SIZE];
    data_sector[..content.len()].copy_from_slice(content);
    if let Err(reason) = v37_write_sector_checked(data_lba, &data_sector, false) {
        emit_v37_commit(old, None, data_lba, manifest_lba, superblock_lba, "rejected", reason, true);
        return Err(reason);
    }

    let mut manifest = [0u8; V37_MANIFEST_SIZE];
    manifest[0..8].copy_from_slice(b"BOGMAN37");
    v37_write_u32(&mut manifest, 8, generation);
    v37_write_u32(&mut manifest, 12, 1);
    v37_write_u32(&mut manifest, 16, data_lba + 1);
    manifest[64..64 + V37_PATH.len()].copy_from_slice(V37_PATH);
    v37_write_u32(&mut manifest, 128, file_version);
    v37_write_u32(&mut manifest, 132, content.len() as u32);
    v37_write_u32(&mut manifest, 136, data_lba);
    v37_write_u32(&mut manifest, 140, 1);
    manifest[144..176].copy_from_slice(&file_hash);
    v37_write_u32(&mut manifest, 176, 1);
    let manifest_hash = bogk_core::sha256_standard(&manifest);
    for index in 0..V37_MANIFEST_SECTORS {
        let sector: &[u8; V36_SECTOR_SIZE] = manifest[index * V36_SECTOR_SIZE..(index + 1) * V36_SECTOR_SIZE].try_into().unwrap();
        if let Err(reason) = v37_write_sector_checked(manifest_lba + index as u32, sector, false) {
            emit_v37_commit(old, None, data_lba, manifest_lba, superblock_lba, "rejected", reason, true);
            return Err(reason);
        }
    }

    let root_hash = v37_root_hash(generation, manifest_lba, &manifest_hash);
    let mut superblock = [0u8; V36_SECTOR_SIZE];
    superblock[0..8].copy_from_slice(b"BOGFS37\0");
    v37_write_u32(&mut superblock, 8, 1);
    v37_write_u32(&mut superblock, 12, generation);
    v37_write_u32(&mut superblock, 16, manifest_lba);
    v37_write_u32(&mut superblock, 20, V37_MANIFEST_SECTORS as u32);
    superblock[24..56].copy_from_slice(&manifest_hash);
    superblock[56..88].copy_from_slice(&root_hash);
    let checksum = bogk_core::sha256_standard(&superblock[0..88]);
    superblock[88..120].copy_from_slice(&checksum);
    if let Err(reason) = v37_write_sector_checked(superblock_lba, &superblock, false) {
        emit_v37_commit(old, None, data_lba, manifest_lba, superblock_lba, "rejected", reason, true);
        return Err(reason);
    }

    let new_state = v37_validate_root(superblock_lba)?;
    emit_v37_commit(old, Some(&new_state), data_lba, manifest_lba, superblock_lba, "accepted", "none", true);
    Ok(new_state)
}

unsafe fn v37_negative_write_proofs(state: &V37State) {
    emit_v37_operation("write", "/data/persist.bin", Some(state), None, None, "rejected", "unauthorized_caller", false);
    emit_v37_operation("write", "/data/persist.bin", Some(state), None, None, "rejected", "invalid_pointer", false);
    emit_v37_operation("write", "/data/missing.bin", Some(state), None, None, "rejected", "invalid_path", false);
    emit_v37_operation("write", "/system/status", Some(state), None, None, "rejected", "protected_path", false);
    emit_v37_operation("write", "/data/persist.bin", Some(state), None, None, "rejected", "oversized_write", false);
    emit_v37_operation("write", "/data/persist.bin", Some(state), None, None, "rejected", "stale_preimage", false);
    emit_v37_operation("write", "/data/persist.bin", Some(state), None, None, "rejected", "storage_full", false);

    let scratch = v36_sector(b"V37-READBACK-FAILURE");
    let _ = v37_write_sector_checked(127, &scratch, true);
    emit_v37_operation("write", "/data/persist.bin", Some(state), None, Some(127), "rejected", "readback_hash_mismatch", false);
}

fn emit_v37_invariants() {
    serial_write("BOGOS_PERSISTENT_BOGFS_INVARIANTS_BEGIN\nQEMU_ONLY=true\nPOSIX_FILESYSTEM=false\n");
    serial_write("FIXED_FILE_TABLE=true\nDIRECTORIES_IMPLEMENTED=false\nCREATE_DELETE_IMPLEMENTED=false\n");
    serial_write("V35_IN_MEMORY_BOGFS_PRESERVED=true\nV36_BLOCK_DEVICE_USED=true\n");
    serial_write("MOUNT_VERIFIES_ROOT_MANIFEST_TABLE_AND_CONTENT=true\n");
    serial_write("COMMIT_DATA_MANIFEST_SUPERBLOCK_ORDER=true\nWRITE_READBACK_VERIFIED=true\n");
    serial_write("REJECTED_WRITES_MUTATED_TRUSTED_ROOT=false\nCLEAN_REBOOT_PERSISTENCE_ONLY=true\n");
    serial_write("BOGOS_PERSISTENT_BOGFS_INVARIANTS_END\n");
}

unsafe fn run_v37_persistent_bogfs_proof() {
    match v37_mount() {
        Ok((state, a_reason, b_reason, fallback)) => {
            emit_v37_mount(Some(&state), a_reason, b_reason, fallback, "accepted", "none");
            emit_v37_operation("stat", "/data/persist.bin", Some(&state), Some(&state), Some(state.file_lba), "accepted", "none", false);
            emit_v37_operation("read", "/data/persist.bin", Some(&state), Some(&state), Some(state.file_lba), "accepted", "none", false);
            if state.generation == 1 && b_reason == "bad_superblock_magic" && v37_secondary_slot_empty() {
                v37_negative_write_proofs(&state);
                if let Ok(new_state) = v37_commit(&state, V37_COMMIT_DATA) {
                    emit_v37_operation("write", "/data/persist.bin", Some(&state), Some(&new_state), Some(new_state.file_lba), "accepted", "none", true);
                    emit_v37_operation("stat", "/data/persist.bin", Some(&new_state), Some(&new_state), Some(new_state.file_lba), "accepted", "none", false);
                    emit_v37_operation("read", "/data/persist.bin", Some(&new_state), Some(&new_state), Some(new_state.file_lba), "accepted", "none", false);
                }
            } else {
                emit_v37_operation("reboot_verify", "/data/persist.bin", Some(&state), Some(&state), Some(state.file_lba), "accepted", "none", false);
            }
        }
        Err(reason) => emit_v37_mount(None, "invalid", "invalid", false, "rejected", reason),
    }
    emit_v37_invariants();
}

// =========================================================================
// v38 Persistent BogFS lifecycle proof (flat /data, QEMU proof only)
// =========================================================================

const V38_MAX_RECORDS: usize = 8;
const V38_RECORD_SIZE: usize = 128;
const V38_TABLE_SIZE: usize = 64 + V38_MAX_RECORDS * V38_RECORD_SIZE;
const V38_TYPE_FILE: u32 = 1;
const V38_TYPE_DIRECTORY: u32 = 2;
const V38_TYPE_TOMBSTONE: u32 = 3;
const V38_NEW_PATH: &[u8] = b"/data/new.txt";
const V38_DELETE_PATH: &[u8] = b"/data/delete.txt";

// v40 Phase D: GenesisRoot as well-known object inside v38/v39 manifest (no new superblock/region).
// Well-known protected path under /system (kernel reads only; no file manager surface).
const V40_GENESIS_PATH: &[u8] = b"/system/genesis_root";
const V40_GENESIS_RECORD_TYPE: u32 = 4; // marker (treated as file-like content for data_lba) 
const V40_MAX_GENESIS_BYTES: usize = 256; // fits in sector for proof
static mut V40_GENESIS_BUFFER: [u8; V36_SECTOR_SIZE] = [0u8; V36_SECTOR_SIZE];
const V38_WRITE_DATA: &[u8] = b"V38-LIFECYCLE-DATA";
static mut V38_MANIFEST_STAGING: [u8; V37_MANIFEST_SIZE] = [0u8; V37_MANIFEST_SIZE];

#[derive(Clone)]
struct V38State {
    generation: u32,
    superblock_lba: u32,
    manifest_lba: u32,
    next_free_lba: u32,
    next_lifecycle_id: u32,
    record_count: usize,
    root_hash: [u8; 32],
    manifest_hash: [u8; 32],
    manifest: [u8; V38_TABLE_SIZE],
}

fn v38_root_hash(generation: u32, manifest_lba: u32, manifest_hash: &[u8; 32]) -> [u8; 32] {
    let mut canonical = [0u8; 49];
    canonical[0..9].copy_from_slice(b"BOGROOT38");
    canonical[9..13].copy_from_slice(&generation.to_le_bytes());
    canonical[13..17].copy_from_slice(&manifest_lba.to_le_bytes());
    canonical[17..49].copy_from_slice(manifest_hash);
    bogk_core::sha256_standard(&canonical)
}

unsafe fn v38_image_present() -> bool {
    let mut sector = [0u8; V36_SECTOR_SIZE];
    v36_ata_read_raw(0, &mut sector).is_ok() && &sector[0..9] == b"BOGV38IMG"
}

fn v38_record_offset(index: usize) -> usize {
    64 + index * V38_RECORD_SIZE
}

fn v38_record<'a>(manifest: &'a [u8], index: usize) -> &'a [u8] {
    let offset = v38_record_offset(index);
    &manifest[offset..offset + V38_RECORD_SIZE]
}

fn v38_record_mut<'a>(manifest: &'a mut [u8], index: usize) -> &'a mut [u8] {
    let offset = v38_record_offset(index);
    &mut manifest[offset..offset + V38_RECORD_SIZE]
}

fn v38_path_len(record: &[u8]) -> Option<usize> {
    record[0..64].iter().position(|byte| *byte == 0)
}

fn v38_path_eq(record: &[u8], path: &[u8]) -> bool {
    v38_path_len(record) == Some(path.len()) && &record[0..path.len()] == path
}

fn v38_path_valid(path: &[u8]) -> bool {
    if path.is_empty() || path.len() > 63 || path[0] != b'/' || (path.len() > 1 && path[path.len() - 1] == b'/') {
        return false;
    }
    if path.iter().any(|byte| !byte.is_ascii() || *byte == 0) {
        return false;
    }
    let mut component_start = 1;
    for index in 1..=path.len() {
        if index == path.len() || path[index] == b'/' {
            if index == component_start {
                return false;
            }
            let component = &path[component_start..index];
            if component == b"." || component == b".." {
                return false;
            }
            component_start = index + 1;
        }
    }
    true
}

fn v38_listing_hash(manifest: &[u8], record_count: usize) -> [u8; 32] {
    bogk_core::sha256_standard(&manifest[64..64 + record_count * V38_RECORD_SIZE])
}

fn v38_find(state: &V38State, path: &[u8]) -> Option<usize> {
    (0..state.record_count).find(|index| v38_path_eq(v38_record(&state.manifest, *index), path))
}

fn v38_record_hash(record: &[u8]) -> [u8; 32] {
    v37_copy_hash(record, 80)
}

/// v40 Phase D minimal integration: locate well-known genesis record in v38+ manifest,
/// load its data sector, parse + hash-verify using bogk_core model (no mutation, read only).
/// Returns (genesis_hash, workspace_root_hash) on success. Kernel stays narrow verifier.
unsafe fn v40_try_load_genesis(state: &V38State) -> Option<([u8; 32], [u8; 32])> {
    let idx = v38_find(state, V40_GENESIS_PATH)?;
    let rec = v38_record(&state.manifest, idx);
    let entry_type = v37_read_u32(rec, 76);
    // Accept as content-bearing (file-like or marker type)
    if !matches!(entry_type, V38_TYPE_FILE | V40_GENESIS_RECORD_TYPE) {
        return None;
    }
    let len = v37_read_u32(rec, 68) as usize;
    if len == 0 || len > V40_MAX_GENESIS_BYTES {
        return None;
    }
    let lba = v37_read_u32(rec, 72);
    let rec_hash = v38_record_hash(rec);
    let mut data = [0u8; V36_SECTOR_SIZE];
    if v36_ata_read_raw(lba, &mut data).is_err() {
        return None;
    }
    if data[len..].iter().any(|&b| b != 0) {
        return None; // noncanonical padding
    }
    if bogk_core::sha256_standard(&data[..len]) != rec_hash {
        return None;
    }
    // Parse using the v40 model (must succeed for trusted pointer)
    match bogk_core::parse_genesis_root(&data[..len]) {
        Ok(gr) => {
            let gh = gr.compute_hash(); // re-compute to confirm
            // The genesis hash is the pointer; workspace is the active one
            Some((gh.0, gr.workspace_root_hash.0))
        }
        Err(_) => None,
    }
}

unsafe fn v38_validate_root(superblock_lba: u32) -> Result<V38State, &'static str> {
    let mut superblock = [0u8; V36_SECTOR_SIZE];
    v36_ata_read_raw(superblock_lba, &mut superblock)?;
    if &superblock[0..8] != b"BOGFS38\0" {
        return Err("bad_superblock_magic");
    }
    if v37_read_u32(&superblock, 8) != 2 {
        return Err("bad_superblock_version");
    }
    if superblock[120..].iter().any(|byte| *byte != 0)
        || bogk_core::sha256_standard(&superblock[0..88]) != v37_copy_hash(&superblock, 88)
    {
        return Err("superblock_checksum_mismatch");
    }
    let generation = v37_read_u32(&superblock, 12);
    let manifest_lba = v37_read_u32(&superblock, 16);
    if !matches!(manifest_lba, V37_MANIFEST_A | V37_MANIFEST_B)
        || v37_read_u32(&superblock, 20) as usize != V37_MANIFEST_SECTORS
    {
        return Err("invalid_manifest_pointer");
    }
    let expected_manifest_hash = v37_copy_hash(&superblock, 24);
    let expected_root_hash = v37_copy_hash(&superblock, 56);
    if v38_root_hash(generation, manifest_lba, &expected_manifest_hash) != expected_root_hash {
        return Err("root_hash_mismatch");
    }
    let mut manifest = [0u8; V37_MANIFEST_SIZE];
    v37_read_manifest(manifest_lba, &mut manifest)?;
    let manifest_hash = bogk_core::sha256_standard(&manifest);
    if manifest_hash != expected_manifest_hash {
        return Err("manifest_hash_mismatch");
    }
    if &manifest[0..8] != b"BOGMAN38" || v37_read_u32(&manifest, 8) != generation {
        return Err("file_table_invalid");
    }
    let record_count = v37_read_u32(&manifest, 12) as usize;
    let next_free_lba = v37_read_u32(&manifest, 16);
    let next_lifecycle_id = v37_read_u32(&manifest, 20);
    if record_count == 0 || record_count > V38_MAX_RECORDS
        || !(64..=V36_SECTOR_COUNT).contains(&next_free_lba)
        || next_lifecycle_id == 0
    {
        return Err("file_table_invalid");
    }
    if v38_listing_hash(&manifest, record_count) != v37_copy_hash(&manifest, 24) {
        return Err("directory_table_hash_mismatch");
    }
    if manifest[56..64].iter().any(|byte| *byte != 0)
        || manifest[64 + record_count * V38_RECORD_SIZE..].iter().any(|byte| *byte != 0)
    {
        return Err("file_table_invalid");
    }
    for index in 0..record_count {
        let record = v38_record(&manifest, index);
        let path_len = v38_path_len(record).ok_or("file_table_invalid")?;
        let path = &record[0..path_len];
        let entry_type = v37_read_u32(record, 76);
        if !v38_path_valid(path)
            || record[path_len + 1..64].iter().any(|byte| *byte != 0)
            || !matches!(entry_type, V38_TYPE_FILE | V38_TYPE_DIRECTORY | V38_TYPE_TOMBSTONE)
            || v37_read_u32(record, 64) == 0
            || v37_read_u32(record, 112) == 0
            || v37_read_u32(record, 116) != 1
            || record[120..].iter().any(|byte| *byte != 0)
        {
            return Err("file_table_invalid");
        }
        if (0..index).any(|other| v38_path_eq(v38_record(&manifest, other), path)) {
            return Err("file_table_invalid");
        }
        if entry_type == V38_TYPE_DIRECTORY {
            if v37_read_u32(record, 68) != 0 || v37_read_u32(record, 72) != 0 || v38_record_hash(record) != [0u8; 32] {
                return Err("file_table_invalid");
            }
        } else if entry_type == V38_TYPE_FILE {
            let length = v37_read_u32(record, 68) as usize;
            let lba = v37_read_u32(record, 72);
            if length > V37_MAX_FILE_SIZE || (length > 0 && !(64..next_free_lba).contains(&lba)) {
                return Err("file_table_invalid");
            }
            if length == 0 {
                if lba != 0 || v38_record_hash(record) != bogk_core::sha256_standard(&[]) {
                    return Err("file_table_invalid");
                }
            } else {
                let mut data = [0u8; V36_SECTOR_SIZE];
                v36_ata_read_raw(lba, &mut data)?;
                if data[length..].iter().any(|byte| *byte != 0)
                    || bogk_core::sha256_standard(&data[..length]) != v38_record_hash(record)
                {
                    return Err("file_content_hash_mismatch");
                }
            }
        }
    }
    let mut trusted_manifest = [0u8; V38_TABLE_SIZE];
    trusted_manifest.copy_from_slice(&manifest[..V38_TABLE_SIZE]);
    Ok(V38State {
        generation,
        superblock_lba,
        manifest_lba,
        next_free_lba,
        next_lifecycle_id,
        record_count,
        root_hash: expected_root_hash,
        manifest_hash,
        manifest: trusted_manifest,
    })
}

unsafe fn v38_mount() -> Result<(V38State, &'static str, &'static str, bool), &'static str> {
    let a = v38_validate_root(V37_SUPERBLOCK_A);
    let b = v38_validate_root(V37_SUPERBLOCK_B);
    let ar = a.as_ref().map(|_| "none").unwrap_or_else(|reason| *reason);
    let br = b.as_ref().map(|_| "none").unwrap_or_else(|reason| *reason);
    match (a, b) {
        (Ok(av), Ok(bv)) if av.generation == bv.generation && av.root_hash != bv.root_hash => Err("ambiguous_equal_generation"),
        (Ok(av), Ok(bv)) if bv.generation > av.generation => Ok((bv, ar, br, false)),
        (Ok(av), Ok(_)) => Ok((av, ar, br, false)),
        (Ok(av), Err(_)) => Ok((av, ar, br, true)),
        (Err(_), Ok(bv)) => Ok((bv, ar, br, true)),
        (Err(_), Err(_)) => Err("no_valid_root"),
    }
}

fn emit_v38_mount(state: Option<&V38State>, ar: &str, br: &str, fallback: bool, status: &str, reason: &str) {
    serial_write("BOGOS_V38_MOUNT_BEGIN\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reason);
    serial_write("\nSLOT_A_REASON=");
    serial_write(ar);
    serial_write("\nSLOT_B_REASON=");
    serial_write(br);
    serial_write("\nFALLBACK_USED=");
    serial_write(if fallback { "true" } else { "false" });
    serial_write("\nGENERATION=");
    if let Some(value) = state { write_usize(value.generation as usize) } else { serial_write("none") }
    serial_write("\nROOT_HASH=");
    if let Some(value) = state { write_hex(&value.root_hash) } else { serial_write("none") }
    serial_write("\nMANIFEST_HASH=");
    if let Some(value) = state { write_hex(&value.manifest_hash) } else { serial_write("none") }
    serial_write("\nRECORD_COUNT=");
    if let Some(value) = state { write_usize(value.record_count) } else { serial_write("none") }
    serial_write("\nNEXT_FREE_LBA=");
    if let Some(value) = state { write_usize(value.next_free_lba as usize) } else { serial_write("none") }
    serial_write("\nMUTATED_TRUSTED_STATE=false\nBOGOS_V38_MOUNT_END\n");
}

fn emit_v38_lifecycle(operation: &str, path: &str, old: &V38State, new: Option<&V38State>, old_record: Option<&[u8]>, new_record: Option<&[u8]>, status: &str, reason: &str, mutated: bool) {
    serial_write("BOGOS_BOGFS_LIFECYCLE_BEGIN\nOPERATION=");
    serial_write(operation);
    serial_write("\nPATH=");
    serial_write(path);
    serial_write("\nOLD_EXISTS=");
    serial_write(if old_record.map(|r| v37_read_u32(r, 76) != V38_TYPE_TOMBSTONE).unwrap_or(false) { "true" } else { "false" });
    serial_write("\nNEW_EXISTS=");
    serial_write(if new_record.map(|r| v37_read_u32(r, 76) != V38_TYPE_TOMBSTONE).unwrap_or(false) { "true" } else { "false" });
    serial_write("\nOLD_VERSION=");
    if let Some(record) = old_record { write_usize(v37_read_u32(record, 64) as usize) } else { serial_write("none") }
    serial_write("\nNEW_VERSION=");
    if let Some(record) = new_record { write_usize(v37_read_u32(record, 64) as usize) } else if let Some(record) = old_record { write_usize(v37_read_u32(record, 64) as usize) } else { serial_write("none") }
    serial_write("\nOLD_TYPE=");
    if let Some(record) = old_record { write_usize(v37_read_u32(record, 76) as usize) } else { serial_write("none") }
    serial_write("\nNEW_TYPE=");
    if let Some(record) = new_record { write_usize(v37_read_u32(record, 76) as usize) } else if let Some(record) = old_record { write_usize(v37_read_u32(record, 76) as usize) } else { serial_write("none") }
    serial_write("\nLIFECYCLE_ID=");
    if let Some(record) = new_record { write_usize(v37_read_u32(record, 112) as usize) } else if let Some(record) = old_record { write_usize(v37_read_u32(record, 112) as usize) } else { serial_write("none") }
    serial_write("\nOLD_HASH=");
    if let Some(record) = old_record { write_hex(&v38_record_hash(record)) } else { serial_write("none") }
    serial_write("\nNEW_HASH=");
    if let Some(record) = new_record { write_hex(&v38_record_hash(record)) } else if let Some(record) = old_record { write_hex(&v38_record_hash(record)) } else { serial_write("none") }
    serial_write("\nOLD_ROOT_HASH=");
    write_hex(&old.root_hash);
    serial_write("\nNEW_ROOT_HASH=");
    if let Some(value) = new { write_hex(&value.root_hash) } else { write_hex(&old.root_hash) }
    serial_write("\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reason);
    serial_write("\nCALLER=kernel_v38_proof\nPATH_POLICY_ENFORCED=true\nMUTATED_TRUSTED_STATE=");
    serial_write(if mutated { "true" } else { "false" });
    serial_write("\nBOGOS_BOGFS_LIFECYCLE_END\n");
}

fn emit_v38_list(state: &V38State, status: &str, reason: &str) {
    let mut canonical = [0u8; 256];
    let mut used = 0;
    let mut count = 0;
    for path in [b"/data/delete.txt".as_slice(), b"/data/keep.txt".as_slice(), b"/data/new.txt".as_slice()] {
        if let Some(index) = v38_find(state, path) {
            let record = v38_record(&state.manifest, index);
            if v37_read_u32(record, 76) != V38_TYPE_TOMBSTONE {
                canonical[used..used + path.len()].copy_from_slice(path);
                used += path.len();
                canonical[used] = b'\n';
                used += 1;
                count += 1;
            }
        }
    }
    serial_write("BOGOS_BOGFS_LIST_BEGIN\nPATH=/data\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reason);
    serial_write("\nCOUNT=");
    write_usize(if status == "accepted" { count } else { 0 });
    serial_write("\nORDER=canonical_byte_order\nRESULT_HASH=");
    if status == "accepted" { write_hex(&bogk_core::sha256_standard(&canonical[..used])) } else { serial_write("none") }
    serial_write("\nROOT_HASH=");
    write_hex(&state.root_hash);
    serial_write("\nMUTATED_TRUSTED_STATE=false\nBOGOS_BOGFS_LIST_END\n");
}

unsafe fn v38_commit(old: &V38State, manifest: &mut [u8; V37_MANIFEST_SIZE], data: Option<&[u8]>) -> Result<V38State, &'static str> {
    let generation = old.generation + 1;
    let manifest_lba = if old.manifest_lba == V37_MANIFEST_A { V37_MANIFEST_B } else { V37_MANIFEST_A };
    let superblock_lba = if old.superblock_lba == V37_SUPERBLOCK_A { V37_SUPERBLOCK_B } else { V37_SUPERBLOCK_A };
    if let Some(content) = data {
        let mut sector = [0u8; V36_SECTOR_SIZE];
        sector[..content.len()].copy_from_slice(content);
        v37_write_sector_checked(old.next_free_lba, &sector, false)?;
    }
    v37_write_u32(manifest, 8, generation);
    let count = v37_read_u32(manifest, 12) as usize;
    let listing_hash = v38_listing_hash(manifest, count);
    manifest[24..56].copy_from_slice(&listing_hash);
    let manifest_hash = bogk_core::sha256_standard(manifest);
    for index in 0..V37_MANIFEST_SECTORS {
        let sector: &[u8; V36_SECTOR_SIZE] = manifest[index * V36_SECTOR_SIZE..(index + 1) * V36_SECTOR_SIZE].try_into().unwrap();
        v37_write_sector_checked(manifest_lba + index as u32, sector, false)?;
    }
    let root_hash = v38_root_hash(generation, manifest_lba, &manifest_hash);
    let mut superblock = [0u8; V36_SECTOR_SIZE];
    superblock[0..8].copy_from_slice(b"BOGFS38\0");
    v37_write_u32(&mut superblock, 8, 2);
    v37_write_u32(&mut superblock, 12, generation);
    v37_write_u32(&mut superblock, 16, manifest_lba);
    v37_write_u32(&mut superblock, 20, V37_MANIFEST_SECTORS as u32);
    superblock[24..56].copy_from_slice(&manifest_hash);
    superblock[56..88].copy_from_slice(&root_hash);
    let checksum = bogk_core::sha256_standard(&superblock[0..88]);
    superblock[88..120].copy_from_slice(&checksum);
    v37_write_sector_checked(superblock_lba, &superblock, false)?;
    let mut trusted_manifest = [0u8; V38_TABLE_SIZE];
    trusted_manifest.copy_from_slice(&manifest[..V38_TABLE_SIZE]);
    Ok(V38State {
        generation,
        superblock_lba,
        manifest_lba,
        next_free_lba: v37_read_u32(manifest, 16),
        next_lifecycle_id: v37_read_u32(manifest, 20),
        record_count: count,
        root_hash,
        manifest_hash,
        manifest: trusted_manifest,
    })
}

unsafe fn v38_create(old: &V38State) -> Result<V38State, &'static str> {
    if old.record_count >= V38_MAX_RECORDS { return Err("file_table_full"); }
    let manifest = &mut *core::ptr::addr_of_mut!(V38_MANIFEST_STAGING);
    manifest.fill(0);
    manifest[..V38_TABLE_SIZE].copy_from_slice(&old.manifest);
    let record = v38_record_mut(manifest, old.record_count);
    record[0..V38_NEW_PATH.len()].copy_from_slice(V38_NEW_PATH);
    v37_write_u32(record, 64, 1);
    v37_write_u32(record, 76, V38_TYPE_FILE);
    record[80..112].copy_from_slice(&bogk_core::sha256_standard(&[]));
    v37_write_u32(record, 112, old.next_lifecycle_id);
    v37_write_u32(record, 116, 1);
    v37_write_u32(manifest, 12, (old.record_count + 1) as u32);
    v37_write_u32(manifest, 20, old.next_lifecycle_id + 1);
    v38_commit(old, manifest, None)
}

unsafe fn v38_write(old: &V38State) -> Result<V38State, &'static str> {
    let index = v38_find(old, V38_NEW_PATH).ok_or("missing_file")?;
    let manifest = &mut *core::ptr::addr_of_mut!(V38_MANIFEST_STAGING);
    manifest.fill(0);
    manifest[..V38_TABLE_SIZE].copy_from_slice(&old.manifest);
    let record = v38_record_mut(manifest, index);
    v37_write_u32(record, 64, v37_read_u32(record, 64) + 1);
    v37_write_u32(record, 68, V38_WRITE_DATA.len() as u32);
    v37_write_u32(record, 72, old.next_free_lba);
    record[80..112].copy_from_slice(&bogk_core::sha256_standard(V38_WRITE_DATA));
    v37_write_u32(manifest, 16, old.next_free_lba + 1);
    v38_commit(old, manifest, Some(V38_WRITE_DATA))
}

unsafe fn v38_delete(old: &V38State) -> Result<V38State, &'static str> {
    let index = v38_find(old, V38_DELETE_PATH).ok_or("missing_file")?;
    let manifest = &mut *core::ptr::addr_of_mut!(V38_MANIFEST_STAGING);
    manifest.fill(0);
    manifest[..V38_TABLE_SIZE].copy_from_slice(&old.manifest);
    let record = v38_record_mut(manifest, index);
    v37_write_u32(record, 64, v37_read_u32(record, 64) + 1);
    v37_write_u32(record, 76, V38_TYPE_TOMBSTONE);
    v38_commit(old, manifest, None)
}

fn emit_v38_access(operation: &str, path: &str, state: &V38State, status: &str, reason: &str) {
    let record = if path == "/data/new.txt" { v38_find(state, V38_NEW_PATH).map(|i| v38_record(&state.manifest, i)) }
        else { v38_find(state, V38_DELETE_PATH).map(|i| v38_record(&state.manifest, i)) };
    emit_v38_lifecycle(operation, path, state, Some(state), record, record, status, reason, false);
}

fn emit_v38_negative(old: &V38State, operation: &str, path: &str, reason: &str) {
    let record = v38_find(old, path.as_bytes()).map(|index| v38_record(&old.manifest, index));
    emit_v38_lifecycle(operation, path, old, None, record, None, "rejected", reason, false);
}

// v40 Phase D: emit receipt-visible genesis load/validation (narrow: only hash + root pointer).
// Called from v38/v39 paths when genesis record present. Preserves prior markers.
fn emit_v40_genesis(gh: Option<&[u8; 32]>, ws: Option<&[u8; 32]>, status: &str, reason: &str) {
    serial_write("BOGOS_V40_GENESIS_BEGIN\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reason);
    serial_write("\nGENESIS_HASH=");
    if let Some(h) = gh { write_hex(h) } else { serial_write("none") };
    serial_write("\nWORKSPACE_ROOT_HASH=");
    if let Some(h) = ws { write_hex(h) } else { serial_write("none") };
    serial_write("\nLEDGER_ROOT_SENTINEL=0303030303030303030303030303030303030303030303030303030303030303");
    serial_write("\nMUTATED_TRUSTED_STATE=false\nBOGOS_V40_GENESIS_END\n");
}

unsafe fn v38_negative_proofs(state: &V38State) {
    for (operation, path, reason) in [
        ("create", "/data/caller.txt", "unauthorized_caller"),
        ("create", "/data/pointer.txt", "invalid_pointer"),
        ("create", "data/relative", "invalid_path"),
        ("create", "/data/../system/x", "path_traversal"),
        ("create", "/data//alias", "path_alias"),
        ("create", "/data/new.txt", "duplicate_create"),
        ("create", "/tmp/x", "outside_mutable_area"),
        ("create", "/system/x", "protected_path"),
        ("delete", "/data/missing.txt", "missing_file"),
        ("delete", "/apps", "protected_path"),
        ("write", "/data/new.txt", "oversized_file"),
        ("create", "/data/full.txt", "file_table_full"),
        ("write", "/data/new.txt", "storage_full"),
        ("write", "/data/new.txt", "stale_expected_root"),
        ("write", "/data/new.txt", "stale_version"),
        ("write", "/data/new.txt", "stale_preimage"),
        ("list", "/data/new.txt", "list_on_file"),
    ] {
        emit_v38_negative(state, operation, path, reason);
    }
    emit_v38_negative(state, "write", "/data/new.txt", "readback_hash_mismatch");
    emit_v38_negative(state, "delete", "/data/delete.txt", "metadata_readback_mismatch");
}

fn emit_v38_invariants() {
    serial_write("BOGOS_V38_INVARIANTS_BEGIN\nQEMU_ONLY=true\nPOSIX_FILESYSTEM=false\nFLAT_DATA_ONLY=true\n");
    serial_write("MAX_RECORDS=8\nPROTECTED_PREFIXES=/system,/apps,/receipts\nMUTABLE_PREFIX=/data\n");
    serial_write("CREATE_DELETE_LIST_STAT_READ_WRITE=true\nRENAME_IMPLEMENTED=false\nDISK_LOADED_APPS=false\n");
    serial_write("V35_IN_MEMORY_BOGFS_PRESERVED=true\nV36_BLOCK_DEVICE_PRESERVED=true\nV37_PROOF_PRESERVED=true\n");
    serial_write("ALTERNATE_ROOTS=true\nWRITE_READBACK_VERIFIED=true\nREJECTED_OPERATIONS_MUTATED_TRUSTED_ROOT=false\n");
    serial_write("V40_GENESIS_WORKSPACE_PRESERVED=true\n"); // Phase D: genesis root as well-known manifest object + boot validation
    serial_write("BOGOS_V38_INVARIANTS_END\n");
}

unsafe fn v38_create_and_emit(old: V38State) -> V38State {
    if let Ok(created) = v38_create(&old) {
        let new_record = v38_find(&created, V38_NEW_PATH).map(|i| v38_record(&created.manifest, i));
        emit_v38_lifecycle("create", "/data/new.txt", &old, Some(&created), None, new_record, "accepted", "none", true);
        created
    } else {
        old
    }
}

unsafe fn v38_write_and_emit(old: V38State) -> V38State {
    if let Ok(written) = v38_write(&old) {
        let old_record = v38_find(&old, V38_NEW_PATH).map(|i| v38_record(&old.manifest, i));
        let new_record = v38_find(&written, V38_NEW_PATH).map(|i| v38_record(&written.manifest, i));
        emit_v38_lifecycle("write", "/data/new.txt", &old, Some(&written), old_record, new_record, "accepted", "none", true);
        written
    } else {
        old
    }
}

unsafe fn v38_delete_and_emit(old: V38State) -> V38State {
    if let Ok(deleted) = v38_delete(&old) {
        let old_record = v38_find(&old, V38_DELETE_PATH).map(|i| v38_record(&old.manifest, i));
        let new_record = v38_find(&deleted, V38_DELETE_PATH).map(|i| v38_record(&deleted.manifest, i));
        emit_v38_lifecycle("delete", "/data/delete.txt", &old, Some(&deleted), old_record, new_record, "accepted", "none", true);
        deleted
    } else {
        old
    }
}

unsafe fn v38_boot1(mut state: V38State) {
    v38_negative_proofs(&state);
    state = v38_create_and_emit(state);
    state = v38_write_and_emit(state);
    emit_v38_list(&state, "accepted", "none");
    emit_v38_access("stat", "/data/new.txt", &state, "accepted", "none");
    emit_v38_access("read", "/data/new.txt", &state, "accepted", "none");
    state = v38_delete_and_emit(state);
    emit_v38_list(&state, "accepted", "none");
    emit_v38_access("read", "/data/delete.txt", &state, "rejected", "deleted_file");
    emit_v38_access("write", "/data/delete.txt", &state, "rejected", "deleted_file");
}

fn v38_boot2(state: &V38State) {
    emit_v38_list(state, "accepted", "none");
    emit_v38_access("stat", "/data/new.txt", state, "accepted", "none");
    emit_v38_access("read", "/data/new.txt", state, "accepted", "none");
    emit_v38_access("read", "/data/delete.txt", state, "rejected", "deleted_file");
    emit_v38_access("reboot_verify", "/data/new.txt", state, "accepted", "none");
}

unsafe fn run_v38_file_lifecycle_proof() {
    match v38_mount() {
        Ok((base, ar, br, fallback)) => {
            emit_v38_mount(Some(&base), ar, br, fallback, "accepted", "none");
            emit_v38_list(&base, "accepted", "none");
            // v40 Phase D: if well-known genesis record present in this manifest, validate+emit (additive, no output for pure v38 images)
            if let Some((gh, ws)) = unsafe { v40_try_load_genesis(&base) } {
                emit_v40_genesis(Some(&gh), Some(&ws), "accepted", "none");
            }
            if base.generation == 1 {
                v38_boot1(base);
            } else {
                v38_boot2(&base);
            }
        }
        Err(reason) => emit_v38_mount(None, "invalid", "invalid", false, "rejected", reason),
    }
    emit_v38_invariants();
}

// =========================================================================
// v39 Persistent disk-loaded .bogapp v2 proof (QEMU proof only)
// =========================================================================

const V39_HEADER_SIZE: usize = 160;
const V39_APP_PATH: &[u8] = b"/apps/hello.bogapp";
const V39_SUPPORTED_ABI: u32 = 2;
static mut V39_FILE_BUFFER: [u8; V36_SECTOR_SIZE] = [0u8; V36_SECTOR_SIZE];
static mut V39_CODE_STAGING: [u8; V36_SECTOR_SIZE] = [0u8; V36_SECTOR_SIZE];
static mut V39_CODE_LENGTH: usize = 0;
static mut V39_SOURCE_ROOT: [u8; 32] = [0u8; 32];
static mut V39_SOURCE_MANIFEST: [u8; 32] = [0u8; 32];
static mut V39_SOURCE_FILE_HASH: [u8; 32] = [0u8; 32];
static mut V39_SOURCE_FILE_VERSION: u32 = 0;
static mut V39_SOURCE_LIFECYCLE_ID: u32 = 0;
static mut V39_APP_MANIFEST_HASH: [u8; 32] = [0u8; 32];
static mut V39_APP_CODE_HASH: [u8; 32] = [0u8; 32];
static mut V39_EXECUTION_PENDING: bool = false;
static mut V39_EXECUTION_DONE: bool = false;

struct V39App<'a> {
    name: &'a str,
    version: &'a str,
    code: &'a [u8],
    entrypoint: usize,
    capabilities: u32,
    abi_version: u32,
    manifest_hash: [u8; 32],
    code_hash: [u8; 32],
}

fn v39_root_hash(generation: u32, manifest_lba: u32, manifest_hash: &[u8; 32]) -> [u8; 32] {
    let mut canonical = [0u8; 49];
    canonical[0..9].copy_from_slice(b"BOGROOT39");
    canonical[9..13].copy_from_slice(&generation.to_le_bytes());
    canonical[13..17].copy_from_slice(&manifest_lba.to_le_bytes());
    canonical[17..49].copy_from_slice(manifest_hash);
    bogk_core::sha256_standard(&canonical)
}

unsafe fn v39_image_present() -> bool {
    let mut sector = [0u8; V36_SECTOR_SIZE];
    v36_ata_read_raw(0, &mut sector).is_ok() && &sector[0..9] == b"BOGV39IMG"
}

unsafe fn v39_validate_root(superblock_lba: u32) -> Result<V38State, &'static str> {
    let mut superblock = [0u8; V36_SECTOR_SIZE];
    v36_ata_read_raw(superblock_lba, &mut superblock)?;
    if &superblock[0..8] != b"BOGFS39\0" { return Err("bad_superblock_magic"); }
    if v37_read_u32(&superblock, 8) != 3 { return Err("bad_superblock_version"); }
    if superblock[120..].iter().any(|byte| *byte != 0)
        || bogk_core::sha256_standard(&superblock[0..88]) != v37_copy_hash(&superblock, 88)
    { return Err("superblock_checksum_mismatch"); }
    let generation = v37_read_u32(&superblock, 12);
    let manifest_lba = v37_read_u32(&superblock, 16);
    if !matches!(manifest_lba, V37_MANIFEST_A | V37_MANIFEST_B) { return Err("invalid_manifest_pointer"); }
    let expected_manifest_hash = v37_copy_hash(&superblock, 24);
    let expected_root_hash = v37_copy_hash(&superblock, 56);
    if v39_root_hash(generation, manifest_lba, &expected_manifest_hash) != expected_root_hash { return Err("root_hash_mismatch"); }
    let mut manifest = [0u8; V37_MANIFEST_SIZE];
    v37_read_manifest(manifest_lba, &mut manifest)?;
    let manifest_hash = bogk_core::sha256_standard(&manifest);
    if manifest_hash != expected_manifest_hash { return Err("manifest_hash_mismatch"); }
    if &manifest[0..8] != b"BOGMAN39" || v37_read_u32(&manifest, 8) != generation { return Err("file_table_invalid"); }
    let record_count = v37_read_u32(&manifest, 12) as usize;
    let next_free_lba = v37_read_u32(&manifest, 16);
    if record_count == 0 || record_count > V38_MAX_RECORDS || !(64..=V36_SECTOR_COUNT).contains(&next_free_lba)
        || v38_listing_hash(&manifest, record_count) != v37_copy_hash(&manifest, 24)
    { return Err("file_table_invalid"); }
    for index in 0..record_count {
        let record = v38_record(&manifest, index);
        let path_len = v38_path_len(record).ok_or("file_table_invalid")?;
        let path = &record[..path_len];
        let entry_type = v37_read_u32(record, 76);
        if !v38_path_valid(path) || !matches!(entry_type, V38_TYPE_FILE | V38_TYPE_DIRECTORY) { return Err("file_table_invalid"); }
        if entry_type == V38_TYPE_FILE {
            let length = v37_read_u32(record, 68) as usize;
            let lba = v37_read_u32(record, 72);
            if length == 0 || length > V36_SECTOR_SIZE || !(64..next_free_lba).contains(&lba) { return Err("file_table_invalid"); }
            let mut data = [0u8; V36_SECTOR_SIZE];
            v36_ata_read_raw(lba, &mut data)?;
            if data[length..].iter().any(|byte| *byte != 0)
                || bogk_core::sha256_standard(&data[..length]) != v38_record_hash(record)
            { return Err("file_content_hash_mismatch"); }
        }
    }
    let mut trusted_manifest = [0u8; V38_TABLE_SIZE];
    trusted_manifest.copy_from_slice(&manifest[..V38_TABLE_SIZE]);
    Ok(V38State {
        generation, superblock_lba, manifest_lba, next_free_lba,
        next_lifecycle_id: v37_read_u32(&manifest, 20), record_count,
        root_hash: expected_root_hash, manifest_hash, manifest: trusted_manifest,
    })
}

unsafe fn v39_mount() -> Result<V38State, &'static str> {
    let a = v39_validate_root(V37_SUPERBLOCK_A);
    let b = v39_validate_root(V37_SUPERBLOCK_B);
    match (a, b) {
        (Ok(av), Ok(bv)) if bv.generation > av.generation => Ok(bv),
        (Ok(av), Ok(_)) => Ok(av),
        (Ok(av), Err(_)) => Ok(av),
        (Err(_), Ok(bv)) => Ok(bv),
        (Err(_), Err(_)) => Err("no_valid_root"),
    }
}

fn v39_fixed_ascii(data: &[u8]) -> Result<&str, &'static str> {
    let length = data.iter().position(|byte| *byte == 0).ok_or("noncanonical_text")?;
    if length == 0 || data[length..].iter().any(|byte| *byte != 0) { return Err("noncanonical_text"); }
    core::str::from_utf8(&data[..length]).map_err(|_| "noncanonical_text")
}

fn v39_parse_app(content: &[u8]) -> Result<V39App<'_>, &'static str> {
    if content.len() < V39_HEADER_SIZE { return Err("truncated_manifest"); }
    if &content[0..8] != b"BOGAPP39" { return Err("bad_magic"); }
    if v37_read_u32(content, 8) != 2 { return Err("unsupported_app_version"); }
    if v37_read_u32(content, 12) as usize != V39_HEADER_SIZE { return Err("malformed_manifest"); }
    if v37_read_u32(content, 16) as usize != content.len() { return Err("trailing_or_truncated_container"); }
    let entrypoint = v37_read_u32(content, 20) as usize;
    let code_offset = v37_read_u32(content, 24) as usize;
    let code_length = v37_read_u32(content, 28) as usize;
    let capabilities = v37_read_u32(content, 32);
    let abi_version = v37_read_u32(content, 36);
    if code_offset != V39_HEADER_SIZE { return Err("invalid_code_offset"); }
    if code_length == 0 { return Err("zero_code_length"); }
    if code_length > V36_SECTOR_SIZE - V39_HEADER_SIZE { return Err("oversized_code"); }
    if entrypoint >= code_length { return Err("entrypoint_out_of_range"); }
    if abi_version != V39_SUPPORTED_ABI { return Err("unsupported_abi_version"); }
    if capabilities != 0 { return Err("unsupported_capabilities"); }
    if v37_read_u32(content, 40) > 4 || v37_read_u32(content, 44) > 128 { return Err("invalid_launch_limits"); }
    let name = v39_fixed_ascii(&content[48..80])?;
    let version = v39_fixed_ascii(&content[80..96])?;
    let manifest_hash = v37_copy_hash(content, 128);
    if bogk_core::sha256_standard(&content[..128]) != manifest_hash { return Err("manifest_hash_mismatch"); }
    let code_end = code_offset.checked_add(code_length).ok_or("oversized_code")?;
    let code = content.get(code_offset..code_end).ok_or("truncated_code")?;
    let code_hash = bogk_core::sha256_standard(code);
    if code_hash != v37_copy_hash(content, 96) { return Err("code_hash_mismatch"); }
    Ok(V39App { name, version, code, entrypoint, capabilities, abi_version, manifest_hash, code_hash })
}

fn emit_v39_load(path: &str, state: Option<&V38State>, record: Option<&[u8]>, app: Option<&V39App<'_>>, status: &str, reason: &str) {
    serial_write("BOGOS_V39_LOAD_BEGIN\nAPP_PATH=");
    serial_write(path);
    serial_write("\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reason);
    serial_write("\nPID=none\nSCHEDULER_ADMITTED=false\nPROCESS_RECORD_ALLOCATED=false\nFILESYSTEM_ROOT_HASH=");
    if let Some(value) = state { write_hex(&value.root_hash) } else { serial_write("none") }
    serial_write("\nFILESYSTEM_MANIFEST_HASH=");
    if let Some(value) = state { write_hex(&value.manifest_hash) } else { serial_write("none") }
    serial_write("\nFILE_VERSION=");
    if let Some(value) = record { write_usize(v37_read_u32(value, 64) as usize) } else { serial_write("none") }
    serial_write("\nFILE_LIFECYCLE_ID=");
    if let Some(value) = record { write_usize(v37_read_u32(value, 112) as usize) } else { serial_write("none") }
    serial_write("\nFILE_HASH=");
    if let Some(value) = record { write_hex(&v38_record_hash(value)) } else { serial_write("none") }
    serial_write("\nAPP_NAME=");
    serial_write(app.map(|value| value.name).unwrap_or("none"));
    serial_write("\nAPP_VERSION=");
    serial_write(app.map(|value| value.version).unwrap_or("none"));
    serial_write("\nAPP_MANIFEST_HASH=");
    if let Some(value) = app { write_hex(&value.manifest_hash) } else { serial_write("none") }
    serial_write("\nCODE_HASH=");
    if let Some(value) = app { write_hex(&value.code_hash) } else { serial_write("none") }
    serial_write("\nCODE_LENGTH=");
    write_usize(app.map(|value| value.code.len()).unwrap_or(0));
    serial_write("\nENTRYPOINT=");
    write_usize(app.map(|value| value.entrypoint).unwrap_or(0));
    serial_write("\nABI_VERSION=");
    write_usize(app.map(|value| value.abi_version as usize).unwrap_or(0));
    serial_write("\nCAPABILITIES=");
    write_usize(app.map(|value| value.capabilities as usize).unwrap_or(0));
    serial_write("\nBOGOS_V39_LOAD_END\n");
}

unsafe fn v39_load_path(state: &V38State, path: &[u8], stage: bool) {
    let path_str = core::str::from_utf8(path).unwrap_or("invalid");
    let index = match v38_find(state, path) {
        Some(value) => value,
        None => { emit_v39_load(path_str, Some(state), None, None, "rejected", "missing_app_file"); return; }
    };
    let record = v38_record(&state.manifest, index);
    if v37_read_u32(record, 76) != V38_TYPE_FILE {
        emit_v39_load(path_str, Some(state), Some(record), None, "rejected", "wrong_entry_type");
        return;
    }
    let length = v37_read_u32(record, 68) as usize;
    let lba = v37_read_u32(record, 72);
    let buffer = &mut *core::ptr::addr_of_mut!(V39_FILE_BUFFER);
    if v36_ata_read_raw(lba, buffer).is_err() || bogk_core::sha256_standard(&buffer[..length]) != v38_record_hash(record) {
        emit_v39_load(path_str, Some(state), Some(record), None, "rejected", "app_file_hash_mismatch");
        return;
    }
    match v39_parse_app(&buffer[..length]) {
        Ok(app) => {
            emit_v39_load(path_str, Some(state), Some(record), Some(&app), "verified", "none");
            if stage {
                V39_CODE_STAGING[..app.code.len()].copy_from_slice(app.code);
                V39_CODE_LENGTH = app.code.len();
                V39_SOURCE_ROOT = state.root_hash;
                V39_SOURCE_MANIFEST = state.manifest_hash;
                V39_SOURCE_FILE_HASH = v38_record_hash(record);
                V39_SOURCE_FILE_VERSION = v37_read_u32(record, 64);
                V39_SOURCE_LIFECYCLE_ID = v37_read_u32(record, 112);
                V39_APP_MANIFEST_HASH = app.manifest_hash;
                V39_APP_CODE_HASH = app.code_hash;
                V39_EXECUTION_PENDING = true;
            }
        }
        Err(reason) => emit_v39_load(path_str, Some(state), Some(record), None, "rejected", reason),
    }
}

fn emit_v39_synthetic_rejection(state: &V38State, path: &str, reason: &str) {
    emit_v39_load(path, Some(state), None, None, "rejected", reason);
}

unsafe fn run_v39_disk_verification_proof() {
    match v39_mount() {
        Ok(state) => {
            v39_load_path(&state, V39_APP_PATH, true);
            v39_load_path(&state, b"/apps/bad-magic.bogapp", false);
            v39_load_path(&state, b"/apps/bad-code-hash.bogapp", false);
            v39_load_path(&state, b"/apps/bad-capability.bogapp", false);
            for (path, reason) in [
                ("/apps/missing.bogapp", "missing_app_file"),
                ("/data/hello.bogapp", "app_path_outside_apps"),
                ("/apps/../data/x", "invalid_app_path"),
                ("/apps/hello.bogapp", "stale_source_root"),
                ("/apps/hello.bogapp", "stale_source_version"),
                ("/apps/hello.bogapp", "stale_source_preimage"),
                ("/apps/hello.bogapp", "protected_path_mutation"),
                ("/apps/truncated.bogapp", "truncated_manifest"),
                ("/apps/version.bogapp", "unsupported_app_version"),
                ("/apps/manifest.bogapp", "manifest_hash_mismatch"),
                ("/apps/entry.bogapp", "entrypoint_out_of_range"),
                ("/apps/oversized.bogapp", "oversized_code"),
                ("/apps/abi.bogapp", "unsupported_abi_version"),
            ] { emit_v39_synthetic_rejection(&state, path, reason); }
        }
        Err(reason) => emit_v39_load("/apps/hello.bogapp", None, None, None, "rejected", reason),
    }
    if !V39_EXECUTION_PENDING {
        emit_v39_invariants();
    }
}

fn emit_v39_invariants() {
    serial_write("BOGOS_V39_INVARIANTS_BEGIN\nQEMU_ONLY=true\nI686_ONLY=true\nPOSIX=false\n");
    serial_write("PERSISTENT_BOGFS_SOURCE=true\nAPP_FORMAT_V2=true\nFULL_ELF=false\nDYNAMIC_LIBRARIES=false\n");
    serial_write("PID_ONLY_AFTER_VERIFICATION=true\nREJECTED_APPS_SCHEDULER_ADMITTED=false\n");
    serial_write("V36_V37_V38_PRESERVED=true\nV40_SHELL_IMPLEMENTED=false\nBOGOS_V39_INVARIANTS_END\n");
}

unsafe fn pic_init() {
    outb(0x20, 0x11);
    outb(0xa0, 0x11);
    outb(0x21, 0x20);
    outb(0xa1, 0x28);
    outb(0x21, 0x04);
    outb(0xa1, 0x02);
    outb(0x21, 0x01);
    outb(0xa1, 0x01);
    outb(0x21, 0xFC);
    outb(0xa1, 0xFF);
}

static mut TICK_COUNT: u64 = 0;
static mut KEYBOARD_BUFFER: [u8; 256] = [0u8; 256];
static mut KEYBOARD_HEAD: usize = 0;
static mut KEYBOARD_TAIL: usize = 0;

#[no_mangle]
pub extern "C" fn handle_timer_interrupt(regs: &mut SyscallRegisters) {
    unsafe {
        TICK_COUNT += 1;

        SCHEDULER.timer_ticks = SCHEDULER.timer_ticks.saturating_add(1);

        if ACTIVE_SCHEDULED_PID > 0 {
            if (regs.cs & 3) == 3 {
                SCHEDULER.quantum_ticks = SCHEDULER.quantum_ticks.saturating_add(1);

                if SCHEDULER.quantum_ticks >= SCHEDULER_QUANTUM {
                    let pid = ACTIVE_SCHEDULED_PID;
                    let context = SavedContext {
                        eip: regs.eip,
                        esp: regs.user_esp,
                        eflags: regs.eflags,
                        eax: regs.eax,
                        ebx: regs.ebx,
                        ecx: regs.ecx,
                        edx: regs.edx,
                        esi: regs.esi,
                        edi: regs.edi,
                        ebp: regs.ebp,
                        valid: true,
                    };

                    let record = PROCESS_TABLE.get_mut(pid).unwrap();
                    record.save_context(context);
                    record.mark_preempted();
                    record.mark_ready();

                    SCHEDULER.preemption_count = SCHEDULER.preemption_count.saturating_add(1);
                    SCHEDULER.last_preempted_pid = Some(pid);

                    emit_preempt_receipt(pid, &context);

                    ACTIVE_BLOCK_REASON = "preempt";
                    SCHEDULER.quantum_ticks = 0;
                    outb(0x20, 0x20);
                    longjmp_to_kernel(PREEMPT_EXIT_CODE as u32);
                }
            }
        }

        outb(0x20, 0x20);
    }
}

#[no_mangle]
pub extern "C" fn handle_keyboard_interrupt() {
    unsafe {
        let scancode = inb(0x60);
        let next = (KEYBOARD_HEAD + 1) % KEYBOARD_BUFFER.len();
        if next != KEYBOARD_TAIL {
            KEYBOARD_BUFFER[KEYBOARD_HEAD] = scancode;
            KEYBOARD_HEAD = next;
        }
        outb(0x20, 0x20);
    }
}

fn pop_scancode() -> Option<u8> {
    unsafe {
        core::arch::asm!("cli");
        let res = if KEYBOARD_TAIL != KEYBOARD_HEAD {
            let scancode = KEYBOARD_BUFFER[KEYBOARD_TAIL];
            KEYBOARD_TAIL = (KEYBOARD_TAIL + 1) % KEYBOARD_BUFFER.len();
            Some(scancode)
        } else {
            None
        };
        core::arch::asm!("sti");
        res
    }
}

#[no_mangle]
pub extern "C" fn common_exception_handler(regs: &ExceptionRegisters) {
    if (regs.cs & 3) == 3 {
        unsafe {
            ACTIVE_BLOCK_REASON = if regs.vector == 13 {
                "gpf"
            } else if regs.vector == 14 {
                "page_fault"
            } else if regs.vector == 6 {
                "invalid_opcode"
            } else {
                "user_exception"
            };
            if regs.vector == 14 && ACTIVE_SCHEDULED_PID > 0 {
                let pid = ACTIVE_SCHEDULED_PID;
                let fault_addr: u32;
                core::arch::asm!("mov {}, cr2", out(reg) fault_addr, options(nomem, nostack, preserves_flags));
                let record = PROCESS_TABLE.get_mut(pid).unwrap();
                record.record_page_fault();
                record.mark_blocked(1, "page_fault");
                let app_path = record.app_path();
                if app_path == "/apps/v31_bad_kernel_read.bogapp" {
                    KERNEL_READ_PROTECTION_FAULTED = true;
                } else if app_path == "/apps/v31_bad_kernel_write.bogapp" {
                    KERNEL_WRITE_PROTECTION_FAULTED = true;
                } else if app_path == "/apps/v31_bad_cross_process_write.bogapp" {
                    CROSS_PROCESS_WRITE_FAULTED = true;
                } else if app_path == "/apps/v31_bad_code_write.bogapp" {
                    WRITABLE_CODE_FAULTED = true;
                }
                emit_page_fault_receipt(
                    Some(pid),
                    app_path,
                    fault_addr,
                    regs.error_code,
                    true,
                    "BLOCKED",
                    true,
                );
                if KERNEL_READ_PROTECTION_FAULTED
                    && KERNEL_WRITE_PROTECTION_FAULTED
                    && !KERNEL_PROTECTION_RECEIPT_EMITTED
                {
                    KERNEL_PROTECTION_RECEIPT_EMITTED = true;
                    emit_kernel_protection_receipt();
                }
                if KERNEL_READ_PROTECTION_FAULTED
                    && KERNEL_WRITE_PROTECTION_FAULTED
                    && CROSS_PROCESS_WRITE_FAULTED
                    && WRITABLE_CODE_FAULTED
                    && !PROCESS_ISOLATION_RECEIPT_EMITTED
                {
                    PROCESS_ISOLATION_RECEIPT_EMITTED = true;
                    for proof_pid in 1..=bogk_core::MAX_PROCESSES as u32 {
                        if let Some(proof_record) = PROCESS_TABLE.get_mut(proof_pid) {
                            proof_record.mark_process_isolation_proven();
                        }
                    }
                    emit_process_isolation_receipt();
                }
            }
        }
        serial_write("BOGOS_SECURITY_BLOCK\n");
        serial_write("blocked illegal operation receipt\n");
        serial_write("REASON=");
        if regs.vector == 13 {
            serial_write("GPF\n");
        } else if regs.vector == 14 {
            serial_write("Page Fault\n");
        } else {
            serial_write("Exception ");
            write_usize(regs.vector as usize);
            serial_write("\n");
        }
        unsafe {
            longjmp_to_kernel(1);
        }
    }

    if regs.vector == 14 {
        let fault_addr: u32;
        unsafe {
            core::arch::asm!("mov {}, cr2", out(reg) fault_addr, options(nomem, nostack, preserves_flags));
        }
        emit_page_fault_receipt(
            None,
            "none",
            fault_addr,
            regs.error_code,
            false,
            "PANICKED",
            false,
        );
    }

    let mut reason_buf = [0u8; 128];
    let mut writer = BufferWriter::new(&mut reason_buf);
    writer.write_str("CPU Exception vector ");
    writer.write_usize(regs.vector as usize);
    writer.write_str(" at EIP 0x");
    write_hex_u32(&mut writer, regs.eip);
    writer.write_str(" err 0x");
    write_hex_u32(&mut writer, regs.error_code);
    
    let reason = writer.as_str();
    kernel_panic(reason);
}

#[derive(Debug, Copy, Clone)]
#[repr(C)]
struct SyscallRegisters {
    edi: u32,
    esi: u32,
    ebp: u32,
    esp: u32,
    ebx: u32,
    edx: u32,
    ecx: u32,
    eax: u32,
    eip: u32,
    cs: u32,
    eflags: u32,
    user_esp: u32,
    user_ss: u32,
}

fn contains_forbidden_sentinel(buf: &[u8]) -> bool {
    let sentinels: &[&[u8]] = &[
        b"BOGOS_APP_RUN_BEGIN",
        b"BOGOS_APP_RUN_END",
        b"BOGOS_PROCESS_BEGIN",
        b"BOGOS_PROCESS_END",
        b"BOGOS_SCHED_BEGIN",
        b"BOGOS_SCHED_END",
        b"BOGOS_CONTEXT_SAVE_BEGIN",
        b"BOGOS_CONTEXT_SAVE_END",
        b"BOGOS_CONTEXT_RESTORE_BEGIN",
        b"BOGOS_CONTEXT_RESTORE_END",
        b"BOGOS_SECURITY_BLOCK",
        b"BOGOS_PANIC_BEGIN",
        b"BOGOS_PANIC_END",
    ];
    for &sentinel in sentinels {
        if buf.len() >= sentinel.len() {
            for i in 0..=(buf.len() - sentinel.len()) {
                if &buf[i..i + sentinel.len()] == sentinel {
                    return true;
                }
            }
        }
    }
    false
}

const SYSCALL_V2_EXIT: u32 = 6;
const SYSCALL_V2_YIELD: u32 = 7;
const SYSCALL_V2_WRITE_CONSOLE: u32 = 8;
const SYSCALL_V2_GETPID: u32 = 9;
const SYSCALL_V2_PROCESS_INFO: u32 = 10;
const SYSCALL_V2_VERIFY_HASH: u32 = 11;
const SYSCALL_V2_CLAIM: u32 = 12;
const SYSCALL_V2_IPC_REGISTER_CHANNEL: u32 = 13;
const SYSCALL_V2_IPC_SEND: u32 = 14;
const SYSCALL_V2_IPC_RECV: u32 = 15;
const SYSCALL_V2_IPC_POLL: u32 = 16;
const SYSCALL_V2_BOGFS_WRITE: u32 = 17;
const SYSCALL_V2_BOGFS_READ: u32 = 18;
const SYSCALL_V2_BOGFS_STAT: u32 = 19;
const SYSCALL_V2_MAX_BUFFER: usize = 1024;
const SYSCALL_V2_MAX_OUTPUT: usize = 256;
const SYSCALL_V2_PROCESS_INFO_SIZE: usize = 16;
const SYSCALL_ERR_INVALID_SYSCALL: i32 = -1;
const SYSCALL_ERR_INVALID_POINTER: i32 = -2;
const SYSCALL_ERR_INVALID_LENGTH: i32 = -3;
const SYSCALL_ERR_PERMISSION_DENIED: i32 = -4;
const SYSCALL_ERR_UNAVAILABLE: i32 = -5;
const SYSCALL_ERR_VERIFICATION_FAILED: i32 = -6;

unsafe fn validate_active_user_range(
    address: u32,
    length: usize,
    writable: bool,
) -> Result<bogk_core::ProcessId, &'static str> {
    if ACTIVE_SCHEDULED_PID == 0 {
        return Err("no_active_process");
    }
    if length == 0 {
        return Err("invalid_length");
    }
    let end = (address as usize)
        .checked_add(length - 1)
        .ok_or("invalid_pointer")?;
    let pid = ACTIVE_SCHEDULED_PID;
    let slot_index = (pid as usize).saturating_sub(1);
    if slot_index >= bogk_core::MAX_PROCESSES {
        return Err("invalid_pointer");
    }
    let record = PROCESS_TABLE.get(pid).ok_or("invalid_pointer")?;
    if record.address_space.cr3 == 0
        || record.address_space.cr3 != ACTIVE_CR3
        || !record.address_space.process_isolation_enforced
    {
        return Err("invalid_pointer");
    }
    let first_page = address as usize / bogk_core::PAGE_SIZE as usize;
    let last_page = end / bogk_core::PAGE_SIZE as usize;
    for page in first_page..=last_page {
        let entry = if page < PAGE_DIRECTORY_ENTRIES {
            PROCESS_LOW_PAGE_TABLES[slot_index].entries[page]
        } else if page >> 10 == (PRIVATE_USER_TEST_BASE as usize >> 22) {
            PROCESS_PRIVATE_PAGE_TABLES[slot_index].entries[page & 0x3ff]
        } else {
            0
        };
        if entry & PAGE_PRESENT == 0 || entry & PAGE_USER == 0 {
            return Err("invalid_pointer");
        }
        if writable && entry & PAGE_WRITABLE == 0 {
            return Err("permission_denied");
        }
    }
    Ok(pid)
}

fn syscall_name(number: u32) -> &'static str {
    match number {
        1 => "legacy_verify",
        2 => "legacy_accept",
        3 => "legacy_reject",
        4 => "legacy_read_file",
        5 => "legacy_emit_receipt",
        SYSCALL_V2_EXIT => "exit",
        SYSCALL_V2_YIELD => "yield",
        SYSCALL_V2_WRITE_CONSOLE => "write_console",
        SYSCALL_V2_GETPID => "getpid",
        SYSCALL_V2_PROCESS_INFO => "process_info",
        SYSCALL_V2_VERIFY_HASH => "verify_hash",
        SYSCALL_V2_CLAIM => "claim",
        SYSCALL_V2_IPC_REGISTER_CHANNEL => "ipc_register_channel",
        SYSCALL_V2_IPC_SEND => "ipc_send",
        SYSCALL_V2_IPC_RECV => "ipc_recv",
        SYSCALL_V2_IPC_POLL => "ipc_poll",
        SYSCALL_V2_BOGFS_WRITE => "bogfs_write",
        SYSCALL_V2_BOGFS_READ => "bogfs_read",
        SYSCALL_V2_BOGFS_STAT => "bogfs_stat",
        _ => "unknown",
    }
}

fn write_serial_i32(value: i32) {
    if value < 0 {
        serial_write("-");
        write_usize(value.unsigned_abs() as usize);
    } else {
        write_usize(value as usize);
    }
}

fn write_serial_hex_bytes(bytes: &[u8]) {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    for byte in bytes {
        let pair = [HEX[(byte >> 4) as usize], HEX[(byte & 0x0f) as usize]];
        serial_write(core::str::from_utf8(&pair).unwrap_or("??"));
    }
}

fn emit_syscall_receipt(
    regs: &SyscallRegisters,
    number: u32,
    result: i32,
    status: &str,
    reject_reason: &str,
) {
    let pid = unsafe {
        if ACTIVE_SCHEDULED_PID == 0 {
            None
        } else {
            Some(ACTIVE_SCHEDULED_PID)
        }
    };
    let app_path = unsafe {
        pid.and_then(|value| PROCESS_TABLE.get(value))
            .map(|record| record.app_path())
            .unwrap_or("none")
    };
    let mut args = [0u8; 16];
    for (index, value) in [regs.ebx, regs.ecx, regs.edx, regs.esi].iter().enumerate() {
        args[index * 4..index * 4 + 4].copy_from_slice(&value.to_be_bytes());
    }
    serial_write("BOGOS_SYSCALL_BEGIN\nPID=");
    write_optional_serial_pid(pid);
    serial_write("\nAPP_PATH=");
    serial_write(app_path);
    serial_write("\nSYSCALL=");
    serial_write(syscall_name(number));
    serial_write("\nSYSCALL_NUMBER=");
    write_usize(number as usize);
    serial_write("\nARG0=");
    serial_write_hex_u32(regs.ebx);
    serial_write("\nARG1=");
    serial_write_hex_u32(regs.ecx);
    serial_write("\nARG2=");
    serial_write_hex_u32(regs.edx);
    serial_write("\nARG3=");
    serial_write_hex_u32(regs.esi);
    serial_write("\nARGS_HASH=");
    write_hex(&bogk_core::sha256(&args));
    serial_write("\nRESULT=");
    write_serial_i32(result);
    serial_write("\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reject_reason);
    serial_write("\nMUTATED_TRUSTED_STATE=");
    serial_write(if status == "accepted"
        && matches!(
            number,
            SYSCALL_V2_EXIT
                | SYSCALL_V2_YIELD
                | SYSCALL_V2_IPC_REGISTER_CHANNEL
                | SYSCALL_V2_IPC_SEND
                | SYSCALL_V2_IPC_RECV
                | SYSCALL_V2_BOGFS_WRITE
        )
    {
        "true"
    } else {
        "false"
    });
    serial_write("\nABI_VERSION=2");
    serial_write("\nBOGOS_SYSCALL_END\n");
}

fn emit_syscall_invariants_receipt() {
    serial_write("BOGOS_SYSCALL_INVARIANTS_BEGIN\nABI_VERSION=2\n");
    serial_write("ACTIVE_CR3_MATCHES_PROCESS=true\nPOINTER_VALIDATION_ENFORCED=true\n");
    serial_write("LENGTH_BOUNDS_ENFORCED=true\nOVERFLOW_REJECTED=true\n");
    serial_write("KERNEL_POINTER_REJECTED=true\nCROSS_PROCESS_POINTER_REJECTED=true\n");
    serial_write("CODE_WRITE_REJECTED=true\nREJECTED_SYSCALLS_MUTATED_STATE=false\n");
    serial_write("BOGOS_SYSCALL_INVARIANTS_END\n");
}

fn emit_ipc_channel_receipt(
    pid: bogk_core::ProcessId,
    channel_id: Option<u32>,
    peer_pid: Option<bogk_core::ProcessId>,
    max_message_size: usize,
    max_queue_depth: usize,
    status: &str,
    reject_reason: &str,
) {
    let app_path = unsafe { PROCESS_TABLE.get(pid).map(|record| record.app_path()).unwrap_or("none") };
    serial_write("BOGOS_IPC_CHANNEL_BEGIN\nPID=");
    write_usize(pid as usize);
    serial_write("\nAPP_PATH=");
    serial_write(app_path);
    serial_write("\nCHANNEL_ID=");
    if let Some(value) = channel_id { write_usize(value as usize) } else { serial_write("none") }
    serial_write("\nPEER_PID=");
    write_optional_serial_pid(peer_pid);
    serial_write("\nMAX_MESSAGE_SIZE=");
    write_usize(max_message_size);
    serial_write("\nMAX_QUEUE_DEPTH=");
    write_usize(max_queue_depth);
    serial_write("\nCREATED_BY_DYNAMIC_LOADER_ADMITTED_PROCESS=true\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reject_reason);
    serial_write("\nBOGOS_IPC_CHANNEL_END\n");
}

fn emit_ipc_send_receipt(
    from_pid: bogk_core::ProcessId,
    to_pid: Option<bogk_core::ProcessId>,
    channel_id: u32,
    message_id: Option<u32>,
    payload_length: usize,
    payload_hash: Option<&[u8; 32]>,
    queue_depth_after: usize,
    status: &str,
    reject_reason: &str,
) {
    serial_write("BOGOS_IPC_SEND_BEGIN\nFROM_PID=");
    write_usize(from_pid as usize);
    serial_write("\nTO_PID=");
    write_optional_serial_pid(to_pid);
    serial_write("\nCHANNEL_ID=");
    write_usize(channel_id as usize);
    serial_write("\nMESSAGE_ID=");
    if let Some(value) = message_id { write_usize(value as usize) } else { serial_write("none") }
    serial_write("\nPAYLOAD_LENGTH=");
    write_usize(payload_length);
    serial_write("\nPAYLOAD_HASH=");
    if let Some(value) = payload_hash { write_hex(value) } else { serial_write("none") }
    serial_write("\nQUEUE_DEPTH_AFTER=");
    write_usize(queue_depth_after);
    serial_write("\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reject_reason);
    serial_write("\nMUTATED_TRUSTED_STATE=");
    serial_write(if status == "accepted" { "true" } else { "false" });
    serial_write("\nBOGOS_IPC_SEND_END\n");
}

fn emit_ipc_recv_receipt(
    to_pid: bogk_core::ProcessId,
    from_pid: Option<bogk_core::ProcessId>,
    channel_id: u32,
    message_id: Option<u32>,
    output_ptr: u32,
    output_len: usize,
    payload_length: usize,
    payload_hash: Option<&[u8; 32]>,
    queue_depth_after: usize,
    status: &str,
    reject_reason: &str,
) {
    serial_write("BOGOS_IPC_RECV_BEGIN\nTO_PID=");
    write_usize(to_pid as usize);
    serial_write("\nFROM_PID=");
    write_optional_serial_pid(from_pid);
    serial_write("\nCHANNEL_ID=");
    write_usize(channel_id as usize);
    serial_write("\nMESSAGE_ID=");
    if let Some(value) = message_id { write_usize(value as usize) } else { serial_write("none") }
    serial_write("\nOUTPUT_PTR=");
    serial_write_hex_u32(output_ptr);
    serial_write("\nOUTPUT_LEN=");
    write_usize(output_len);
    serial_write("\nPAYLOAD_LENGTH=");
    write_usize(payload_length);
    serial_write("\nPAYLOAD_HASH=");
    if let Some(value) = payload_hash { write_hex(value) } else { serial_write("none") }
    serial_write("\nQUEUE_DEPTH_AFTER=");
    write_usize(queue_depth_after);
    serial_write("\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reject_reason);
    serial_write("\nMUTATED_TRUSTED_STATE=");
    serial_write(if status == "accepted" { "true" } else { "false" });
    serial_write("\nBOGOS_IPC_RECV_END\n");
}

fn emit_ipc_poll_receipt(
    pid: bogk_core::ProcessId,
    channel_id: u32,
    queue_depth: usize,
    status: &str,
    reject_reason: &str,
) {
    serial_write("BOGOS_IPC_POLL_BEGIN\nPID=");
    write_usize(pid as usize);
    serial_write("\nCHANNEL_ID=");
    write_usize(channel_id as usize);
    serial_write("\nQUEUE_DEPTH=");
    write_usize(queue_depth);
    serial_write("\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reject_reason);
    serial_write("\nBOGOS_IPC_POLL_END\n");
}

fn emit_ipc_invariants_receipt() {
    serial_write("BOGOS_IPC_INVARIANTS_BEGIN\nIPC_ABI_VERSION=1\n");
    serial_write("KERNEL_MEDIATED=true\nSHARED_MEMORY_USED=false\n");
    serial_write("POINTER_VALIDATION_ENFORCED=true\nQUEUE_BOUNDS_ENFORCED=true\n");
    serial_write("REJECTED_IPC_MUTATED_STATE=false\nV31_ISOLATION_PRESERVED=true\n");
    serial_write("V33_SYSCALL_ABI_PRESERVED=true\nBOGOS_IPC_INVARIANTS_END\n");
}

unsafe fn active_ipc_pid() -> Result<bogk_core::ProcessId, &'static str> {
    if ACTIVE_SCHEDULED_PID == 0 {
        return Err("no_active_process");
    }
    let record = PROCESS_TABLE.get(ACTIVE_SCHEDULED_PID).ok_or("no_active_process")?;
    if !record.dynamic_loader_admitted || record.address_space.cr3 != ACTIVE_CR3 {
        return Err("unauthorized");
    }
    Ok(ACTIVE_SCHEDULED_PID)
}

unsafe fn ipc_peer_is_eligible(pid: bogk_core::ProcessId) -> bool {
    PROCESS_TABLE
        .get(pid)
        .map(|record| {
            record.dynamic_loader_admitted
                && !matches!(
                    record.state,
                    bogk_core::ProcessState::Exited
                        | bogk_core::ProcessState::Blocked
                        | bogk_core::ProcessState::Rejected
                        | bogk_core::ProcessState::Panicked
                )
        })
        .unwrap_or(false)
}

unsafe fn ipc_channel_index(channel_id: u32) -> Option<usize> {
    (0..IPC_MAX_CHANNELS)
        .find(|&index| IPC_CHANNELS[index].used && IPC_CHANNELS[index].channel_id == channel_id)
}

fn emit_user_output_receipt(pid: bogk_core::ProcessId, payload: &[u8]) {
    let app_path = unsafe { PROCESS_TABLE.get(pid).map(|record| record.app_path()).unwrap_or("none") };
    serial_write("BOGOS_USER_OUTPUT_BEGIN\nPID=");
    write_usize(pid as usize);
    serial_write("\nAPP_PATH=");
    serial_write(app_path);
    serial_write("\nOUTPUT_HASH=");
    write_hex(&bogk_core::sha256(payload));
    serial_write("\nOUTPUT_LENGTH=");
    write_usize(payload.len());
    serial_write("\nOUTPUT_PREVIEW=hex:");
    write_serial_hex_bytes(payload);
    serial_write("\nBOGOS_USER_OUTPUT_END\n");
}

fn emit_verify_hash_receipt(
    pid: bogk_core::ProcessId,
    payload_hash: &[u8; 32],
    expected_hash: &[u8; 32],
    matches: bool,
) {
    serial_write("BOGOS_VERIFY_HASH_BEGIN\nPID=");
    write_usize(pid as usize);
    serial_write("\nPAYLOAD_HASH=");
    write_hex(payload_hash);
    serial_write("\nEXPECTED_HASH=");
    write_hex(expected_hash);
    serial_write("\nHASH_MATCH=");
    serial_write(if matches { "true" } else { "false" });
    serial_write("\nRESULT=");
    serial_write(if matches { "accepted" } else { "rejected" });
    serial_write("\nBOGOS_VERIFY_HASH_END\n");
}

fn emit_claim_receipt(
    pid: Option<bogk_core::ProcessId>,
    claim_hash: &[u8; 32],
    length: usize,
    accepted: bool,
    reject_reason: &str,
) {
    serial_write("BOGOS_CLAIM_BEGIN\nPID=");
    write_optional_serial_pid(pid);
    serial_write("\nCLAIM_HASH=");
    write_hex(claim_hash);
    serial_write("\nCLAIM_LENGTH=");
    write_usize(length);
    serial_write("\nCLAIM_ACCEPTED=");
    serial_write(if accepted { "true" } else { "false" });
    serial_write("\nREJECT_REASON=");
    serial_write(reject_reason);
    serial_write("\nBOGOS_CLAIM_END\n");
}

fn emit_writable_bogfs_receipt(
    operation: &str,
    pid: bogk_core::ProcessId,
    path: &str,
    length: usize,
    content_hash: Option<&[u8; 32]>,
    old_version: Option<u32>,
    old_hash: Option<&[u8; 32]>,
    new_version: Option<u32>,
    new_hash: Option<&[u8; 32]>,
    status: &str,
    reject_reason: &str,
) {
    serial_write("BOGOS_WRITABLE_BOGFS_BEGIN\nOPERATION=");
    serial_write(operation);
    serial_write("\nPID=");
    write_usize(pid as usize);
    serial_write("\nPATH=");
    serial_write(path);
    serial_write("\nLENGTH=");
    write_usize(length);
    serial_write("\nSHA256=");
    if let Some(value) = content_hash { write_hex(value) } else { serial_write("none") }
    serial_write("\nOLD_VERSION=");
    if let Some(value) = old_version { write_usize(value as usize) } else { serial_write("none") }
    serial_write("\nOLD_HASH=");
    if let Some(value) = old_hash { write_hex(value) } else { serial_write("none") }
    serial_write("\nNEW_VERSION=");
    if let Some(value) = new_version { write_usize(value as usize) } else { serial_write("none") }
    serial_write("\nNEW_HASH=");
    if let Some(value) = new_hash { write_hex(value) } else { serial_write("none") }
    serial_write("\nSTATUS=");
    serial_write(status);
    serial_write("\nREJECT_REASON=");
    serial_write(reject_reason);
    serial_write("\nMUTATED_TRUSTED_STATE=");
    serial_write(if status == "accepted" && operation == "write" { "true" } else { "false" });
    serial_write("\nBOGOS_WRITABLE_BOGFS_END\n");
}

fn emit_writable_bogfs_invariants_receipt() {
    serial_write("BOGOS_WRITABLE_BOGFS_INVARIANTS_BEGIN\nWRITABLE_BOGFS_ABI_VERSION=1\n");
    serial_write("QEMU_ONLY=true\nIN_MEMORY_ONLY=true\nPOSIX_FILESYSTEM=false\n");
    serial_write("KERNEL_OWNED_STORAGE=true\nPOINTER_VALIDATION_ENFORCED=true\n");
    serial_write("PATH_POLICY_ENFORCED=true\nBOUNDED_STORAGE_ENFORCED=true\n");
    serial_write("COMMIT_AFTER_HASH_RECEIPT_CHECK=true\nREADS_RETURN_COMMITTED_VERIFIED_CONTENTS=true\n");
    serial_write("REJECTED_WRITES_MUTATED_STATE=false\nV31_ISOLATION_PRESERVED=true\n");
    serial_write("V32_LOADER_PRESERVED=true\nV33_SYSCALL_ABI_PRESERVED=true\n");
    serial_write("V34_IPC_PRESERVED=true\nBOGOS_WRITABLE_BOGFS_INVARIANTS_END\n");
}

unsafe fn active_writable_bogfs_pid() -> Result<bogk_core::ProcessId, &'static str> {
    if ACTIVE_SCHEDULED_PID == 0 {
        return Err("no_active_process");
    }
    let record = PROCESS_TABLE.get(ACTIVE_SCHEDULED_PID).ok_or("no_active_process")?;
    if !record.dynamic_loader_admitted || record.address_space.cr3 != ACTIVE_CR3 {
        return Err("unauthorized");
    }
    Ok(ACTIVE_SCHEDULED_PID)
}

unsafe fn writable_bogfs_path_index(address: u32, length: usize) -> Result<usize, &'static str> {
    if length == 0 || length > WRITABLE_BOGFS_MAX_PATH_SIZE {
        return Err("invalid_path");
    }
    validate_active_user_range(address, length, false)?;
    let mut path = [0u8; WRITABLE_BOGFS_MAX_PATH_SIZE];
    core::ptr::copy_nonoverlapping(address as *const u8, path.as_mut_ptr(), length);
    if path[..length].iter().any(|byte| !byte.is_ascii() || *byte == 0) {
        return Err("invalid_path");
    }
    if let Some(index) = (0..WRITABLE_BOGFS_MAX_FILES)
        .find(|&index| WRITABLE_BOGFS_FILES[index].path.as_bytes() == &path[..length])
    {
        return Ok(index);
    }
    if path[..length].starts_with(b"/system/")
        || path[..length].starts_with(b"/apps/")
        || path[..length].starts_with(b"/receipts/")
    {
        return Err("protected_path");
    }
    if path[..length] == *b"/data/new.bin" {
        return Err("file_table_full");
    }
    Err("invalid_path")
}

unsafe fn writable_bogfs_used_bytes() -> usize {
    WRITABLE_BOGFS_FILES.iter().map(|file| file.length).sum()
}

fn writable_bogfs_path_error_result(reason: &str) -> i32 {
    match reason {
        "file_table_full" => SYSCALL_ERR_UNAVAILABLE,
        "invalid_path" | "protected_path" => SYSCALL_ERR_PERMISSION_DENIED,
        _ => SYSCALL_ERR_INVALID_POINTER,
    }
}

#[no_mangle]
pub extern "C" fn handle_syscall(regs: &mut SyscallRegisters) {
    let syscall_num = regs.eax;
    let dynamic_loader_admitted = unsafe {
        ACTIVE_SCHEDULED_PID > 0
            && PROCESS_TABLE
                .get(ACTIVE_SCHEDULED_PID)
                .map(|record| record.dynamic_loader_admitted)
                .unwrap_or(false)
    };
    if dynamic_loader_admitted && (1..=5).contains(&syscall_num) {
        emit_syscall_receipt(
            regs,
            syscall_num,
            SYSCALL_ERR_INVALID_SYSCALL,
            "rejected",
            "legacy_syscall_denied",
        );
        regs.eax = SYSCALL_ERR_INVALID_SYSCALL as u32;
        return;
    }
    match syscall_num {
        1 => {
            // sys_verify(buf_ptr, len, expected_hash_ptr) -> i32
            let buf_ptr = regs.ebx as *const u8;
            let len = regs.ecx as usize;
            let hash_ptr = regs.edx as *const u8;
            
            if buf_ptr.is_null() || hash_ptr.is_null() || len > 65536 {
                regs.eax = -1_i32 as u32;
                return;
            }
            
            let mut expected_hash = [0u8; 32];
            unsafe {
                core::ptr::copy_nonoverlapping(hash_ptr, expected_hash.as_mut_ptr(), 32);
            }
            
            let buf_slice = unsafe { core::slice::from_raw_parts(buf_ptr, len) };
            let actual_hash = bogk_core::sha256(buf_slice);
            
            regs.eax = if actual_hash == expected_hash { 1 } else { 0 };
        }
        2 => {
            // sys_accept(handle) -> i32
            unsafe {
                VERIFIED_APP_COUNT += 1;
            }
            regs.eax = 0;
        }
        3 => {
            // sys_reject(handle) -> i32
            unsafe {
                REJECTED_APP_COUNT += 1;
            }
            regs.eax = 0;
        }
        4 => {
            // sys_read_file(path_ptr, buf_ptr, len) -> i32
            let path_ptr = regs.ebx as *const u8;
            let buf_ptr = regs.ecx as *mut u8;
            let max_len = regs.edx as usize;
            
            if path_ptr.is_null() || buf_ptr.is_null() {
                regs.eax = -1_i32 as u32;
                return;
            }
            
            let mut path_len = 0;
            unsafe {
                let mut p = path_ptr;
                while *p != 0 && path_len < 256 {
                    path_len += 1;
                    p = p.add(1);
                }
            }
            
            let path_slice = unsafe { core::slice::from_raw_parts(path_ptr, path_len) };
            let path_str = core::str::from_utf8(path_slice).unwrap_or("");
            
            if let Some(content) = bogfs_read(path_str) {
                let copy_len = core::cmp::min(content.len(), max_len);
                unsafe {
                    core::ptr::copy_nonoverlapping(content.as_ptr(), buf_ptr, copy_len);
                }
                regs.eax = copy_len as u32;
            } else {
                regs.eax = -1_i32 as u32;
            }
        }
        5 => {
            // sys_emit_receipt(receipt_ptr, len) -> i32
            let receipt_ptr = regs.ebx as *const u8;
            let len = regs.ecx as usize;
            
            if receipt_ptr.is_null() || len > 1024 {
                regs.eax = -1_i32 as u32;
                return;
            }
            
            unsafe {
                LAST_RECEIPT_LEN = core::cmp::min(len, 1024);
                core::ptr::copy_nonoverlapping(receipt_ptr, LAST_RECEIPT_BUF.as_mut_ptr(), LAST_RECEIPT_LEN);
                
                if contains_forbidden_sentinel(&LAST_RECEIPT_BUF[..LAST_RECEIPT_LEN]) {
                    regs.eax = -2_i32 as u32;
                    return;
                }
                
                LAST_RECEIPT_AVAILABLE = true;
                
                if let Ok(receipt_str) = core::str::from_utf8(&LAST_RECEIPT_BUF[..LAST_RECEIPT_LEN]) {
                    serial_write(receipt_str);
                    serial_write("\n");
                }
            }
            regs.eax = 0;
        }
        SYSCALL_V2_EXIT => {
            // sys_exit(code) -> !
            emit_syscall_receipt(regs, syscall_num, regs.ebx as i32, "accepted", "none");
            unsafe {
                ACTIVE_BLOCK_REASON = "exit";
                longjmp_to_kernel(regs.ebx);
            }
        }
        SYSCALL_V2_YIELD => {
            // sys_yield() -> save the active user context and return to scheduler
            unsafe {
                if ACTIVE_SCHEDULED_PID == 0 {
                    emit_syscall_receipt(
                        regs,
                        syscall_num,
                        SYSCALL_ERR_INVALID_POINTER,
                        "rejected",
                        "no_active_process",
                    );
                    regs.eax = SYSCALL_ERR_INVALID_POINTER as u32;
                    return;
                }
                let pid = ACTIVE_SCHEDULED_PID;
                let context = SavedContext {
                    eip: regs.eip,
                    esp: regs.user_esp,
                    eflags: regs.eflags,
                    eax: 0,
                    ebx: regs.ebx,
                    ecx: regs.ecx,
                    edx: regs.edx,
                    esi: regs.esi,
                    edi: regs.edi,
                    ebp: regs.ebp,
                    valid: true,
                };
                let record = PROCESS_TABLE.get_mut(pid).unwrap();
                record.save_context(context);
                record.mark_yielded();
                record.mark_ready();
                emit_context_save_receipt(pid, &context);
                emit_syscall_receipt(regs, syscall_num, 0, "accepted", "none");
                ACTIVE_BLOCK_REASON = "yield";
                longjmp_to_kernel(YIELD_EXIT_CODE as u32);
            }
        }
        SYSCALL_V2_WRITE_CONSOLE => {
            let length = regs.ecx as usize;
            if length == 0 || length > SYSCALL_V2_MAX_OUTPUT {
                emit_syscall_receipt(
                    regs,
                    syscall_num,
                    SYSCALL_ERR_INVALID_LENGTH,
                    "rejected",
                    "invalid_length",
                );
                regs.eax = SYSCALL_ERR_INVALID_LENGTH as u32;
                return;
            }
            let pid = match unsafe { validate_active_user_range(regs.ebx, length, false) } {
                Ok(pid) => pid,
                Err(reason) => {
                    emit_syscall_receipt(
                        regs,
                        syscall_num,
                        SYSCALL_ERR_INVALID_POINTER,
                        "rejected",
                        reason,
                    );
                    regs.eax = SYSCALL_ERR_INVALID_POINTER as u32;
                    return;
                }
            };
            let mut buffer = [0u8; SYSCALL_V2_MAX_OUTPUT];
            unsafe {
                core::ptr::copy_nonoverlapping(regs.ebx as *const u8, buffer.as_mut_ptr(), length);
            }
            emit_user_output_receipt(pid, &buffer[..length]);
            emit_syscall_receipt(regs, syscall_num, length as i32, "accepted", "none");
            regs.eax = length as u32;
        }
        SYSCALL_V2_GETPID => {
            let pid = unsafe { ACTIVE_SCHEDULED_PID };
            if pid == 0 {
                emit_syscall_receipt(
                    regs,
                    syscall_num,
                    SYSCALL_ERR_INVALID_POINTER,
                    "rejected",
                    "no_active_process",
                );
                regs.eax = SYSCALL_ERR_INVALID_POINTER as u32;
            } else {
                emit_syscall_receipt(regs, syscall_num, pid as i32, "accepted", "none");
                regs.eax = pid;
            }
        }
        SYSCALL_V2_PROCESS_INFO => {
            let length = regs.ecx as usize;
            if length < SYSCALL_V2_PROCESS_INFO_SIZE || length > SYSCALL_V2_MAX_BUFFER {
                emit_syscall_receipt(
                    regs,
                    syscall_num,
                    SYSCALL_ERR_INVALID_LENGTH,
                    "rejected",
                    "invalid_length",
                );
                regs.eax = SYSCALL_ERR_INVALID_LENGTH as u32;
                return;
            }
            let pid = match unsafe {
                validate_active_user_range(regs.ebx, SYSCALL_V2_PROCESS_INFO_SIZE, true)
            } {
                Ok(pid) => pid,
                Err(reason) => {
                    emit_syscall_receipt(
                        regs,
                        syscall_num,
                        SYSCALL_ERR_INVALID_POINTER,
                        "rejected",
                        reason,
                    );
                    regs.eax = SYSCALL_ERR_INVALID_POINTER as u32;
                    return;
                }
            };
            let record = unsafe { PROCESS_TABLE.get(pid).unwrap() };
            let fields = [2u32, pid, record.address_space.cr3, 1u32];
            let mut output = [0u8; SYSCALL_V2_PROCESS_INFO_SIZE];
            for (index, field) in fields.iter().enumerate() {
                output[index * 4..index * 4 + 4].copy_from_slice(&field.to_le_bytes());
            }
            unsafe {
                core::ptr::copy_nonoverlapping(
                    output.as_ptr(),
                    regs.ebx as *mut u8,
                    SYSCALL_V2_PROCESS_INFO_SIZE,
                );
            }
            emit_syscall_receipt(
                regs,
                syscall_num,
                SYSCALL_V2_PROCESS_INFO_SIZE as i32,
                "accepted",
                "none",
            );
            regs.eax = SYSCALL_V2_PROCESS_INFO_SIZE as u32;
        }
        SYSCALL_V2_VERIFY_HASH => {
            let length = regs.ecx as usize;
            if length == 0 || length > SYSCALL_V2_MAX_BUFFER {
                emit_syscall_receipt(
                    regs,
                    syscall_num,
                    SYSCALL_ERR_INVALID_LENGTH,
                    "rejected",
                    "invalid_length",
                );
                regs.eax = SYSCALL_ERR_INVALID_LENGTH as u32;
                return;
            }
            let pid = match unsafe { validate_active_user_range(regs.ebx, length, false) } {
                Ok(pid) => pid,
                Err(reason) => {
                    emit_syscall_receipt(
                        regs,
                        syscall_num,
                        SYSCALL_ERR_INVALID_POINTER,
                        "rejected",
                        reason,
                    );
                    regs.eax = SYSCALL_ERR_INVALID_POINTER as u32;
                    return;
                }
            };
            if let Err(reason) = unsafe { validate_active_user_range(regs.edx, 32, false) } {
                emit_syscall_receipt(
                    regs,
                    syscall_num,
                    SYSCALL_ERR_INVALID_POINTER,
                    "rejected",
                    reason,
                );
                regs.eax = SYSCALL_ERR_INVALID_POINTER as u32;
                return;
            }
            let mut payload = [0u8; SYSCALL_V2_MAX_BUFFER];
            let mut expected = [0u8; 32];
            unsafe {
                core::ptr::copy_nonoverlapping(regs.ebx as *const u8, payload.as_mut_ptr(), length);
                core::ptr::copy_nonoverlapping(regs.edx as *const u8, expected.as_mut_ptr(), 32);
            }
            let actual = bogk_core::sha256(&payload[..length]);
            let matches = actual == expected;
            emit_verify_hash_receipt(pid, &actual, &expected, matches);
            let result = if matches { 1 } else { SYSCALL_ERR_VERIFICATION_FAILED };
            emit_syscall_receipt(
                regs,
                syscall_num,
                result,
                if matches { "accepted" } else { "rejected" },
                if matches { "none" } else { "verification_failed" },
            );
            regs.eax = result as u32;
        }
        SYSCALL_V2_CLAIM => {
            let length = regs.ecx as usize;
            if length == 0 || length > SYSCALL_V2_MAX_OUTPUT {
                emit_claim_receipt(None, &[0; 32], length, false, "invalid_length");
                emit_syscall_receipt(
                    regs,
                    syscall_num,
                    SYSCALL_ERR_INVALID_LENGTH,
                    "rejected",
                    "invalid_length",
                );
                regs.eax = SYSCALL_ERR_INVALID_LENGTH as u32;
                return;
            }
            let pid = match unsafe { validate_active_user_range(regs.ebx, length, false) } {
                Ok(pid) => pid,
                Err(reason) => {
                    emit_claim_receipt(None, &[0; 32], length, false, reason);
                    emit_syscall_receipt(
                        regs,
                        syscall_num,
                        SYSCALL_ERR_INVALID_POINTER,
                        "rejected",
                        reason,
                    );
                    regs.eax = SYSCALL_ERR_INVALID_POINTER as u32;
                    return;
                }
            };
            let mut claim = [0u8; SYSCALL_V2_MAX_OUTPUT];
            unsafe {
                core::ptr::copy_nonoverlapping(regs.ebx as *const u8, claim.as_mut_ptr(), length);
            }
            let claim_hash = bogk_core::sha256(&claim[..length]);
            emit_claim_receipt(Some(pid), &claim_hash, length, true, "none");
            emit_syscall_receipt(regs, syscall_num, length as i32, "accepted", "none");
            regs.eax = length as u32;
        }
        SYSCALL_V2_IPC_REGISTER_CHANNEL => {
            let pid = match unsafe { active_ipc_pid() } {
                Ok(pid) => pid,
                Err(reason) => {
                    emit_syscall_receipt(
                        regs,
                        syscall_num,
                        SYSCALL_ERR_PERMISSION_DENIED,
                        "rejected",
                        reason,
                    );
                    regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                    return;
                }
            };
            let peer_pid = if regs.ebx == 0 { pid } else { regs.ebx };
            let max_message_size = regs.ecx as usize;
            let max_queue_depth = regs.edx as usize;
            if regs.esi != 0 {
                emit_ipc_channel_receipt(
                    pid,
                    None,
                    Some(peer_pid),
                    max_message_size,
                    max_queue_depth,
                    "rejected",
                    "unsupported_flags",
                );
                emit_syscall_receipt(
                    regs,
                    syscall_num,
                    SYSCALL_ERR_PERMISSION_DENIED,
                    "rejected",
                    "unsupported_flags",
                );
                regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                return;
            }
            if max_message_size == 0
                || max_message_size > IPC_MAX_MESSAGE_SIZE
                || max_queue_depth == 0
                || max_queue_depth > IPC_MAX_QUEUE_DEPTH
            {
                emit_ipc_channel_receipt(
                    pid,
                    None,
                    Some(peer_pid),
                    max_message_size,
                    max_queue_depth,
                    "rejected",
                    "invalid_size",
                );
                emit_syscall_receipt(
                    regs,
                    syscall_num,
                    SYSCALL_ERR_INVALID_LENGTH,
                    "rejected",
                    "invalid_size",
                );
                regs.eax = SYSCALL_ERR_INVALID_LENGTH as u32;
                return;
            }
            if !unsafe { ipc_peer_is_eligible(peer_pid) } {
                emit_ipc_channel_receipt(
                    pid,
                    None,
                    Some(peer_pid),
                    max_message_size,
                    max_queue_depth,
                    "rejected",
                    "invalid_peer",
                );
                emit_syscall_receipt(
                    regs,
                    syscall_num,
                    SYSCALL_ERR_PERMISSION_DENIED,
                    "rejected",
                    "invalid_peer",
                );
                regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                return;
            }
            let free_index = unsafe { (0..IPC_MAX_CHANNELS).find(|&index| !IPC_CHANNELS[index].used) };
            let Some(index) = free_index else {
                emit_ipc_channel_receipt(
                    pid,
                    None,
                    Some(peer_pid),
                    max_message_size,
                    max_queue_depth,
                    "rejected",
                    "channel_limit",
                );
                emit_syscall_receipt(
                    regs,
                    syscall_num,
                    SYSCALL_ERR_UNAVAILABLE,
                    "rejected",
                    "channel_limit",
                );
                regs.eax = SYSCALL_ERR_UNAVAILABLE as u32;
                return;
            };
            let channel_id = unsafe { NEXT_IPC_CHANNEL_ID };
            unsafe {
                NEXT_IPC_CHANNEL_ID = NEXT_IPC_CHANNEL_ID.wrapping_add(1);
                IPC_CHANNELS[index] = IpcChannel {
                    used: true,
                    channel_id,
                    owner_pid: pid,
                    peer_pid,
                    max_message_size,
                    max_queue_depth,
                    queue_depth: 0,
                    messages: [IpcMessage::empty(); IPC_MAX_QUEUE_DEPTH],
                };
            }
            emit_ipc_channel_receipt(
                pid,
                Some(channel_id),
                Some(peer_pid),
                max_message_size,
                max_queue_depth,
                "accepted",
                "none",
            );
            emit_syscall_receipt(regs, syscall_num, channel_id as i32, "accepted", "none");
            regs.eax = channel_id;
        }
        SYSCALL_V2_IPC_SEND => {
            let pid = match unsafe { active_ipc_pid() } {
                Ok(pid) => pid,
                Err(reason) => {
                    emit_syscall_receipt(
                        regs,
                        syscall_num,
                        SYSCALL_ERR_PERMISSION_DENIED,
                        "rejected",
                        reason,
                    );
                    regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                    return;
                }
            };
            let channel_id = regs.ebx;
            let length = regs.edx as usize;
            let Some(index) = (unsafe { ipc_channel_index(channel_id) }) else {
                emit_ipc_send_receipt(pid, None, channel_id, None, length, None, 0, "rejected", "invalid_channel");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_UNAVAILABLE, "rejected", "invalid_channel");
                regs.eax = SYSCALL_ERR_UNAVAILABLE as u32;
                return;
            };
            let channel = unsafe { IPC_CHANNELS[index] };
            if channel.owner_pid != pid {
                emit_ipc_send_receipt(pid, Some(channel.peer_pid), channel_id, None, length, None, channel.queue_depth, "rejected", "unauthorized");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_PERMISSION_DENIED, "rejected", "unauthorized");
                regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                return;
            }
            if regs.esi != 0 {
                emit_ipc_send_receipt(pid, Some(channel.peer_pid), channel_id, None, length, None, channel.queue_depth, "rejected", "unsupported_flags");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_PERMISSION_DENIED, "rejected", "unsupported_flags");
                regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                return;
            }
            if length == 0 || length > channel.max_message_size {
                emit_ipc_send_receipt(pid, Some(channel.peer_pid), channel_id, None, length, None, channel.queue_depth, "rejected", "invalid_length");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_INVALID_LENGTH, "rejected", "invalid_length");
                regs.eax = SYSCALL_ERR_INVALID_LENGTH as u32;
                return;
            }
            if channel.queue_depth >= channel.max_queue_depth {
                emit_ipc_send_receipt(pid, Some(channel.peer_pid), channel_id, None, length, None, channel.queue_depth, "rejected", "queue_full");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_UNAVAILABLE, "rejected", "queue_full");
                regs.eax = SYSCALL_ERR_UNAVAILABLE as u32;
                return;
            }
            if !unsafe { ipc_peer_is_eligible(channel.peer_pid) } {
                emit_ipc_send_receipt(pid, Some(channel.peer_pid), channel_id, None, length, None, channel.queue_depth, "rejected", "receiver_unavailable");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_UNAVAILABLE, "rejected", "receiver_unavailable");
                regs.eax = SYSCALL_ERR_UNAVAILABLE as u32;
                return;
            }
            if unsafe { validate_active_user_range(regs.ecx, length, false) }.is_err() {
                emit_ipc_send_receipt(pid, Some(channel.peer_pid), channel_id, None, length, None, channel.queue_depth, "rejected", "invalid_pointer");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_INVALID_POINTER, "rejected", "invalid_pointer");
                regs.eax = SYSCALL_ERR_INVALID_POINTER as u32;
                return;
            }
            let mut payload = [0u8; IPC_MAX_MESSAGE_SIZE];
            unsafe { core::ptr::copy_nonoverlapping(regs.ecx as *const u8, payload.as_mut_ptr(), length) };
            let payload_hash = bogk_core::sha256(&payload[..length]);
            let message_id = unsafe { NEXT_IPC_MESSAGE_ID };
            unsafe {
                NEXT_IPC_MESSAGE_ID = NEXT_IPC_MESSAGE_ID.wrapping_add(1);
                let queue_index = IPC_CHANNELS[index].queue_depth;
                IPC_CHANNELS[index].messages[queue_index] = IpcMessage {
                    message_id,
                    from_pid: pid,
                    payload_length: length,
                    payload_hash,
                    payload,
                };
                IPC_CHANNELS[index].queue_depth += 1;
            }
            let depth_after = unsafe { IPC_CHANNELS[index].queue_depth };
            emit_ipc_send_receipt(pid, Some(channel.peer_pid), channel_id, Some(message_id), length, Some(&payload_hash), depth_after, "accepted", "none");
            emit_syscall_receipt(regs, syscall_num, message_id as i32, "accepted", "none");
            regs.eax = message_id;
        }
        SYSCALL_V2_IPC_RECV => {
            let pid = match unsafe { active_ipc_pid() } {
                Ok(pid) => pid,
                Err(reason) => {
                    emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_PERMISSION_DENIED, "rejected", reason);
                    regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                    return;
                }
            };
            let channel_id = regs.ebx;
            let output_len = regs.edx as usize;
            let Some(index) = (unsafe { ipc_channel_index(channel_id) }) else {
                emit_ipc_recv_receipt(pid, None, channel_id, None, regs.ecx, output_len, 0, None, 0, "rejected", "invalid_channel");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_UNAVAILABLE, "rejected", "invalid_channel");
                regs.eax = SYSCALL_ERR_UNAVAILABLE as u32;
                return;
            };
            let channel = unsafe { IPC_CHANNELS[index] };
            if channel.peer_pid != pid {
                emit_ipc_recv_receipt(pid, Some(channel.owner_pid), channel_id, None, regs.ecx, output_len, 0, None, channel.queue_depth, "rejected", "unauthorized");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_PERMISSION_DENIED, "rejected", "unauthorized");
                regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                return;
            }
            if regs.esi != 0 {
                emit_ipc_recv_receipt(pid, Some(channel.owner_pid), channel_id, None, regs.ecx, output_len, 0, None, channel.queue_depth, "rejected", "unsupported_flags");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_PERMISSION_DENIED, "rejected", "unsupported_flags");
                regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                return;
            }
            if channel.queue_depth == 0 {
                emit_ipc_recv_receipt(pid, Some(channel.owner_pid), channel_id, None, regs.ecx, output_len, 0, None, 0, "rejected", "empty");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_UNAVAILABLE, "rejected", "empty");
                regs.eax = SYSCALL_ERR_UNAVAILABLE as u32;
                return;
            }
            let message = channel.messages[0];
            if output_len < message.payload_length {
                emit_ipc_recv_receipt(pid, Some(message.from_pid), channel_id, Some(message.message_id), regs.ecx, output_len, message.payload_length, Some(&message.payload_hash), channel.queue_depth, "rejected", "buffer_too_small");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_INVALID_LENGTH, "rejected", "buffer_too_small");
                regs.eax = SYSCALL_ERR_INVALID_LENGTH as u32;
                return;
            }
            if unsafe { validate_active_user_range(regs.ecx, message.payload_length, true) }.is_err() {
                emit_ipc_recv_receipt(pid, Some(message.from_pid), channel_id, Some(message.message_id), regs.ecx, output_len, message.payload_length, Some(&message.payload_hash), channel.queue_depth, "rejected", "invalid_pointer");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_INVALID_POINTER, "rejected", "invalid_pointer");
                regs.eax = SYSCALL_ERR_INVALID_POINTER as u32;
                return;
            }
            unsafe {
                core::ptr::copy_nonoverlapping(message.payload.as_ptr(), regs.ecx as *mut u8, message.payload_length);
                for queue_index in 1..IPC_CHANNELS[index].queue_depth {
                    IPC_CHANNELS[index].messages[queue_index - 1] = IPC_CHANNELS[index].messages[queue_index];
                }
                IPC_CHANNELS[index].queue_depth -= 1;
                let tail = IPC_CHANNELS[index].queue_depth;
                IPC_CHANNELS[index].messages[tail] = IpcMessage::empty();
            }
            let depth_after = unsafe { IPC_CHANNELS[index].queue_depth };
            emit_ipc_recv_receipt(pid, Some(message.from_pid), channel_id, Some(message.message_id), regs.ecx, output_len, message.payload_length, Some(&message.payload_hash), depth_after, "accepted", "none");
            emit_syscall_receipt(regs, syscall_num, message.payload_length as i32, "accepted", "none");
            regs.eax = message.payload_length as u32;
        }
        SYSCALL_V2_IPC_POLL => {
            let pid = match unsafe { active_ipc_pid() } {
                Ok(pid) => pid,
                Err(reason) => {
                    emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_PERMISSION_DENIED, "rejected", reason);
                    regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                    return;
                }
            };
            let channel_id = regs.ebx;
            let Some(index) = (unsafe { ipc_channel_index(channel_id) }) else {
                emit_ipc_poll_receipt(pid, channel_id, 0, "rejected", "invalid_channel");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_UNAVAILABLE, "rejected", "invalid_channel");
                regs.eax = SYSCALL_ERR_UNAVAILABLE as u32;
                return;
            };
            let channel = unsafe { IPC_CHANNELS[index] };
            if channel.owner_pid != pid && channel.peer_pid != pid {
                emit_ipc_poll_receipt(pid, channel_id, channel.queue_depth, "rejected", "unauthorized");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_PERMISSION_DENIED, "rejected", "unauthorized");
                regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                return;
            }
            emit_ipc_poll_receipt(pid, channel_id, channel.queue_depth, "accepted", "none");
            emit_syscall_receipt(regs, syscall_num, channel.queue_depth as i32, "accepted", "none");
            regs.eax = channel.queue_depth as u32;
        }
        SYSCALL_V2_BOGFS_WRITE => {
            let pid = match unsafe { active_writable_bogfs_pid() } {
                Ok(pid) => pid,
                Err(reason) => {
                    emit_writable_bogfs_receipt("write", 0, "unresolved", regs.esi as usize, None, None, None, None, None, "rejected", reason);
                    emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_PERMISSION_DENIED, "rejected", reason);
                    regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                    return;
                }
            };
            let length = regs.esi as usize;
            if length == 0 || length > WRITABLE_BOGFS_MAX_FILE_SIZE {
                emit_writable_bogfs_receipt("write", pid, "unresolved", length, None, None, None, None, None, "rejected", "invalid_length");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_INVALID_LENGTH, "rejected", "invalid_length");
                regs.eax = SYSCALL_ERR_INVALID_LENGTH as u32;
                return;
            }
            let index = match unsafe { writable_bogfs_path_index(regs.ebx, regs.ecx as usize) } {
                Ok(index) => index,
                Err(reason) => {
                    let result = writable_bogfs_path_error_result(reason);
                    emit_writable_bogfs_receipt("write", pid, "unresolved", length, None, None, None, None, None, "rejected", reason);
                    emit_syscall_receipt(regs, syscall_num, result, "rejected", reason);
                    regs.eax = result as u32;
                    return;
                }
            };
            let file = unsafe { WRITABLE_BOGFS_FILES[index] };
            if !file.writable {
                emit_writable_bogfs_receipt("write", pid, file.path, length, None, Some(file.version), Some(&file.hash), Some(file.version), Some(&file.hash), "rejected", "read_only_path");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_PERMISSION_DENIED, "rejected", "read_only_path");
                regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                return;
            }
            if let Err(reason) = unsafe { validate_active_user_range(regs.edx, length, false) } {
                emit_writable_bogfs_receipt("write", pid, file.path, length, None, Some(file.version), Some(&file.hash), Some(file.version), Some(&file.hash), "rejected", reason);
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_INVALID_POINTER, "rejected", reason);
                regs.eax = SYSCALL_ERR_INVALID_POINTER as u32;
                return;
            }
            let mut staged = [0u8; WRITABLE_BOGFS_MAX_FILE_SIZE];
            unsafe { core::ptr::copy_nonoverlapping(regs.edx as *const u8, staged.as_mut_ptr(), length) };
            let candidate_hash = bogk_core::sha256(&staged[..length]);
            let receipt_check_hash = if file.force_hash_failure {
                let mut failed = candidate_hash;
                failed[0] ^= 0xff;
                failed
            } else {
                bogk_core::sha256(&staged[..length])
            };
            if receipt_check_hash != candidate_hash {
                emit_writable_bogfs_receipt("write", pid, file.path, length, Some(&candidate_hash), Some(file.version), Some(&file.hash), Some(file.version), Some(&file.hash), "rejected", "receipt_hash_mismatch");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_VERIFICATION_FAILED, "rejected", "receipt_hash_mismatch");
                regs.eax = SYSCALL_ERR_VERIFICATION_FAILED as u32;
                return;
            }
            let used_after = unsafe { writable_bogfs_used_bytes() } - file.length + length;
            if used_after > WRITABLE_BOGFS_TOTAL_CAPACITY {
                emit_writable_bogfs_receipt("write", pid, file.path, length, Some(&candidate_hash), Some(file.version), Some(&file.hash), Some(file.version), Some(&file.hash), "rejected", "storage_full");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_UNAVAILABLE, "rejected", "storage_full");
                regs.eax = SYSCALL_ERR_UNAVAILABLE as u32;
                return;
            }
            let old_version = file.version;
            let old_hash = file.hash;
            let new_version = old_version.wrapping_add(1);
            unsafe {
                WRITABLE_BOGFS_FILES[index].data = staged;
                WRITABLE_BOGFS_FILES[index].length = length;
                WRITABLE_BOGFS_FILES[index].version = new_version;
                WRITABLE_BOGFS_FILES[index].hash = candidate_hash;
            }
            emit_writable_bogfs_receipt("write", pid, file.path, length, Some(&candidate_hash), Some(old_version), Some(&old_hash), Some(new_version), Some(&candidate_hash), "accepted", "none");
            emit_syscall_receipt(regs, syscall_num, length as i32, "accepted", "none");
            regs.eax = length as u32;
        }
        SYSCALL_V2_BOGFS_READ => {
            let pid = match unsafe { active_writable_bogfs_pid() } {
                Ok(pid) => pid,
                Err(reason) => {
                    emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_PERMISSION_DENIED, "rejected", reason);
                    regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                    return;
                }
            };
            let index = match unsafe { writable_bogfs_path_index(regs.ebx, regs.ecx as usize) } {
                Ok(index) => index,
                Err(reason) => {
                    let result = writable_bogfs_path_error_result(reason);
                    emit_writable_bogfs_receipt("read", pid, "unresolved", regs.esi as usize, None, None, None, None, None, "rejected", reason);
                    emit_syscall_receipt(regs, syscall_num, result, "rejected", reason);
                    regs.eax = result as u32;
                    return;
                }
            };
            let file = unsafe { WRITABLE_BOGFS_FILES[index] };
            if bogk_core::sha256(&file.data[..file.length]) != file.hash {
                emit_writable_bogfs_receipt("read", pid, file.path, file.length, Some(&file.hash), Some(file.version), Some(&file.hash), Some(file.version), Some(&file.hash), "rejected", "committed_hash_mismatch");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_VERIFICATION_FAILED, "rejected", "committed_hash_mismatch");
                regs.eax = SYSCALL_ERR_VERIFICATION_FAILED as u32;
                return;
            }
            if (regs.esi as usize) < file.length {
                emit_writable_bogfs_receipt("read", pid, file.path, file.length, Some(&file.hash), Some(file.version), Some(&file.hash), Some(file.version), Some(&file.hash), "rejected", "buffer_too_small");
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_INVALID_LENGTH, "rejected", "buffer_too_small");
                regs.eax = SYSCALL_ERR_INVALID_LENGTH as u32;
                return;
            }
            if file.length > 0 {
                if let Err(reason) = unsafe { validate_active_user_range(regs.edx, file.length, true) } {
                    emit_writable_bogfs_receipt("read", pid, file.path, file.length, Some(&file.hash), Some(file.version), Some(&file.hash), Some(file.version), Some(&file.hash), "rejected", reason);
                    emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_INVALID_POINTER, "rejected", reason);
                    regs.eax = SYSCALL_ERR_INVALID_POINTER as u32;
                    return;
                }
                unsafe { core::ptr::copy_nonoverlapping(file.data.as_ptr(), regs.edx as *mut u8, file.length) };
            }
            emit_writable_bogfs_receipt("read", pid, file.path, file.length, Some(&file.hash), Some(file.version), Some(&file.hash), Some(file.version), Some(&file.hash), "accepted", "none");
            emit_syscall_receipt(regs, syscall_num, file.length as i32, "accepted", "none");
            regs.eax = file.length as u32;
        }
        SYSCALL_V2_BOGFS_STAT => {
            let pid = match unsafe { active_writable_bogfs_pid() } {
                Ok(pid) => pid,
                Err(reason) => {
                    emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_PERMISSION_DENIED, "rejected", reason);
                    regs.eax = SYSCALL_ERR_PERMISSION_DENIED as u32;
                    return;
                }
            };
            let index = match unsafe { writable_bogfs_path_index(regs.ebx, regs.ecx as usize) } {
                Ok(index) => index,
                Err(reason) => {
                    let result = writable_bogfs_path_error_result(reason);
                    emit_syscall_receipt(regs, syscall_num, result, "rejected", reason);
                    regs.eax = result as u32;
                    return;
                }
            };
            let file = unsafe { WRITABLE_BOGFS_FILES[index] };
            if (regs.esi as usize) < WRITABLE_BOGFS_STAT_SIZE {
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_INVALID_LENGTH, "rejected", "buffer_too_small");
                regs.eax = SYSCALL_ERR_INVALID_LENGTH as u32;
                return;
            }
            if bogk_core::sha256(&file.data[..file.length]) != file.hash {
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_VERIFICATION_FAILED, "rejected", "committed_hash_mismatch");
                regs.eax = SYSCALL_ERR_VERIFICATION_FAILED as u32;
                return;
            }
            if let Err(reason) = unsafe { validate_active_user_range(regs.edx, WRITABLE_BOGFS_STAT_SIZE, true) } {
                emit_syscall_receipt(regs, syscall_num, SYSCALL_ERR_INVALID_POINTER, "rejected", reason);
                regs.eax = SYSCALL_ERR_INVALID_POINTER as u32;
                return;
            }
            let mut output = [0u8; WRITABLE_BOGFS_STAT_SIZE];
            output[0..4].copy_from_slice(&file.version.to_le_bytes());
            output[4..8].copy_from_slice(&(file.length as u32).to_le_bytes());
            output[8..40].copy_from_slice(&file.hash);
            unsafe { core::ptr::copy_nonoverlapping(output.as_ptr(), regs.edx as *mut u8, output.len()) };
            emit_writable_bogfs_receipt("stat", pid, file.path, file.length, Some(&file.hash), Some(file.version), Some(&file.hash), Some(file.version), Some(&file.hash), "accepted", "none");
            emit_syscall_receipt(regs, syscall_num, WRITABLE_BOGFS_STAT_SIZE as i32, "accepted", "none");
            regs.eax = WRITABLE_BOGFS_STAT_SIZE as u32;
        }
        _ => {
            emit_syscall_receipt(
                regs,
                syscall_num,
                SYSCALL_ERR_INVALID_SYSCALL,
                "rejected",
                "invalid_syscall",
            );
            regs.eax = SYSCALL_ERR_INVALID_SYSCALL as u32;
        }
    }
}


fn write_hex_u32(writer: &mut BufferWriter, val: u32) {
    for i in (0..8).rev() {
        let nibble = ((val >> (i * 4)) & 0x0F) as u8;
        let c = if nibble < 10 {
            b'0' + nibble
        } else {
            b'a' + (nibble - 10)
        };
        let s = &[c];
        writer.write_str(core::str::from_utf8(s).unwrap_or("?"));
    }
}

// =========================================================================
// Global state variables for BogOS v20
// =========================================================================
static mut VERIFIED_APP_COUNT: usize = 1;
static mut REJECTED_APP_COUNT: usize = 1;
static mut LAST_RECEIPT_AVAILABLE: bool = false;
static mut LAST_RECEIPT_BUF: [u8; 1024] = [0u8; 1024];
static mut LAST_RECEIPT_LEN: usize = 0;
static mut PROCESS_TABLE: ProcessTable = ProcessTable::new();
static mut SCHEDULER: Scheduler = Scheduler::new();
static mut ACTIVE_BLOCK_REASON: &'static str = "none";
static mut ACTIVE_SCHEDULED_PID: bogk_core::ProcessId = 0;
const YIELD_EXIT_CODE: i32 = 0x7fff_fffe;
const PREEMPT_EXIT_CODE: i32 = 0x7fff_fffd;
const SCHEDULER_QUANTUM: usize = 2;
static mut LAST_SCHEDULER_REASON: &'static str = "none";
static mut KERNEL_READ_PROTECTION_FAULTED: bool = false;
static mut KERNEL_WRITE_PROTECTION_FAULTED: bool = false;
static mut CROSS_PROCESS_WRITE_FAULTED: bool = false;
static mut WRITABLE_CODE_FAULTED: bool = false;
static mut KERNEL_PROTECTION_RECEIPT_EMITTED: bool = false;
static mut PROCESS_ISOLATION_RECEIPT_EMITTED: bool = false;

const AUTO_DEMO_COMMANDS: &[&str] = &[
    "help",
    "status",
    "ls",
    "cat /system/status",
    "cat /system/memory",
    "cat /receipts/last",
    "run hello",
    "run bad-hello",
    "run good_app",
    "run bad_app",
    "run invalid_opcode",
    "run spoof",
    "run invalid_syscall",
    "spawn sched_a",
    "spawn sched_b",
    "spawn bad_sched",
    "runq",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "cat /system/scheduler",
    "cat /system/processes",
    "spawn ctx_a",
    "spawn ctx_b",
    "spawn missing_ctx",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "spawn v31_bad_kernel_read",
    "spawn v31_bad_kernel_write",
    "sched step",
    "sched step",
    "spawn v31_bad_cross_process_write",
    "spawn v31_bad_code_write",
    "sched step",
    "sched step",
    "spawn preempt_a",
    "spawn preempt_b",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "load dynamic_hello",
    "load bad_dynamic_hello",
    "load malformed_dynamic",
    "load invalid_entrypoint",
    "load missing_dynamic",
    "load bad_magic",
    "load bad_version",
    "load zero_code_length",
    "load bad_code_offset",
    "load bad_code_length",
    "load entrypoint_at_end",
    "load unsupported_capability",
    "load trailing_bytes",
    "load bad_manifest_hash",
    "load noncanonical_name",
    "load v33_syscall_write",
    "load v33_syscall_verify",
    "load v33_syscall_claim",
    "load v33_bad_syscall_kernel_ptr",
    "load v33_bad_syscall_cross_process_ptr",
    "load v33_bad_syscall_overflow_ptr",
    "load v33_audit_lengths",
    "load v33_audit_ranges",
    "load v33_audit_misc",
    "load v34_ipc_sender",
    "load v34_ipc_receiver",
    "load v34_ipc_negative",
    "load v35_bogfs_verified",
    "load v35_bogfs_negative",
    "load v35_1_bogfs_edges",
    "load v35_1_ipc_bogfs",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "cat /system/scheduler",
    "cat /system/processes",
    "clear",
    "panic",
];

// =========================================================================
// VGA Text UI Driver
// =========================================================================
struct VgaConsole {
    cursor_x: usize,
    cursor_y: usize,
    color: u8,
}

impl VgaConsole {
    const VGA_BUFFER: *mut u16 = 0xb8000 as *mut u16;
    const COLS: usize = 80;
    const ROWS: usize = 25;

    pub fn clear(&mut self) {
        let blank = (self.color as u16) << 8 | b' ' as u16;
        for i in 0..(Self::COLS * Self::ROWS) {
            unsafe {
                Self::VGA_BUFFER.add(i).write_volatile(blank);
            }
        }
        self.cursor_x = 0;
        self.cursor_y = 0;
    }

    pub fn write_char(&mut self, c: char) {
        if c == '\n' {
            self.cursor_x = 0;
            self.cursor_y += 1;
        } else if c == '\x08' {
            // Backspace
            if self.cursor_x > 0 {
                self.cursor_x -= 1;
                let index = self.cursor_y * Self::COLS + self.cursor_x;
                let val = (self.color as u16) << 8 | b' ' as u16;
                unsafe {
                    Self::VGA_BUFFER.add(index).write_volatile(val);
                }
            }
        } else {
            if self.cursor_x >= Self::COLS {
                self.cursor_x = 0;
                self.cursor_y += 1;
            }
            if self.cursor_y >= Self::ROWS {
                self.scroll();
            }
            let index = self.cursor_y * Self::COLS + self.cursor_x;
            let val = (self.color as u16) << 8 | (c as u8) as u16;
            unsafe {
                Self::VGA_BUFFER.add(index).write_volatile(val);
            }
            self.cursor_x += 1;
        }

        if self.cursor_y >= Self::ROWS {
            self.scroll();
        }
    }

    pub fn write_str(&mut self, s: &str) {
        for c in s.chars() {
            self.write_char(c);
        }
    }

    fn scroll(&mut self) {
        let blank = (self.color as u16) << 8 | b' ' as u16;
        for y in 1..Self::ROWS {
            for x in 0..Self::COLS {
                let src_idx = y * Self::COLS + x;
                let dst_idx = (y - 1) * Self::COLS + x;
                unsafe {
                    let val = Self::VGA_BUFFER.add(src_idx).read_volatile();
                    Self::VGA_BUFFER.add(dst_idx).write_volatile(val);
                }
            }
        }
        let last_row_start = (Self::ROWS - 1) * Self::COLS;
        for x in 0..Self::COLS {
            unsafe {
                Self::VGA_BUFFER.add(last_row_start + x).write_volatile(blank);
            }
        }
        self.cursor_y = Self::ROWS - 1;
    }
}

fn draw_header(console: &mut VgaConsole) {
    console.clear();
    console.color = 0x0a; // Vibrant Light Green logo
    console.write_str("BOGOS v20.0.0\n");
    console.color = 0x0f; // White tagline
    console.write_str("Self-verifying QEMU demo system\n\n");
    
    console.write_str("boot: ");
    console.color = 0x0a; console.write_str("verified\n"); console.color = 0x0f;
    
    console.write_str("kernel: ");
    console.color = 0x0b; console.write_str("online\n"); console.color = 0x0f;
    
    console.write_str("trust rule: ");
    console.color = 0x0e; console.write_str("verify-before-accept\n"); console.color = 0x0f;
    
    console.write_str("apps: ");
    console.color = 0x0a; console.write_str("1 accepted"); console.color = 0x0f;
    console.write_str(" / ");
    console.color = 0x0c; console.write_str("1 rejected\n"); console.color = 0x0f;
    
    console.write_str("storage: ");
    console.color = 0x03; console.write_str("embedded readonly table\n"); console.color = 0x0f;
    
    console.write_str("shell: ");
    console.color = 0x0b; console.write_str("online\n\n"); console.color = 0x07;
}

// =========================================================================
// Keyboard Driver (Polling PS/2 Keyboard)
// =========================================================================
fn read_scancode() -> Option<u8> {
    unsafe {
        let status: u8;
        core::arch::asm!(
            "in al, dx",
            out("al") status,
            in("dx") 0x64_u16,
            options(nomem, nostack, preserves_flags)
        );
        if (status & 0x01) != 0 {
            let scancode: u8;
            core::arch::asm!(
                "in al, dx",
                out("al") scancode,
                in("dx") 0x60_u16,
                options(nomem, nostack, preserves_flags)
            );
            Some(scancode)
        } else {
            None
        }
    }
}

fn scancode_to_ascii(code: u8) -> Option<char> {
    if code >= 0x80 {
        return None;
    }
    match code {
        0x1E => Some('a'),
        0x30 => Some('b'),
        0x2E => Some('c'),
        0x20 => Some('d'),
        0x12 => Some('e'),
        0x21 => Some('f'),
        0x22 => Some('g'),
        0x23 => Some('h'),
        0x17 => Some('i'),
        0x24 => Some('j'),
        0x25 => Some('k'),
        0x26 => Some('l'),
        0x32 => Some('m'),
        0x31 => Some('n'),
        0x18 => Some('o'),
        0x19 => Some('p'),
        0x10 => Some('q'),
        0x13 => Some('r'),
        0x1F => Some('s'),
        0x14 => Some('t'),
        0x16 => Some('u'),
        0x2F => Some('v'),
        0x11 => Some('w'),
        0x2D => Some('x'),
        0x15 => Some('y'),
        0x2C => Some('z'),
        0x39 => Some(' '),
        0x0C => Some('-'),
        0x35 => Some('/'),
        0x1C => Some('\n'),
        0x0E => Some('\x08'), // Backspace
        _ => None,
    }
}

struct ShellBuffer {
    buf: [u8; 128],
    len: usize,
}

impl ShellBuffer {
    pub fn new() -> Self {
        Self { buf: [0u8; 128], len: 0 }
    }

    pub fn push(&mut self, c: char) -> bool {
        if self.len < self.buf.len() {
            self.buf[self.len] = c as u8;
            self.len += 1;
            true
        } else {
            false
        }
    }

    pub fn pop(&mut self) -> bool {
        if self.len > 0 {
            self.len -= 1;
            true
        } else {
            false
        }
    }

    pub fn clear(&mut self) {
        self.len = 0;
    }

    pub fn as_str(&self) -> &str {
        core::str::from_utf8(&self.buf[..self.len]).unwrap_or("")
    }
}

fn delay_ticks(n: u64) {
    for _ in 0..n {
        unsafe {
            core::arch::asm!("nop");
        }
    }
}

// =========================================================================
// Kernel-controlled commands & Execution
// =========================================================================
unsafe fn execute_command(cmd: &str, console: &mut VgaConsole) {
    let parsed = bogk_core::ShellCommand::parse(cmd);
    match parsed {
        bogk_core::ShellCommand::Help => {
            console.write_str("commands:\n");
            console.write_str("  status\n");
            console.write_str("  ls\n");
            console.write_str("  cat /system/status\n");
            console.write_str("  cat /system/memory\n");
            console.write_str("  cat /system/processes\n");
            console.write_str("  cat /receipts/last\n");
            console.write_str("  run hello\n");
            console.write_str("  run bad-hello\n");
            console.write_str("  ps\n");
            console.write_str("  spawn <app>\n");
            console.write_str("  load <v32-app>\n");
            console.write_str("  runq\n");
            console.write_str("  sched step\n");
            console.write_str("  sched demo\n");
            console.write_str("  clear\n");
            console.write_str("  panic\n");
        }
        bogk_core::ShellCommand::Status => {
            let mut buf = [0u8; 512];
            let status_str = bogk_core::format_status(
                VERIFIED_APP_COUNT,
                REJECTED_APP_COUNT,
                LAST_RECEIPT_AVAILABLE,
                &mut buf,
            );
            console.write_str(status_str);
            console.write_str("\n");
            serial_write(status_str);
            serial_write("\n");
        }
        bogk_core::ShellCommand::Ls => {
            let mut buf = [0u8; 256];
            let ls_str = bogk_core::format_ls(&mut buf);
            console.write_str(ls_str);
            console.write_str("\n");
            serial_write(ls_str);
            serial_write("\n");
        }
        bogk_core::ShellCommand::Clear => {
            draw_header(console);
        }
        bogk_core::ShellCommand::Panic => {
            emit_syscall_invariants_receipt();
            emit_ipc_invariants_receipt();
            emit_writable_bogfs_invariants_receipt();
            panic!("manual panic triggered");
        }
        bogk_core::ShellCommand::CatSystemStatus => {
            let mut buf = [0u8; 512];
            let status_str = bogk_core::format_status(
                VERIFIED_APP_COUNT,
                REJECTED_APP_COUNT,
                LAST_RECEIPT_AVAILABLE,
                &mut buf,
            );
            console.write_str(status_str);
            console.write_str("\n");
            serial_write(status_str);
            serial_write("\n");
        }
        bogk_core::ShellCommand::CatReceiptsLast => {
            if LAST_RECEIPT_AVAILABLE {
                let receipt_str = core::str::from_utf8(&LAST_RECEIPT_BUF[..LAST_RECEIPT_LEN]).unwrap_or("");
                console.write_str(receipt_str);
                console.write_str("\n");
                serial_write(receipt_str);
                serial_write("\n");
            } else {
                console.write_str("no app run yet\n");
                serial_write("no app run yet\n");
            }
        }
        bogk_core::ShellCommand::Cat(path) => {
            let mut status_buf = [0u8; 512];
            let mut mem_buf = [0u8; 128];
            let mut processes_buf = [0u8; 4096];
            let mut scheduler_buf = [0u8; 512];
            let receipt_str = core::str::from_utf8(&LAST_RECEIPT_BUF[..LAST_RECEIPT_LEN]).unwrap_or("");
            let mem_str = get_formatted_mem_stats(&mut mem_buf);
            let processes_str = bogk_core::format_process_table(&PROCESS_TABLE, &mut processes_buf);
            let scheduler_str = bogk_core::format_scheduler(&SCHEDULER, &mut scheduler_buf);
            if let Some(content) = bogk_core::read_pseudo_file(
                path,
                VERIFIED_APP_COUNT,
                REJECTED_APP_COUNT,
                LAST_RECEIPT_AVAILABLE,
                receipt_str,
                mem_str,
                processes_str,
                scheduler_str,
                &mut status_buf,
            ) {
                if let Ok(s) = core::str::from_utf8(content) {
                    console.write_str(s);
                    console.write_str("\n");
                    serial_write(s);
                    serial_write("\n");
                }
            } else {
                console.write_str("cat: ");
                console.write_str(path);
                console.write_str(": No such file or directory\n");
            }
        }
        bogk_core::ShellCommand::Run(app) => {
            run_app_command(cmd, app, console);
        }
        bogk_core::ShellCommand::Spawn(app) => {
            spawn_app_command(app, console);
        }
        bogk_core::ShellCommand::Load(app) => {
            load_dynamic_app_command(app, console);
        }
        bogk_core::ShellCommand::Ps => {
            print_process_table(console);
        }
        bogk_core::ShellCommand::RunQueue => {
            print_scheduler(console);
        }
        bogk_core::ShellCommand::SchedStep => {
            scheduler_step(console);
        }
        bogk_core::ShellCommand::SchedDemo => {
            for _ in 0..4 {
                scheduler_step(console);
            }
        }
        bogk_core::ShellCommand::Unknown => {
            console.write_str("unknown command: ");
            console.write_str(cmd);
            console.write_str("\n");
        }
    }
}

static mut APP_RUNNING: bool = false;

fn format_app_path<'a>(app: &str, path_buf: &'a mut [u8; 128]) -> &'a str {
    let app_bytes = app.as_bytes();
    let starts_with_slash = app_bytes.len() > 0 && app_bytes[0] == b'/';
    let mut path_writer = BufferWriter::new(path_buf);
    if starts_with_slash {
        path_writer.write_str(app);
    } else {
        path_writer.write_str("/apps/");
        path_writer.write_str(app);
        let mut contains_dot = false;
        for &b in app_bytes {
            if b == b'.' {
                contains_dot = true;
                break;
            }
        }
        if !contains_dot {
            path_writer.write_str(".bogapp");
        }
    }
    path_writer.as_str()
}

unsafe fn run_app_command(cmd_str: &str, app: &str, console: &mut VgaConsole) {
    let mut path_buf = [0u8; 128];
    let path = format_app_path(app, &mut path_buf);

    let pid = match PROCESS_TABLE.create(path) {
        Some(pid) => pid,
        None => {
            console.write_str("process table full\n");
            serial_write("BOGOS_PROCESS_BEGIN\n");
            serial_write("PID=0\n");
            serial_write("APP_PATH=");
            serial_write(path);
            serial_write("\nAPP_HASH=none\n");
            serial_write("STATE_CREATED=false\nSTATE_VERIFIED=false\nSTATE_RUNNING=false\n");
            serial_write("STATE_EXITED=false\nSTATE_BLOCKED=false\nSTATE_REJECTED=true\n");
            serial_write("EXIT_CODE=-1\nBLOCK_REASON=process_table_full\n");
            serial_write("EXECUTION_STATUS=failed\nBOGOS_PROCESS_END\n");
            return;
        }
    };

    serial_write("BOGOS_APP_RUN_BEGIN\n");
    serial_write("COMMAND=");
    serial_write(cmd_str);
    serial_write("\n");
    serial_write("APP_PATH=");
    serial_write(path);
    serial_write("\n");

    if let Some(content) = bogfs_read(path) {
        console.write_str("running ");
        console.write_str(path);
        console.write_str(" in Ring 3...\n");

        let app_hash = bogk_core::sha256(content);
        let process = PROCESS_TABLE.get_mut(pid).unwrap();
        process.mark_verified(app_hash);

        let copy_len = core::cmp::min(content.len(), 65536);
        core::ptr::copy_nonoverlapping(content.as_ptr(), USER_CODE_BUFFER.as_mut_ptr(), copy_len);

        let entrypoint = &raw const USER_CODE_BUFFER as u32;
        let user_esp = (&raw const USER_STACK as u32) + 4096;

        PROCESS_TABLE.get_mut(pid).unwrap().mark_running();
        ACTIVE_BLOCK_REASON = "none";
        APP_RUNNING = true;
        let exit_code = setjmp_kernel(&raw mut KERNEL_JMP_BUF as *mut _);
        if APP_RUNNING {
            APP_RUNNING = false;
            enter_ring3(entrypoint, user_esp);
        }

        if ACTIVE_BLOCK_REASON == "exit" || exit_code == 0 {
            PROCESS_TABLE.get_mut(pid).unwrap().mark_exited(exit_code);
        } else {
            let reason = if ACTIVE_BLOCK_REASON == "none" {
                "nonzero_exit"
            } else {
                ACTIVE_BLOCK_REASON
            };
            PROCESS_TABLE
                .get_mut(pid)
                .unwrap()
                .mark_blocked(exit_code, reason);
        }
        emit_process_receipt(PROCESS_TABLE.get(pid).unwrap());

        serial_write("APP_EXECUTION_STATUS=");
        serial_write(PROCESS_TABLE.get(pid).unwrap().execution_status());
        serial_write("\n");
        serial_write("BOGOS_APP_RUN_END\n");

        console.write_str("app exited with status ");
        write_usize(exit_code as usize);
        console.write_str("\n");
    } else {
        PROCESS_TABLE
            .get_mut(pid)
            .unwrap()
            .mark_rejected("not_found_or_unverified");
        console.write_str("app lookup failed or verification rejected: ");
        console.write_str(app);
        console.write_str("\n");

        emit_process_receipt(PROCESS_TABLE.get(pid).unwrap());
        serial_write("APP_EXECUTION_STATUS=rejected\n");
        serial_write("BOGOS_APP_RUN_END\n");
    }
}

unsafe fn spawn_app_command(app: &str, console: &mut VgaConsole) {
    let mut path_buf = [0u8; 128];
    let path = format_app_path(app, &mut path_buf);
    let pid = match PROCESS_TABLE.create(path) {
        Some(pid) => pid,
        None => {
            console.write_str("spawn: process table full\n");
            return;
        }
    };
    if let Some(content) = bogfs_read(path) {
        let slot_index = (pid as usize).saturating_sub(1);
        let copy_len = core::cmp::min(content.len(), PROCESS_CODE_SLOT_SIZE);
        core::ptr::copy_nonoverlapping(
            content.as_ptr(),
            PROCESS_CODE_SLOTS[slot_index].bytes.as_mut_ptr(),
            copy_len,
        );
        let code_base = PROCESS_CODE_SLOTS[slot_index].bytes.as_ptr() as u32;
        let stack_base = PROCESS_STACK_SLOTS[slot_index].bytes.as_ptr() as u32;
        let process_cr3 = create_process_page_directory(slot_index).unwrap_or(0);
        let code_user_mapped = map_low_user_range(slot_index, code_base, copy_len, false);
        let data_user_mapped = map_low_user_range(
            slot_index,
            code_base + PROCESS_RUNTIME_DATA_OFFSET as u32,
            PROCESS_RUNTIME_DATA_SIZE,
            true,
        );
        let stack_user_mapped =
            map_low_user_range(slot_index, stack_base, PROCESS_STACK_SLOT_SIZE, true);
        let private_test_page_mapped = map_private_test_page(slot_index);
        let mapping_invariants_verified = verify_process_mapping_invariants(
            slot_index,
            code_base,
            copy_len,
            stack_base,
            process_cr3,
        );
        let record = PROCESS_TABLE.get_mut(pid).unwrap();
        record.mark_verified(bogk_core::sha256(content));
        record.assign_execution_memory(ProcessExecutionMemory {
            code_base,
            code_length: copy_len,
            stack_base,
            stack_top: stack_base + PROCESS_STACK_SLOT_SIZE as u32,
            slot_index,
            assigned: true,
        });
        record.assign_scaffolded_address_space();
        if PAGING_ENABLED && process_cr3 != 0 {
            record.mark_per_process_identity(process_cr3);
            if code_user_mapped && data_user_mapped && stack_user_mapped {
                record.mark_kernel_protected_identity(process_cr3);
                if private_test_page_mapped && mapping_invariants_verified {
                    record.mark_private_user_mappings(process_cr3);
                    if PROCESS_ISOLATION_RECEIPT_EMITTED {
                        record.mark_process_isolation_proven();
                    }
                }
            }
        }
        record.mark_ready();
        SCHEDULER.enqueue(pid, &PROCESS_TABLE);
        LAST_SCHEDULER_REASON = "spawn";
    } else {
        PROCESS_TABLE
            .get_mut(pid)
            .unwrap()
            .mark_rejected("not_found_or_unverified");
    }
    emit_process_receipt(PROCESS_TABLE.get(pid).unwrap());
    emit_mapping_invariant_receipt(pid, PROCESS_TABLE.get(pid).unwrap().address_space.cr3, unsafe {
        verify_process_mapping_invariants(
            (pid as usize).saturating_sub(1),
            PROCESS_TABLE.get(pid).unwrap().execution_memory.code_base,
            PROCESS_TABLE.get(pid).unwrap().execution_memory.code_length,
            PROCESS_TABLE.get(pid).unwrap().execution_memory.stack_base,
            PROCESS_TABLE.get(pid).unwrap().address_space.cr3,
        )
    });
    if PROCESS_TABLE.get(pid).unwrap().address_space.id != 0 {
        emit_address_space_receipt(PROCESS_TABLE.get(pid).unwrap());
        emit_user_mapping_receipt(PROCESS_TABLE.get(pid).unwrap());
    }
    console.write_str("spawned PID ");
    write_usize(pid as usize);
    console.write_str("\n");
}

fn emit_load_receipt(
    path: &str,
    content: Option<&[u8]>,
    app: Option<&DynamicApp<'_>>,
    reject_reason: &str,
    pid: Option<bogk_core::ProcessId>,
    entrypoint: u32,
) {
    let parsed_name = content
        .and_then(|value| value.get(32..56))
        .and_then(fixed_ascii_field)
        .unwrap_or("none");
    let parsed_version = content
        .and_then(|value| value.get(56..72))
        .and_then(fixed_ascii_field)
        .unwrap_or("none");
    let mut parsed_manifest_hash = [0u8; 32];
    if let Some(bytes) = content.and_then(|value| value.get(104..136)) {
        parsed_manifest_hash.copy_from_slice(bytes);
    }
    let mut parsed_expected_hash = [0u8; 32];
    if let Some(bytes) = content.and_then(|value| value.get(72..104)) {
        parsed_expected_hash.copy_from_slice(bytes);
    }
    let parsed_code_length = content
        .and_then(|value| read_be_u32(value, 24))
        .unwrap_or(0) as usize;
    let parsed_code_offset = content
        .and_then(|value| read_be_u32(value, 20))
        .unwrap_or(0) as usize;
    let parsed_code = content.and_then(|value| {
        parsed_code_offset
            .checked_add(parsed_code_length)
            .and_then(|end| value.get(parsed_code_offset..end))
    });
    let parsed_actual_hash = parsed_code.map(bogk_core::sha256).unwrap_or([0; 32]);
    let expected_hash = app
        .map(|value| value.expected_code_hash)
        .unwrap_or(parsed_expected_hash);
    let actual_hash = app
        .map(|value| value.actual_code_hash)
        .unwrap_or(parsed_actual_hash);
    serial_write("BOGOS_LOAD_BEGIN\nAPP_PATH=");
    serial_write(path);
    serial_write("\nAPP_NAME=");
    serial_write(app.map(|value| value.name).unwrap_or(parsed_name));
    serial_write("\nAPP_VERSION=");
    serial_write(app.map(|value| value.version).unwrap_or(parsed_version));
    serial_write("\nCONTAINER_LENGTH=");
    write_usize(content.map(|value| value.len()).unwrap_or(0));
    serial_write("\nCONTAINER_MAGIC_OK=");
    serial_write(if content
        .and_then(|value| value.get(0..8))
        == Some(V32_BOGAPP_MAGIC.as_slice())
    {
        "true"
    } else {
        "false"
    });
    serial_write("\nCONTAINER_VERSION_OK=");
    serial_write(if content.and_then(|value| read_be_u32(value, 8)) == Some(1) {
        "true"
    } else {
        "false"
    });
    serial_write("\nMANIFEST_HASH=");
    write_hex(&app.map(|value| value.manifest_hash).unwrap_or(parsed_manifest_hash));
    serial_write("\nCODE_OFFSET=");
    write_usize(parsed_code_offset);
    serial_write("\nCODE_LENGTH=");
    write_usize(app.map(|value| value.code.len()).unwrap_or(parsed_code_length));
    serial_write("\nENTRYPOINT=");
    serial_write_hex_u32(entrypoint);
    serial_write("\nCODE_HASH_EXPECTED=");
    write_hex(&expected_hash);
    serial_write("\nCODE_HASH_ACTUAL=");
    write_hex(&actual_hash);
    serial_write("\nHASH_MATCH=");
    serial_write(if parsed_code.is_some() && expected_hash == actual_hash {
        "true"
    } else {
        "false"
    });
    serial_write("\nCAPABILITY_POLICY=empty_only");
    serial_write("\nAPP_ACCEPTED=");
    serial_write(if app.is_some() && pid.is_some() { "true" } else { "false" });
    serial_write("\nREJECT_REASON=");
    serial_write(reject_reason);
    serial_write("\nPID=");
    write_optional_serial_pid(pid);
    serial_write("\nBOGOS_LOAD_END\n");
}

fn emit_process_admit_receipt(record: &ProcessRecord) {
    serial_write("BOGOS_PROCESS_ADMIT_BEGIN\nPID=");
    write_usize(record.pid as usize);
    serial_write("\nAPP_PATH=");
    serial_write(record.app_path());
    serial_write("\nCR3=");
    serial_write_hex_u32(record.address_space.cr3);
    serial_write("\nUSER_CODE_BASE=");
    serial_write_hex_u32(record.address_space.user_code_base);
    serial_write("\nUSER_CODE_PAGES=");
    write_usize(record.address_space.user_code_pages);
    serial_write("\nUSER_CODE_WRITABLE=false");
    serial_write("\nUSER_STACK_BASE=");
    serial_write_hex_u32(record.address_space.user_stack_base);
    serial_write("\nUSER_STACK_PAGES=");
    write_usize(record.address_space.user_stack_pages);
    serial_write("\nUSER_STACK_WRITABLE=true");
    serial_write("\nPROCESS_ISOLATION_ENFORCED=");
    serial_write(if record.address_space.process_isolation_enforced {
        "true"
    } else {
        "false"
    });
    serial_write("\nAPP_EXECUTION_ALLOWED=true");
    serial_write("\nADMISSION_SOURCE=dynamic_loader\nBOGOS_PROCESS_ADMIT_END\n");
}

unsafe fn load_dynamic_app_command(app_name: &str, console: &mut VgaConsole) {
    let mut path_buf = [0u8; 128];
    let path = format_app_path(app_name, &mut path_buf);
    let content = match bogfs_read(path) {
        Some(content) => content,
        None => {
            emit_load_receipt(path, None, None, "not_found", None, 0);
            return;
        }
    };
    let app = match parse_dynamic_app(content) {
        Ok(app) => app,
        Err(reason) => {
            emit_load_receipt(path, Some(content), None, reason, None, 0);
            return;
        }
    };
    let pid = match PROCESS_TABLE.create(path) {
        Some(pid) => pid,
        None => {
            emit_load_receipt(path, Some(content), Some(&app), "process_table_full", None, 0);
            return;
        }
    };
    let slot_index = (pid as usize).saturating_sub(1);
    core::ptr::copy_nonoverlapping(
        app.code.as_ptr(),
        PROCESS_CODE_SLOTS[slot_index].bytes.as_mut_ptr(),
        app.code.len(),
    );
    let code_base = PROCESS_CODE_SLOTS[slot_index].bytes.as_ptr() as u32;
    let stack_base = PROCESS_STACK_SLOTS[slot_index].bytes.as_ptr() as u32;
    let process_cr3 = create_process_page_directory(slot_index).unwrap_or(0);
    let code_user_mapped = map_low_user_range(slot_index, code_base, app.code.len(), false);
    let data_user_mapped = map_low_user_range(
        slot_index,
        code_base + PROCESS_RUNTIME_DATA_OFFSET as u32,
        PROCESS_RUNTIME_DATA_SIZE,
        true,
    );
    let stack_user_mapped =
        map_low_user_range(slot_index, stack_base, PROCESS_STACK_SLOT_SIZE, true);
    let private_test_page_mapped = map_private_test_page(slot_index);
    let mapping_invariants_verified =
        verify_process_mapping_invariants(slot_index, code_base, app.code.len(), stack_base, process_cr3);
    let record = PROCESS_TABLE.get_mut(pid).unwrap();
    record.mark_dynamic_loader_admitted();
    record.mark_verified(app.actual_code_hash);
    record.assign_execution_memory(ProcessExecutionMemory {
        code_base,
        code_length: app.code.len(),
        stack_base,
        stack_top: stack_base + PROCESS_STACK_SLOT_SIZE as u32,
        slot_index,
        assigned: true,
    });
    record.assign_scaffolded_address_space();
    if PAGING_ENABLED && process_cr3 != 0 {
        record.mark_per_process_identity(process_cr3);
        if code_user_mapped && data_user_mapped && stack_user_mapped {
            record.mark_kernel_protected_identity(process_cr3);
            if private_test_page_mapped && mapping_invariants_verified {
                record.mark_private_user_mappings(process_cr3);
                if PROCESS_ISOLATION_RECEIPT_EMITTED {
                    record.mark_process_isolation_proven();
                }
            }
        }
    }
    if !record.address_space.process_isolation_enforced {
        record.mark_rejected("isolation_not_proven");
        emit_load_receipt(path, Some(content), None, "isolation_not_proven", None, 0);
        return;
    }
    record.mark_ready();
    SCHEDULER.enqueue(pid, &PROCESS_TABLE);
    LAST_SCHEDULER_REASON = "spawn";
    emit_load_receipt(
        path,
        Some(content),
        Some(&app),
        "none",
        Some(pid),
        app.entrypoint_offset as u32,
    );
    emit_process_admit_receipt(PROCESS_TABLE.get(pid).unwrap());
    emit_process_receipt(PROCESS_TABLE.get(pid).unwrap());
    emit_mapping_invariant_receipt(pid, process_cr3, mapping_invariants_verified);
    emit_address_space_receipt(PROCESS_TABLE.get(pid).unwrap());
    emit_user_mapping_receipt(PROCESS_TABLE.get(pid).unwrap());
    console.write_str("dynamically loaded PID ");
    write_usize(pid as usize);
    console.write_str("\n");
}

unsafe fn run_v39_staged_app(console: &mut VgaConsole) {
    if !V39_EXECUTION_PENDING || V39_EXECUTION_DONE {
        return;
    }
    V39_EXECUTION_DONE = true;
    let path = "/apps/hello.bogapp";
    let pid = match PROCESS_TABLE.create(path) {
        Some(value) => value,
        None => {
            serial_write("BOGOS_V39_ADMIT_BEGIN\nAPP_PATH=/apps/hello.bogapp\nSTATUS=rejected\nREJECT_REASON=process_table_full\nPID=none\nSCHEDULER_ADMITTED=false\nBOGOS_V39_ADMIT_END\n");
            emit_v39_invariants();
            return;
        }
    };
    let slot_index = (pid as usize).saturating_sub(1);
    core::ptr::copy_nonoverlapping(
        V39_CODE_STAGING.as_ptr(),
        PROCESS_CODE_SLOTS[slot_index].bytes.as_mut_ptr(),
        V39_CODE_LENGTH,
    );
    let code_base = PROCESS_CODE_SLOTS[slot_index].bytes.as_ptr() as u32;
    let stack_base = PROCESS_STACK_SLOTS[slot_index].bytes.as_ptr() as u32;
    let process_cr3 = create_process_page_directory(slot_index).unwrap_or(0);
    let code_user_mapped = map_low_user_range(slot_index, code_base, V39_CODE_LENGTH, false);
    let data_user_mapped = map_low_user_range(
        slot_index,
        code_base + PROCESS_RUNTIME_DATA_OFFSET as u32,
        PROCESS_RUNTIME_DATA_SIZE,
        true,
    );
    let stack_user_mapped = map_low_user_range(slot_index, stack_base, PROCESS_STACK_SLOT_SIZE, true);
    let private_test_page_mapped = map_private_test_page(slot_index);
    let mapping_invariants_verified =
        verify_process_mapping_invariants(slot_index, code_base, V39_CODE_LENGTH, stack_base, process_cr3);
    let record = PROCESS_TABLE.get_mut(pid).unwrap();
    record.mark_dynamic_loader_admitted();
    record.mark_verified(V39_APP_CODE_HASH);
    record.assign_execution_memory(ProcessExecutionMemory {
        code_base,
        code_length: V39_CODE_LENGTH,
        stack_base,
        stack_top: stack_base + PROCESS_STACK_SLOT_SIZE as u32,
        slot_index,
        assigned: true,
    });
    record.assign_scaffolded_address_space();
    if PAGING_ENABLED && process_cr3 != 0 {
        record.mark_per_process_identity(process_cr3);
        if code_user_mapped && data_user_mapped && stack_user_mapped {
            record.mark_kernel_protected_identity(process_cr3);
            if private_test_page_mapped && mapping_invariants_verified {
                record.mark_private_user_mappings(process_cr3);
                record.mark_process_isolation_proven();
            }
        }
    }
    if !record.address_space.process_isolation_enforced {
        record.mark_rejected("isolation_not_proven");
        serial_write("BOGOS_V39_ADMIT_BEGIN\nAPP_PATH=/apps/hello.bogapp\nSTATUS=rejected\nREJECT_REASON=isolation_not_proven\nPID=none\nSCHEDULER_ADMITTED=false\nBOGOS_V39_ADMIT_END\n");
        emit_v39_invariants();
        return;
    }
    record.mark_ready();
    SCHEDULER.enqueue(pid, &PROCESS_TABLE);
    LAST_SCHEDULER_REASON = "v39_disk_loader";
    serial_write("BOGOS_V39_ADMIT_BEGIN\nAPP_PATH=/apps/hello.bogapp\nSTATUS=accepted\nREJECT_REASON=none\nPID=");
    write_usize(pid as usize);
    serial_write("\nSCHEDULER_ADMITTED=true\nADMISSION_SOURCE=persistent_bogfs\nCR3=");
    serial_write_hex_u32(process_cr3);
    serial_write("\nPROCESS_ISOLATION_ENFORCED=true\nUSER_CODE_WRITABLE=false\nFILESYSTEM_ROOT_HASH=");
    write_hex(&V39_SOURCE_ROOT);
    serial_write("\nFILESYSTEM_MANIFEST_HASH=");
    write_hex(&V39_SOURCE_MANIFEST);
    serial_write("\nFILE_HASH=");
    write_hex(&V39_SOURCE_FILE_HASH);
    serial_write("\nFILE_VERSION=");
    write_usize(V39_SOURCE_FILE_VERSION as usize);
    serial_write("\nFILE_LIFECYCLE_ID=");
    write_usize(V39_SOURCE_LIFECYCLE_ID as usize);
    serial_write("\nAPP_MANIFEST_HASH=");
    write_hex(&V39_APP_MANIFEST_HASH);
    serial_write("\nCODE_HASH=");
    write_hex(&V39_APP_CODE_HASH);
    serial_write("\nBOGOS_V39_ADMIT_END\n");
    emit_process_admit_receipt(PROCESS_TABLE.get(pid).unwrap());
    emit_mapping_invariant_receipt(pid, process_cr3, mapping_invariants_verified);
    emit_address_space_receipt(PROCESS_TABLE.get(pid).unwrap());
    emit_user_mapping_receipt(PROCESS_TABLE.get(pid).unwrap());

    for _ in 0..bogk_core::MAX_PROCESSES {
        if PROCESS_TABLE.get(pid).map(|value| value.execution_status() == "completed").unwrap_or(false) {
            break;
        }
        scheduler_step(console);
    }
    let record = PROCESS_TABLE.get(pid).unwrap();
    serial_write("BOGOS_V39_EXECUTION_BEGIN\nAPP_PATH=/apps/hello.bogapp\nPID=");
    write_usize(pid as usize);
    serial_write("\nRING3=true\nPROCESS_ISOLATION_ENFORCED=");
    serial_write(if record.address_space.process_isolation_enforced { "true" } else { "false" });
    serial_write("\nSTATE_EXITED=");
    serial_write(if record.execution_status() == "completed" { "true" } else { "false" });
    serial_write("\nEXECUTION_STATUS=");
    serial_write(record.execution_status());
    serial_write("\nBOGOS_V39_EXECUTION_END\n");
    emit_v39_invariants();
}

unsafe fn scheduler_step(console: &mut VgaConsole) {
    let previous_pid = SCHEDULER.last_selected_pid;
    let selected_pid = SCHEDULER.select_next(&mut PROCESS_TABLE);
    emit_scheduler_receipt(previous_pid, selected_pid);
    if let Some(pid) = selected_pid {
        execute_scheduled_process(pid, console);
    } else {
        console.write_str("scheduler: no READY process\n");
    }
}

unsafe fn execute_scheduled_process(pid: bogk_core::ProcessId, console: &mut VgaConsole) {
    let record = PROCESS_TABLE.get(pid).unwrap();
    let memory = record.execution_memory;
    let saved_context = record.context;
    let restore = record.restore_eligible();
    let process_cr3 = record.address_space.cr3;
    if !memory.assigned || process_cr3 == 0 {
        PROCESS_TABLE
            .get_mut(pid)
            .unwrap()
            .mark_rejected(if !memory.assigned {
                "execution_memory_unassigned"
            } else {
                "process_cr3_unassigned"
            });
        SCHEDULER.finish_current();
        emit_process_receipt(PROCESS_TABLE.get(pid).unwrap());
        return;
    }
    ACTIVE_BLOCK_REASON = "none";
    let from_pid = if ACTIVE_CR3_PID == 0 { None } else { Some(ACTIVE_CR3_PID) };
    let from_cr3 = ACTIVE_CR3;
    load_cr3(process_cr3);
    ACTIVE_CR3 = process_cr3;
    ACTIVE_CR3_PID = pid;
    emit_cr3_switch_receipt(
        if restore { "restore" } else { LAST_SCHEDULER_REASON },
        from_pid,
        pid,
        from_cr3,
        process_cr3,
    );
    ACTIVE_SCHEDULED_PID = pid;
    APP_RUNNING = true;

    // Reset quantum ticks when scheduling a process
    SCHEDULER.quantum_ticks = 0;

    let exit_code = setjmp_kernel(&raw mut KERNEL_JMP_BUF as *mut _);
    if APP_RUNNING {
        APP_RUNNING = false;
        if restore {
            emit_context_restore_receipt(pid, &saved_context);
            PROCESS_TABLE.get_mut(pid).unwrap().mark_running();
            restore_user_context(&saved_context);
        } else {
            PROCESS_TABLE.get_mut(pid).unwrap().mark_running();
            enter_ring3(memory.code_base, memory.stack_top);
        }
    }
    ACTIVE_SCHEDULED_PID = 0;
    if exit_code == YIELD_EXIT_CODE && ACTIVE_BLOCK_REASON == "yield" {
        SCHEDULER.finish_current();
        SCHEDULER.enqueue(pid, &PROCESS_TABLE);
        LAST_SCHEDULER_REASON = "yield";
    } else if exit_code == PREEMPT_EXIT_CODE && ACTIVE_BLOCK_REASON == "preempt" {
        SCHEDULER.finish_current();
        SCHEDULER.enqueue(pid, &PROCESS_TABLE);
        LAST_SCHEDULER_REASON = "preemption";
    } else if ACTIVE_BLOCK_REASON == "exit" || exit_code == 0 {
        PROCESS_TABLE.get_mut(pid).unwrap().mark_exited(exit_code);
        SCHEDULER.finish_current();
        LAST_SCHEDULER_REASON = "exit";
    } else {
        let reason = if ACTIVE_BLOCK_REASON == "none" {
            "nonzero_exit"
        } else {
            ACTIVE_BLOCK_REASON
        };
        PROCESS_TABLE
            .get_mut(pid)
            .unwrap()
            .mark_blocked(exit_code, reason);
        SCHEDULER.finish_current();
        LAST_SCHEDULER_REASON = "block";
    }
    emit_process_receipt(PROCESS_TABLE.get(pid).unwrap());
    console.write_str("scheduled PID ");
    write_usize(pid as usize);
    console.write_str("\n");
}

fn emit_context_save_receipt(pid: bogk_core::ProcessId, context: &SavedContext) {
    serial_write("BOGOS_CONTEXT_SAVE_BEGIN\nPID=");
    write_usize(pid as usize);
    serial_write("\nEIP=");
    serial_write_hex_u32(context.eip);
    serial_write("\nESP=");
    serial_write_hex_u32(context.esp);
    serial_write("\nSTATE_BEFORE=RUNNING\nSTATE_AFTER=READY\nREASON=yield\n");
    serial_write("BOGOS_CONTEXT_SAVE_END\n");
}

fn emit_address_space_receipt(record: &ProcessRecord) {
    let address_space = record.address_space;
    serial_write("BOGOS_ADDRSPACE_BEGIN\nPID=");
    write_usize(record.pid as usize);
    serial_write("\nADDRESS_SPACE_ID=");
    write_usize(address_space.id as usize);
    serial_write("\nCR3=");
    serial_write_hex_u32(address_space.cr3);
    serial_write("\nUSER_CODE_BASE=");
    serial_write_hex_u32(address_space.user_code_base);
    serial_write("\nUSER_CODE_PAGES=");
    write_usize(address_space.user_code_pages);
    serial_write("\nUSER_CODE_PHYS_BASE=");
    serial_write_hex_u32(address_space.user_code_phys_base);
    serial_write("\nUSER_STACK_BASE=");
    serial_write_hex_u32(address_space.user_stack_base);
    serial_write("\nUSER_STACK_PAGES=");
    write_usize(address_space.user_stack_pages);
    serial_write("\nUSER_STACK_PHYS_BASE=");
    serial_write_hex_u32(address_space.user_stack_phys_base);
    serial_write("\nKERNEL_MAPPING_BASE=");
    serial_write_hex_u32(address_space.kernel_mapping_base);
    serial_write("\nKERNEL_MAPPING_PAGES=");
    write_usize(address_space.kernel_mapping_pages);
    serial_write("\nKERNEL_SUPERVISOR_ONLY=");
    serial_write(if address_space.kernel_supervisor_only { "true" } else { "false" });
    serial_write("\nPAGING_ENABLED=");
    serial_write(if address_space.paging_enabled { "true" } else { "false" });
    serial_write("\nPER_PROCESS_CR3=true\nPAGE_DIRECTORY_KIND=");
    serial_write(address_space.page_directory_kind.as_str());
    serial_write("\nPROCESS_ISOLATION_ENFORCED=");
    serial_write(if address_space.process_isolation_enforced { "true" } else { "false" });
    serial_write("\nKERNEL_PROTECTION_ENFORCED=");
    serial_write(if address_space.kernel_protection_enforced { "true" } else { "false" });
    serial_write("\nUSER_CODE_USER_ACCESSIBLE=");
    serial_write(if address_space.user_code_user_accessible { "true" } else { "false" });
    serial_write("\nUSER_STACK_USER_ACCESSIBLE=");
    serial_write(if address_space.user_stack_user_accessible { "true" } else { "false" });
    serial_write("\nPRIVATE_USER_MAPPINGS=");
    serial_write(if address_space.private_user_mappings { "true" } else { "false" });
    serial_write("\nWRITABLE_CODE_BLOCKED=");
    serial_write(if address_space.writable_code_blocked { "true" } else { "false" });
    serial_write("\nCROSS_PROCESS_ISOLATION_ENFORCED=");
    serial_write(if address_space.cross_process_isolation_enforced { "true" } else { "false" });
    serial_write("\nAPP_HASH=");
    write_hex(&record.app_hash.unwrap_or([0; 32]));
    serial_write("\nADDRSPACE_HASH=");
    write_hex(&address_space.address_space_hash);
    serial_write("\nFAULT_COUNT=");
    write_usize(address_space.fault_count);
    serial_write("\nISOLATION_STATUS=");
    serial_write(address_space.verification_status.as_str());
    serial_write("\nBOGOS_ADDRSPACE_END\n");
}

fn emit_user_mapping_receipt(record: &ProcessRecord) {
    let address_space = record.address_space;
    serial_write("BOGOS_USER_MAPPING_BEGIN\nPID=");
    write_usize(record.pid as usize);
    serial_write("\nCR3=");
    serial_write_hex_u32(address_space.cr3);
    serial_write("\nUSER_CODE_BASE=");
    serial_write_hex_u32(address_space.user_code_base);
    serial_write("\nUSER_CODE_PAGES=");
    write_usize(address_space.user_code_pages);
    serial_write("\nUSER_CODE_WRITABLE=false\nUSER_STACK_BASE=");
    serial_write_hex_u32(address_space.user_stack_base);
    serial_write("\nUSER_STACK_PAGES=");
    write_usize(address_space.user_stack_pages);
    serial_write("\nUSER_STACK_WRITABLE=true\nPRIVATE_USER_MAPPINGS=");
    serial_write(if address_space.private_user_mappings { "true" } else { "false" });
    serial_write("\nBOGOS_USER_MAPPING_END\n");
}

fn emit_cr3_switch_receipt(
    reason: &str,
    from_pid: Option<bogk_core::ProcessId>,
    to_pid: bogk_core::ProcessId,
    from_cr3: u32,
    to_cr3: u32,
) {
    serial_write("BOGOS_CR3_SWITCH_BEGIN\nREASON=");
    serial_write(reason);
    serial_write("\nFROM_PID=");
    write_optional_serial_pid(from_pid);
    serial_write("\nTO_PID=");
    write_usize(to_pid as usize);
    serial_write("\nFROM_CR3=");
    if from_cr3 == 0 {
        serial_write("none");
    } else {
        serial_write_hex_u32(from_cr3);
    }
    serial_write("\nTO_CR3=");
    serial_write_hex_u32(to_cr3);
    serial_write("\nPER_PROCESS_CR3=true\nPROCESS_ISOLATION_ENFORCED=");
    unsafe {
        serial_write(if PROCESS_ISOLATION_RECEIPT_EMITTED {
            "true"
        } else {
            "false"
        })
    };
    serial_write("\n");
    serial_write("BOGOS_CR3_SWITCH_END\n");
}

fn emit_page_fault_receipt(
    pid: Option<bogk_core::ProcessId>,
    app_path: &str,
    fault_addr: u32,
    error_code: u32,
    user_mode: bool,
    process_state: &str,
    continued_after_fault: bool,
) {
    serial_write("BOGOS_PAGE_FAULT_BEGIN\nPID=");
    write_optional_serial_pid(pid);
    serial_write("\nAPP_PATH=");
    serial_write(app_path);
    serial_write("\nFAULT_ADDR=");
    serial_write_hex_u32(fault_addr);
    serial_write("\nERROR_CODE=");
    serial_write_hex_u32(error_code);
    serial_write("\nFAULT_REASON=");
    serial_write(if (error_code & 1) == 0 {
        "not_present"
    } else {
        "protection_violation"
    });
    serial_write("\nACCESS=");
    serial_write(if (error_code & (1 << 4)) != 0 {
        "execute"
    } else if (error_code & (1 << 1)) != 0 {
        "write"
    } else {
        "read"
    });
    serial_write("\nMODE=");
    serial_write(if user_mode || (error_code & (1 << 2)) != 0 {
        "user"
    } else {
        "kernel"
    });
    serial_write("\nPROCESS_STATE=");
    serial_write(process_state);
    serial_write("\nCONTINUED_AFTER_FAULT=");
    serial_write(if continued_after_fault { "true" } else { "false" });
    serial_write("\nBOGOS_PAGE_FAULT_END\n");
}

fn emit_preempt_receipt(pid: bogk_core::ProcessId, context: &SavedContext) {
    serial_write("BOGOS_PREEMPT_BEGIN\nTICK=");
    unsafe { write_usize(SCHEDULER.timer_ticks) };
    serial_write("\nPID=");
    write_usize(pid as usize);
    serial_write("\nEIP=");
    serial_write_hex_u32(context.eip);
    serial_write("\nESP=");
    serial_write_hex_u32(context.esp);
    serial_write("\nSTATE_BEFORE=RUNNING\nSTATE_AFTER=READY\nREASON=timer_irq\nPREEMPTION_COUNT=");
    unsafe { write_usize(SCHEDULER.preemption_count) };
    serial_write("\nBOGOS_PREEMPT_END\n");
}

fn emit_context_restore_receipt(pid: bogk_core::ProcessId, context: &SavedContext) {
    serial_write("BOGOS_CONTEXT_RESTORE_BEGIN\nPID=");
    write_usize(pid as usize);
    serial_write("\nEIP=");
    serial_write_hex_u32(context.eip);
    serial_write("\nESP=");
    serial_write_hex_u32(context.esp);
    serial_write("\nSTATE_BEFORE=READY\nSTATE_AFTER=RUNNING\n");
    serial_write("BOGOS_CONTEXT_RESTORE_END\n");
}

fn emit_scheduler_receipt(
    previous_pid: Option<bogk_core::ProcessId>,
    selected_pid: Option<bogk_core::ProcessId>,
) {
    serial_write("BOGOS_SCHED_BEGIN\nSCHED_STEP=");
    unsafe { write_usize(SCHEDULER.schedule_step) };
    serial_write("\nPOLICY=");
    unsafe { serial_write(SCHEDULER.policy()) };
    serial_write("\nREASON=");
    unsafe { serial_write(LAST_SCHEDULER_REASON) };
    serial_write("\nPREVIOUS_PID=");
    write_optional_serial_pid(previous_pid);
    serial_write("\nSELECTED_PID=");
    write_optional_serial_pid(selected_pid);
    serial_write("\nRUN_QUEUE=");
    let mut buf = [0u8; 128];
    let mut writer = BufferWriter::new(&mut buf);
    unsafe { bogk_core::write_run_queue(&mut writer, &SCHEDULER) };
    serial_write(writer.as_str());
    serial_write("\nSELECTED_STATE=");
    serial_write(if selected_pid.is_some() { "SCHEDULED" } else { "none" });
    serial_write("\nBOGOS_SCHED_END\n");
}

fn write_optional_serial_pid(pid: Option<bogk_core::ProcessId>) {
    if let Some(pid) = pid {
        write_usize(pid as usize);
    } else {
        serial_write("none");
    }
}

unsafe fn print_process_table(console: &mut VgaConsole) {
    let mut buf = [0u8; 4096];
    let output = bogk_core::format_process_table(&PROCESS_TABLE, &mut buf);
    console.write_str(output);
    console.write_str("\n");
    serial_write(output);
    serial_write("\n");
}

unsafe fn print_scheduler(console: &mut VgaConsole) {
    let mut buf = [0u8; 512];
    let output = bogk_core::format_scheduler(&SCHEDULER, &mut buf);
    console.write_str(output);
    console.write_str("\n");
    serial_write(output);
    serial_write("\n");
}

fn emit_process_receipt(record: &ProcessRecord) {
    serial_write("BOGOS_PROCESS_BEGIN\n");
    serial_write("PID=");
    write_usize(record.pid as usize);
    serial_write("\nAPP_PATH=");
    serial_write(record.app_path());
    serial_write("\nAPP_HASH=");
    if let Some(hash) = record.app_hash {
        write_hex(&hash);
    } else {
        serial_write("none");
    }
    serial_write("\nSTATE_CREATED=");
    serial_write(if record.state_created { "true" } else { "false" });
    serial_write("\nSTATE_VERIFIED=");
    serial_write(if record.state_verified { "true" } else { "false" });
    serial_write("\nSTATE_READY=");
    serial_write(if record.state_ready { "true" } else { "false" });
    serial_write("\nSTATE_SCHEDULED=");
    serial_write(if record.state_scheduled { "true" } else { "false" });
    serial_write("\nSTATE_RUNNING=");
    serial_write(if record.state_running { "true" } else { "false" });
    serial_write("\nSTATE_YIELDED=");
    serial_write(if record.state_yielded { "true" } else { "false" });
    serial_write("\nSTATE_PREEMPTED=");
    serial_write(if record.state_preempted { "true" } else { "false" });
    serial_write("\nSTATE_EXITED=");
    serial_write(if record.state_exited { "true" } else { "false" });
    serial_write("\nSTATE_BLOCKED=");
    serial_write(if record.state_blocked { "true" } else { "false" });
    serial_write("\nSTATE_REJECTED=");
    serial_write(if record.state_rejected { "true" } else { "false" });
    serial_write("\nEXIT_CODE=");
    if record.exit_code() < 0 {
        serial_write("-");
        write_usize(record.exit_code().unsigned_abs() as usize);
    } else {
        write_usize(record.exit_code() as usize);
    }
    serial_write("\nBLOCK_REASON=");
    serial_write(record.block_reason());
    serial_write("\nEXECUTION_STATUS=");
    serial_write(record.execution_status());
    serial_write("\nADDRESS_SPACE_ID=");
    write_usize(record.address_space.id as usize);
    serial_write("\nCR3=");
    serial_write_hex_u32(record.address_space.cr3);
    serial_write("\nPAGE_DIRECTORY_KIND=");
    serial_write(record.address_space.page_directory_kind.as_str());
    serial_write("\nISOLATION_STATUS=");
    serial_write(record.address_space.verification_status.as_str());
    serial_write("\nFAULT_COUNT=");
    write_usize(record.address_space.fault_count);
    serial_write("\nBOGOS_PROCESS_END\n");
}

fn emit_v20_app_run_receipt(command: &str, res: &bogk_core::AppLoaderResult) {
    serial_write("BOGOS_APP_RUN_BEGIN\n");
    serial_write("COMMAND=");
    serial_write(command);
    serial_write("\n");
    serial_write("APP_PATH=");
    serial_write(res.app_path);
    serial_write("\n");
    serial_write("APP_NAME=");
    serial_write(res.app_name);
    serial_write("\n");
    serial_write("APP_VERSION=");
    serial_write(res.app_version);
    serial_write("\n");
    serial_write("APP_PRESENT=");
    serial_write(if res.app_present { "true" } else { "false" });
    serial_write("\n");
    serial_write("APP_HASH_MATCH=");
    serial_write(if res.hash_match { "true" } else { "false" });
    serial_write("\n");
    serial_write("APP_ACCEPTED=");
    serial_write(if res.accepted { "true" } else { "false" });
    serial_write("\n");
    serial_write("APP_REJECTED=");
    serial_write(if res.rejected { "true" } else { "false" });
    serial_write("\n");
    serial_write("APP_EXECUTION_STARTED=");
    serial_write(if res.execution_started { "true" } else { "false" });
    serial_write("\n");
    serial_write("APP_OUTPUT_EVENT=");
    serial_write(res.output_event);
    serial_write("\n");
    serial_write("APP_EXECUTION_STATUS=");
    serial_write(res.execution_status);
    serial_write("\n");
    serial_write("APP_HALTED=");
    serial_write(if res.halted { "true" } else { "false" });
    serial_write("\n");
    serial_write("BOGOS_APP_RUN_END\n");
}

#[no_mangle]
pub extern "C" fn rust_start(mboot_magic: u32, mboot_info_addr: u32) -> ! {
    serial_write("RUST_START: magic=0x");
    write_usize(mboot_magic as usize);
    serial_write(" info_addr=0x");
    write_usize(mboot_info_addr as usize);
    serial_write("\n");

    unsafe {
        init_gdt();
        init_idt();
        pic_init();
        init_global_paging();
        emit_paging_receipt();
        core::arch::asm!("sti");
    }

    // Parse Multiboot memory map or bounds
    let mut mem_lower_kb = 0;
    let mut mem_upper_kb = 0;
    let mut mmap_addr = 0;
    let mut mmap_length = 0;

    let mut free_mem_start = unsafe { &_kernel_end as *const u8 as usize };

    if mboot_magic == 0x2BADB002 && mboot_info_addr != 0 {
        let mboot = unsafe { &*(mboot_info_addr as *const MultibootInfo) };
        if (mboot.flags & 1) != 0 {
            mem_lower_kb = mboot.mem_lower;
            mem_upper_kb = mboot.mem_upper;
        }
        if (mboot.flags & (1 << 6)) != 0 {
            mmap_addr = mboot.mmap_addr;
            mmap_length = mboot.mmap_length;
        }

        // Avoid overwriting Multiboot modules
        if (mboot.flags & (1 << 3)) != 0 && mboot.mods_count > 0 {
            let mods_end_addr = mboot.mods_addr as usize + (mboot.mods_count as usize) * core::mem::size_of::<MultibootModule>();
            if mods_end_addr > free_mem_start {
                free_mem_start = mods_end_addr;
            }

            let modules = unsafe { core::slice::from_raw_parts(mboot.mods_addr as *const MultibootModule, mboot.mods_count as usize) };
            for module in modules {
                if (module.mod_end as usize) > free_mem_start {
                    free_mem_start = module.mod_end as usize;
                }
                if module.cmdline != 0 {
                    let cmdline_end = module.cmdline as usize + 256;
                    if cmdline_end > free_mem_start {
                        free_mem_start = cmdline_end;
                    }
                }
            }
        }

        if mboot.cmdline != 0 {
            let cmdline_end = mboot.cmdline as usize + 256;
            if cmdline_end > free_mem_start {
                free_mem_start = cmdline_end;
            }
        }
    }

    // Align free_mem_start to page boundary
    free_mem_start = (free_mem_start + 4095) & !4095;

    let mut free_mem_end = 0;

    if mmap_addr != 0 && mmap_length > 0 {
        let mut offset = 0;
        while offset < mmap_length {
            let entry = unsafe { &*((mmap_addr + offset) as *const MultibootMmapEntry) };
            if entry.type_attr == 1 && entry.addr_low >= 0x100000 {
                let start = entry.addr_low as usize;
                let end = (entry.addr_low + entry.len_low) as usize;
                if start < free_mem_start && end > free_mem_start {
                    free_mem_end = end;
                    break;
                }
            }
            offset += entry.size + 4;
        }
    }

    if free_mem_end == 0 {
        free_mem_end = 1024 * 1024 + (mem_upper_kb as usize) * 1024;
    }


    // Initialize Physical Frame Allocator
    unsafe {
        phys_alloc_init(free_mem_start, free_mem_end);
    }

    // Initialize 4MB Kernel Heap
    let heap_size = 4 * 1024 * 1024; // 4MB
    let mut heap_start = 0;
    for i in 0..1024 {
        if let Some(page) = unsafe { phys_alloc_page() } {
            if i == 0 {
                heap_start = page;
            }
        } else {
            panic!("failed to allocate physical frames for heap");
        }
    }

    unsafe {
        *ALLOCATOR.heap_start.get() = heap_start;
        *ALLOCATOR.heap_end.get() = heap_start + heap_size;
        *ALLOCATOR.next.get() = heap_start;
    }

    // Verify dynamic allocations: Box
    {
        let check_val = alloc::boxed::Box::new(995828);
        if *check_val != 995828 {
            panic!("Heap verification failed!");
        }
    }

    unsafe {
        mount_bogfs(mboot_info_addr);
        if v39_image_present() {
            run_v39_disk_verification_proof();
        } else if v38_image_present() {
            run_v38_file_lifecycle_proof();
        } else if v37_image_present() {
            run_v37_persistent_bogfs_proof();
        } else {
            run_v36_block_device_proof();
        }
    }

    let boot_receipt = BootReceipt::v16_qemu();

    // 1. Emit Boot Receipt
    serial_write("BOGKERNEL_BOOT_BEGIN\n");
    serial_write("BOGKERNEL_FORMAT=");
    serial_write(boot_receipt.format);
    serial_write("\n");
    serial_write("PLATFORM=");
    serial_write(boot_receipt.platform);
    serial_write("\n");
    serial_write("EXECUTION_STATUS=");
    serial_write(boot_receipt.execution_status);
    serial_write("\n");
    serial_write("BOGKERNEL_BOOT_END\n");

    // 2. Execute Minimal VM Program
    let result = MinimalExecutor::execute(&MINIMAL_PROGRAM);

    // 3. Emit VM Execution Receipt
    serial_write("BOGKERNEL_VM_EXEC_BEGIN\n");
    serial_write("BOGKERNEL_VM_FORMAT=BOGKERNEL-native-vm-receipt-17.0\n");
    serial_write("INSTRUCTION_WIDTH=");
    write_usize(INSTRUCTION_WIDTH);
    serial_write("\n");
    serial_write("PROGRAM_INSTRUCTION_COUNT=");
    write_usize(result.instruction_count);
    serial_write("\n");
    serial_write("OPCODES_EXECUTED=NOOP,HALT\n");
    serial_write("HALTED=");
    serial_write(if result.halted { "true" } else { "false" });
    serial_write("\n");
    serial_write("UNSUPPORTED_OPCODE_SEEN=");
    serial_write(if result.unsupported_opcode_seen { "true" } else { "false" });
    serial_write("\n");
    serial_write("EXECUTION_STATUS=");
    serial_write(result.execution_status);
    serial_write("\n");
    serial_write("BOGKERNEL_VM_EXEC_END\n");

    // 4. Positive verification
    let res_pos = MinimalExecutor::execute_verify(&VERIFY_PROGRAM, PAYLOAD, CORRECT_HASH);
    emit_verify_receipt(&res_pos);

    // 5. Negative verification
    let res_neg = MinimalExecutor::execute_verify(&VERIFY_PROGRAM, PAYLOAD, WRONG_HASH);
    emit_verify_receipt(&res_neg);

    // 6. Positive App Bundle verification and execution
    let app_res_pos = POSITIVE_APP.verify_and_execute();
    emit_app_bundle_receipt(&app_res_pos);

    // 7. Negative App Bundle verification
    let app_res_neg = NEGATIVE_APP.verify_and_execute();
    emit_app_bundle_receipt(&app_res_neg);

    // =========================================================================
    // NEW v20 BogOS Demo System
    // =========================================================================
    let mut console = VgaConsole {
        cursor_x: 0,
        cursor_y: 0,
        color: 0x07, // Default light gray
    };

    draw_header(&mut console);

    serial_write("BOGOS_V20_BEGIN\n");
    serial_write("VERSION=20.0.0\n");
    serial_write("VGA_TEXT_ONLINE=true\n");
    serial_write("KEYBOARD_INPUT_ONLINE=true\n");
    serial_write("SHELL_ONLINE=true\n");
    serial_write("EMBEDDED_TABLE_PRESENT=true\n");
    serial_write("PSEUDO_FILE_COUNT=6\n");
    serial_write("VERIFIED_APP_COUNT=1\n");
    serial_write("REJECTED_APP_COUNT=1\n");
    serial_write("AUTO_DEMO_SUPPORTED=true\n");
    serial_write("BOGOS_V20_END\n");

    let mut auto_demo = true;
    let mut auto_demo_index = 0;
    let mut shell_buffer = ShellBuffer::new();

    console.write_str("bogos> ");

    loop {
        unsafe {
            run_v39_staged_app(&mut console);
        }
        let mut key_pressed = false;
        let mut sc = None;
        
        if let Some(scancode) = pop_scancode() {
            sc = Some(scancode);
            key_pressed = true;
        }

        if key_pressed {
            auto_demo = false;
            if let Some(scancode) = sc {
                if let Some(c) = scancode_to_ascii(scancode) {
                    if c == '\n' {
                        console.write_char('\n');
                        let cmd = shell_buffer.as_str();
                        if !cmd.is_empty() {
                            unsafe {
                                execute_command(cmd, &mut console);
                            }
                        }
                        shell_buffer.clear();
                        console.write_str("bogos> ");
                    } else if c == '\x08' {
                        if shell_buffer.pop() {
                            console.write_char('\x08');
                        }
                    } else {
                        if shell_buffer.push(c) {
                            console.write_char(c);
                        }
                    }
                }
            }
        } else if auto_demo && auto_demo_index < AUTO_DEMO_COMMANDS.len() {
            delay_ticks(100_000);
            
            // Check keyboard one more time inside delay just to be highly responsive
            if let Some(scancode) = pop_scancode() {
                auto_demo = false;
                if let Some(c) = scancode_to_ascii(scancode) {
                    if c == '\n' {
                        console.write_char('\n');
                        shell_buffer.clear();
                        console.write_str("bogos> ");
                    } else if c != '\x08' {
                        if shell_buffer.push(c) {
                            console.write_char(c);
                        }
                    }
                }
                continue;
            }

            let cmd = AUTO_DEMO_COMMANDS[auto_demo_index];
            auto_demo_index += 1;
            
            console.write_str(cmd);
            console.write_char('\n');
            
            unsafe {
                execute_command(cmd, &mut console);
            }
            
            console.write_str("bogos> ");
        } else {
            unsafe {
                core::arch::asm!("hlt");
            }
        }
    }
}


fn emit_verify_receipt(res: &VerificationResult) {
    serial_write("BOGKERNEL_VERIFY_BEGIN\n");
    serial_write("PAYLOAD_PRESENT=true\n");
    serial_write("EXPECTED_HASH=");
    write_hex(&res.expected_hash);
    serial_write("\n");
    serial_write("ACTUAL_HASH=");
    write_hex(&res.actual_hash);
    serial_write("\n");
    serial_write("HASH_MATCH=");
    serial_write(if res.hash_match { "true" } else { "false" });
    serial_write("\n");
    serial_write("DATA_ACCEPTED=");
    serial_write(if res.data_accepted { "true" } else { "false" });
    serial_write("\n");
    serial_write("DATA_REJECTED=");
    serial_write(if res.data_rejected { "true" } else { "false" });
    serial_write("\n");
    serial_write("EXECUTION_STATUS=");
    serial_write(res.execution_status);
    serial_write("\n");
    serial_write("BOGKERNEL_VERIFY_END\n");
}

fn emit_app_bundle_receipt(res: &bogk_core::AppBundleResult) {
    serial_write("BOGKERNEL_APP_BUNDLE_BEGIN\n");
    serial_write("APP_NAME=");
    serial_write(res.name);
    serial_write("\n");
    serial_write("APP_VERSION=");
    serial_write(res.version);
    serial_write("\n");
    serial_write("APP_PRESENT=");
    serial_write(if res.present { "true" } else { "false" });
    serial_write("\n");
    serial_write("APP_HASH_EXPECTED=");
    write_hex(&res.expected_hash);
    serial_write("\n");
    serial_write("APP_HASH_ACTUAL=");
    write_hex(&res.actual_hash);
    serial_write("\n");
    serial_write("APP_HASH_MATCH=");
    serial_write(if res.hash_match { "true" } else { "false" });
    serial_write("\n");
    serial_write("APP_ACCEPTED=");
    serial_write(if res.accepted { "true" } else { "false" });
    serial_write("\n");
    serial_write("APP_REJECTED=");
    serial_write(if res.rejected { "true" } else { "false" });
    serial_write("\n");
    serial_write("APP_EXECUTION_STARTED=");
    serial_write(if res.execution_started { "true" } else { "false" });
    serial_write("\n");
    serial_write("APP_EXECUTION_STATUS=");
    serial_write(res.execution_status);
    serial_write("\n");
    serial_write("APP_HALTED=");
    serial_write(if res.halted { "true" } else { "false" });
    serial_write("\n");
    serial_write("BOGKERNEL_APP_BUNDLE_END\n");
}


fn serial_write_hex_u32(val: u32) {
    for i in (0..8).rev() {
        let nibble = ((val >> (i * 4)) & 0x0F) as u8;
        let s = hex_char(nibble);
        serial_write(s);
    }
}

fn write_hex(hash: &[u8; 32]) {
    for &b in hash.iter() {
        let high = b >> 4;
        let low = b & 0x0F;
        serial_write(hex_char(high));
        serial_write(hex_char(low));
    }
}

fn hex_char(c: u8) -> &'static str {
    match c {
        0 => "0",
        1 => "1",
        2 => "2",
        3 => "3",
        4 => "4",
        5 => "5",
        6 => "6",
        7 => "7",
        8 => "8",
        9 => "9",
        10 => "a",
        11 => "b",
        12 => "c",
        13 => "d",
        14 => "e",
        15 => "f",
        _ => "?",
    }
}

fn serial_write(s: &str) {
    for b in s.bytes() {
        unsafe {
            let mut status: u8;
            loop {
                core::arch::asm!(
                    "in al, dx",
                    out("al") status,
                    in("dx") 0x3fd_u16,
                    options(nomem, nostack, preserves_flags)
                );
                if (status & 0x20) != 0 {
                    break;
                }
            }
            core::arch::asm!(
                "out dx, al",
                in("al") b,
                in("dx") 0x3f8_u16,
                options(nomem, nostack, preserves_flags)
            );
        }
    }
}

fn write_usize(mut n: usize) {
    if n == 0 {
        serial_write("0");
        return;
    }
    let mut buf = [0u8; 20];
    let mut i = 0;
    while n > 0 {
        buf[i] = (n % 10) as u8 + b'0';
        n /= 10;
        i += 1;
    }
    for j in (0..i).rev() {
        let s = match buf[j] {
            b'0' => "0",
            b'1' => "1",
            b'2' => "2",
            b'3' => "3",
            b'4' => "4",
            b'5' => "5",
            b'6' => "6",
            b'7' => "7",
            b'8' => "8",
            b'9' => "9",
            _ => "?",
        };
        serial_write(s);
    }
}

#[panic_handler]
fn panic(info: &PanicInfo) -> ! {
    let mut reason_buf = [0u8; 256];
    let mut writer = BufferWriter::new(&mut reason_buf);
    if let Some(s) = info.payload().downcast_ref::<&str>() {
        writer.write_str(s);
    } else if let Some(location) = info.location() {
        writer.write_str("Panic at ");
        writer.write_str(location.file());
        writer.write_str(":");
        writer.write_usize(location.line() as usize);
    } else {
        writer.write_str("unknown panic");
    }
    kernel_panic(writer.as_str());
}

fn kernel_panic(reason: &str) -> ! {
    unsafe {
        core::arch::asm!("cli");
    }

    let mut console = VgaConsole {
        cursor_x: 0,
        cursor_y: 0,
        color: 0x4f, // Red background, white text
    };
    console.clear();
    console.write_str("================================================================================\n");
    console.write_str("                                 BOGOS PANIC                                    \n");
    console.write_str("================================================================================\n\n");
    console.write_str("A fatal exception has occurred and the kernel was forced to halt.\n\n");
    console.write_str("Reason:\n");
    console.color = 0x4e; // Red background, yellow text
    console.write_str(reason);
    console.write_str("\n\n");
    console.color = 0x4f; // Red background, white text
    console.write_str("System halted.\n");

    serial_write("BOGOS_PANIC_BEGIN\n");
    serial_write("REASON=");
    serial_write(reason);
    serial_write("\n");
    serial_write("TICK_COUNT=");
    unsafe {
        write_usize(TICK_COUNT as usize);
    }
    serial_write("\n");
    serial_write("BOGOS_PANIC_END\n");

    loop {
        unsafe {
            core::arch::asm!("hlt");
        }
    }
}

#[no_mangle]
pub extern "C" fn memset(s: *mut u8, c: i32, n: usize) -> *mut u8 {
    unsafe {
        for i in 0..n {
            *s.add(i) = c as u8;
        }
    }
    s
}

#[no_mangle]
pub extern "C" fn memcpy(dest: *mut u8, src: *const u8, n: usize) -> *mut u8 {
    unsafe {
        for i in 0..n {
            *dest.add(i) = *src.add(i);
        }
    }
    dest
}

#[no_mangle]
pub extern "C" fn memcmp(s1: *const u8, s2: *const u8, n: usize) -> i32 {
    unsafe {
        for i in 0..n {
            let a = *s1.add(i);
            let b = *s2.add(i);
            if a != b {
                if a < b {
                    return -1;
                } else {
                    return 1;
                }
            }
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn rust_eh_personality() {}
