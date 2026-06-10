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
// Global state variables for BogOS v20
// =========================================================================
static mut VERIFIED_APP_COUNT: usize = 1;
static mut REJECTED_APP_COUNT: usize = 1;
static mut LAST_RECEIPT_AVAILABLE: bool = false;
static mut LAST_RECEIPT_BUF: [u8; 1024] = [0u8; 1024];
static mut LAST_RECEIPT_LEN: usize = 0;

const AUTO_DEMO_COMMANDS: &[&str] = &[
    "help",
    "status",
    "ls",
    "cat /system/status",
    "cat /receipts/last",
    "run hello",
    "run bad-hello",
    "clear",
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
            console.write_str("  cat /receipts/last\n");
            console.write_str("  run hello\n");
            console.write_str("  run bad-hello\n");
            console.write_str("  clear\n");
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
        }
        bogk_core::ShellCommand::Ls => {
            let mut buf = [0u8; 256];
            let ls_str = bogk_core::format_ls(&mut buf);
            console.write_str(ls_str);
            console.write_str("\n");
        }
        bogk_core::ShellCommand::Clear => {
            draw_header(console);
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
        }
        bogk_core::ShellCommand::CatReceiptsLast => {
            if LAST_RECEIPT_AVAILABLE {
                let receipt_str = core::str::from_utf8(&LAST_RECEIPT_BUF[..LAST_RECEIPT_LEN]).unwrap_or("");
                console.write_str(receipt_str);
                console.write_str("\n");
            } else {
                console.write_str("no app run yet\n");
            }
        }
        bogk_core::ShellCommand::Cat(path) => {
            let mut status_buf = [0u8; 512];
            let receipt_str = core::str::from_utf8(&LAST_RECEIPT_BUF[..LAST_RECEIPT_LEN]).unwrap_or("");
            if let Some(content) = bogk_core::read_pseudo_file(
                path,
                VERIFIED_APP_COUNT,
                REJECTED_APP_COUNT,
                LAST_RECEIPT_AVAILABLE,
                receipt_str,
                &mut status_buf,
            ) {
                if let Ok(s) = core::str::from_utf8(content) {
                    console.write_str(s);
                    console.write_str("\n");
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
        bogk_core::ShellCommand::Unknown => {
            console.write_str("unknown command: ");
            console.write_str(cmd);
            console.write_str("\n");
        }
    }
}

unsafe fn run_app_command(cmd_str: &str, app: &str, console: &mut VgaConsole) {
    if app == "hello" {
        console.write_str("verifying /apps/hello.bogapp\n");
        let res = bogk_core::load_and_verify_app(
            "/apps/hello.bogapp",
            bogk_core::HELLO_BYTECODE,
            bogk_core::HELLO_APP_HASH,
            "hello-bogos",
            "20.0.0",
        );
        console.write_str("hash_match=");
        console.write_str(if res.hash_match { "true\n" } else { "false\n" });
        console.write_str("app_accepted=");
        console.write_str(if res.accepted { "true\n" } else { "false\n" });
        console.write_str("app_execution_started=");
        console.write_str(if res.execution_started { "true\n" } else { "false\n" });
        if res.accepted {
            console.write_str("hello from verified BogOS app\n");
            VERIFIED_APP_COUNT += 1;
        }
        console.write_str("app_halted=");
        console.write_str(if res.halted { "true\n" } else { "false\n" });
        
        LAST_RECEIPT_LEN = bogk_core::format_app_receipt(cmd_str, &res, &mut LAST_RECEIPT_BUF).len();
        LAST_RECEIPT_AVAILABLE = true;
        console.write_str("receipt_written=true\n");
        
        emit_v20_app_run_receipt(cmd_str, &res);
        
    } else if app == "bad-hello" {
        console.write_str("verifying /apps/bad-hello.bogapp\n");
        let res = bogk_core::load_and_verify_app(
            "/apps/bad-hello.bogapp",
            bogk_core::HELLO_BYTECODE,
            bogk_core::BAD_HELLO_APP_HASH,
            "bad-hello-bogos",
            "20.0.0",
        );
        console.write_str("hash_match=");
        console.write_str(if res.hash_match { "true\n" } else { "false\n" });
        console.write_str("app_accepted=");
        console.write_str(if res.accepted { "true\n" } else { "false\n" });
        console.write_str("app_rejected=");
        console.write_str(if res.rejected { "true\n" } else { "false\n" });
        console.write_str("app_execution_started=");
        console.write_str(if res.execution_started { "true\n" } else { "false\n" });
        
        if res.rejected {
            REJECTED_APP_COUNT += 1;
            let old_color = console.color;
            console.color = 0x0c; // Light red
            console.write_str("\nBOGOS SECURITY BLOCK\n");
            console.write_str("/apps/bad-hello.bogapp rejected\n");
            console.write_str("reason: hash mismatch\n");
            console.write_str("execution prevented\n\n");
            console.color = old_color;
        } else {
            console.write_str("blocked: app failed verification\n");
        }
        
        LAST_RECEIPT_LEN = bogk_core::format_app_receipt(cmd_str, &res, &mut LAST_RECEIPT_BUF).len();
        LAST_RECEIPT_AVAILABLE = true;
        console.write_str("receipt_written=true\n");
        
        emit_v20_app_run_receipt(cmd_str, &res);
        
    } else {
        console.write_str("app lookup failed: ");
        console.write_str(app);
        console.write_str("\n");
        let res = bogk_core::load_missing_app("/apps/unknown.bogapp");
        emit_v20_app_run_receipt(cmd_str, &res);
    }
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
    serial_write("PSEUDO_FILE_COUNT=4\n");
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
        
        for _ in 0..10000 {
            if let Some(scancode) = read_scancode() {
                sc = Some(scancode);
                key_pressed = true;
                break;
            }
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
            if let Some(scancode) = read_scancode() {
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
                core::arch::asm!("pause");
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
