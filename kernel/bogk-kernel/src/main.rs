#![no_std]
#![no_main]

use core::panic::PanicInfo;
use bogk_core::{BootReceipt, MinimalExecutor, INSTRUCTION_WIDTH, VerificationResult, AppBundle, AppManifest};

core::arch::global_asm!(
    r#"
    .global kernel_entry
    kernel_entry:
        mov esp, offset stack_top

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
/// Format: >BBHHH
/// NOOP: 0x00, 0x00, 0x0000, 0x0000, 0x0000
/// HALT: 0x01, 0x00, 0x0000, 0x0000, 0x0000
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

    loop {}
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
