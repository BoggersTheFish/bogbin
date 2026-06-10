#![no_std]
#![no_main]

use core::panic::PanicInfo;
use bogk_core::{BootReceipt, MinimalExecutor, INSTRUCTION_WIDTH};

/// Multiboot1 Header
#[no_mangle]
#[link_section = ".multiboot_header"]
pub static MULTIBOOT_HEADER: [u32; 3] = [
    0x1BADB002, // magic
    0x00000000, // flags
    0xE4524FFE, // checksum (-(0x1BADB002 + 0) as u32)
];

/// Embedded minimal BOGVM program: NOOP + HALT
/// Format: >BBHHH
/// NOOP: 0x00, 0x00, 0x0000, 0x0000, 0x0000
/// HALT: 0x01, 0x00, 0x0000, 0x0000, 0x0000
static MINIMAL_PROGRAM: [u8; 16] = [
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // NOOP
    0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // HALT
];

#[no_mangle]
pub extern "C" fn rust_start() -> ! {
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

    loop {}
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

/// Minimal usize writer for serial output without allocation.
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
fn panic(_info: &PanicInfo) -> ! {
    loop {}
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
pub extern "C" fn rust_eh_personality() {}
