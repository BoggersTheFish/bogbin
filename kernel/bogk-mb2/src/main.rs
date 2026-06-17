#![no_std]
#![no_main]

use core::panic::PanicInfo;

core::arch::global_asm!(
    r#"
    .section .multiboot2, "a"
    .align 8
    .global mb2_header_start
    mb2_header_start:
        .long 0xE85250D6
        .long 0
        .long mb2_header_end - mb2_header_start
        .long -(0xE85250D6 + 0 + (mb2_header_end - mb2_header_start))

        .short 5
        .short 0
        .long 20
        .long 0
        .long 0
        .long 32

        .align 8

        .short 0
        .short 0
        .long 8
    mb2_header_end:

    .global kernel_entry
    kernel_entry:
        mov esp, offset stack_top
        push ebx
        push eax
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
    "#
);

#[no_mangle]
pub extern "C" fn rust_start(mboot_magic: u32, mboot_info_addr: u32) -> ! {
    bogk_boot_fb::run_magenta_proof_mb2(mboot_magic, mboot_info_addr)
}

#[no_mangle]
pub extern "C" fn rust_eh_personality() {}

#[no_mangle]
pub unsafe extern "C" fn memcpy(
    dest: *mut core::ffi::c_void,
    src: *const core::ffi::c_void,
    n: usize,
) -> *mut core::ffi::c_void {
    let d = dest as *mut u8;
    let s = src as *const u8;
    for i in 0..n {
        d.add(i).write_volatile(s.add(i).read_volatile());
    }
    dest
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {
        unsafe {
            core::arch::asm!("cli");
            core::arch::asm!("hlt");
        }
    }
}