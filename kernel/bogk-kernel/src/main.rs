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
        .skip 16384
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

static mut KERNEL_STACK: [u8; 4096] = [0; 4096];
const PROCESS_CODE_SLOT_SIZE: usize = 65536;
const PROCESS_STACK_SLOT_SIZE: usize = 4096;
static mut USER_STACK: [u8; PROCESS_STACK_SLOT_SIZE] = [0; PROCESS_STACK_SLOT_SIZE];
static mut USER_CODE_BUFFER: [u8; PROCESS_CODE_SLOT_SIZE] = [0; PROCESS_CODE_SLOT_SIZE];
static mut PROCESS_CODE_SLOTS: [[u8; PROCESS_CODE_SLOT_SIZE]; bogk_core::MAX_PROCESSES] =
    [[0; PROCESS_CODE_SLOT_SIZE]; bogk_core::MAX_PROCESSES];
static mut PROCESS_STACK_SLOTS: [[u8; PROCESS_STACK_SLOT_SIZE]; bogk_core::MAX_PROCESSES] =
    [[0; PROCESS_STACK_SLOT_SIZE]; bogk_core::MAX_PROCESSES];

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
    TSS.esp0 = (&raw const KERNEL_STACK as *const _ as u32) + 4096;

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

#[no_mangle]
pub extern "C" fn handle_syscall(regs: &mut SyscallRegisters) {
    let syscall_num = regs.eax;
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
        6 => {
            // sys_exit(code) -> !
            unsafe {
                longjmp_to_kernel(regs.ebx);
            }
        }
        7 => {
            // sys_yield() -> save the active user context and return to scheduler
            unsafe {
                if ACTIVE_SCHEDULED_PID == 0 {
                    regs.eax = -1_i32 as u32;
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
                ACTIVE_BLOCK_REASON = "yield";
                longjmp_to_kernel(YIELD_EXIT_CODE as u32);
            }
        }
        _ => {
            regs.eax = -1_i32 as u32;
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
    "cat /system/scheduler",
    "cat /system/processes",
    "spawn ctx_a",
    "spawn ctx_b",
    "spawn missing_ctx",
    "sched step",
    "sched step",
    "sched step",
    "sched step",
    "spawn preempt_a",
    "spawn preempt_b",
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

        if exit_code == 0 {
            PROCESS_TABLE.get_mut(pid).unwrap().mark_exited(0);
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
            PROCESS_CODE_SLOTS[slot_index].as_mut_ptr(),
            copy_len,
        );
        let code_base = PROCESS_CODE_SLOTS[slot_index].as_ptr() as u32;
        let stack_base = PROCESS_STACK_SLOTS[slot_index].as_ptr() as u32;
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
    console.write_str("spawned PID ");
    write_usize(pid as usize);
    console.write_str("\n");
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
    if !memory.assigned {
        PROCESS_TABLE
            .get_mut(pid)
            .unwrap()
            .mark_rejected("execution_memory_unassigned");
        SCHEDULER.finish_current();
        emit_process_receipt(PROCESS_TABLE.get(pid).unwrap());
        return;
    }
    ACTIVE_BLOCK_REASON = "none";
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
    } else if exit_code == 0 {
        PROCESS_TABLE.get_mut(pid).unwrap().mark_exited(0);
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
