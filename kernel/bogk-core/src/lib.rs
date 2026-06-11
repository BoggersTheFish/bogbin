#![no_std]

/// The fixed-point scale used for all BOGVM wave-state math.
pub const SCALE: u16 = 1000;

/// The fixed instruction width in bytes.
pub const INSTRUCTION_WIDTH: usize = 8;

/// BOGVM Opcodes as defined in docs/bogvm_bytecode_contract.md
#[repr(u8)]
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum Opcode {
    Noop = 0x00,
    Halt = 0x01,
    CreateNode = 0x02,
    CreateEdge = 0x03,
    CreateClaim = 0x04,
    Activate = 0x05,
    Propagate = 0x06,
    Decay = 0x07,
    Interfere = 0x08,
    ComputeTension = 0x09,
    Verify = 0x0A,
    Accept = 0x0B,
    Reject = 0x0C,
    Quarantine = 0x0D,
    LogReceipt = 0x0E,
    EmitReceipt = 0x0F,
    DeclareBasis = 0x10,
    LoadCoefficients = 0x11,
    Synthesize = 0x12,
    VerifyHash = 0x13,
    AcceptData = 0x14,
    StoreResidual = 0x15,
    ApplyResidual = 0x16,
    RejectData = 0x17,
}

impl From<u8> for Opcode {
    fn from(value: u8) -> Self {
        match value {
            0x00 => Opcode::Noop,
            0x01 => Opcode::Halt,
            0x02 => Opcode::CreateNode,
            0x03 => Opcode::CreateEdge,
            0x04 => Opcode::CreateClaim,
            0x05 => Opcode::Activate,
            0x06 => Opcode::Propagate,
            0x07 => Opcode::Decay,
            0x08 => Opcode::Interfere,
            0x09 => Opcode::ComputeTension,
            0x0A => Opcode::Verify,
            0x0B => Opcode::Accept,
            0x0C => Opcode::Reject,
            0x0D => Opcode::Quarantine,
            0x0E => Opcode::LogReceipt,
            0x0F => Opcode::EmitReceipt,
            0x10 => Opcode::DeclareBasis,
            0x11 => Opcode::LoadCoefficients,
            0x12 => Opcode::Synthesize,
            0x13 => Opcode::VerifyHash,
            0x14 => Opcode::AcceptData,
            0x15 => Opcode::StoreResidual,
            0x16 => Opcode::ApplyResidual,
            0x17 => Opcode::RejectData,
            _ => Opcode::Noop, // Default to NOOP for unknown if used loosely, but executor will check.
        }
    }
}

/// A BOGVM instruction.
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub struct Instruction {
    pub opcode: Opcode,
    pub opcode_raw: u8,
    pub flags: u8,
    pub target: u16,
    pub source: u16,
    pub param: u16,
}

impl Instruction {
    /// Decodes an 8-byte big-endian instruction.
    pub fn decode(data: &[u8]) -> Option<Self> {
        if data.len() < INSTRUCTION_WIDTH {
            return None;
        }
        let opcode_raw = data[0];
        let flags = data[1];
        let target = u16::from_be_bytes([data[2], data[3]]);
        let source = u16::from_be_bytes([data[4], data[5]]);
        let param = u16::from_be_bytes([data[6], data[7]]);

        Some(Self {
            opcode: Opcode::from(opcode_raw),
            opcode_raw,
            flags,
            target,
            source,
            param,
        })
    }
}

/// The result of a BOGVM execution.
#[derive(Debug, PartialEq, Eq)]
pub struct ExecutionResult {
    pub instruction_count: usize,
    pub pc_final: usize,
    pub halted: bool,
    pub unsupported_opcode_seen: bool,
    pub execution_status: &'static str,
}

/// The result of a BOGVM verification execution.
#[derive(Debug, PartialEq, Eq)]
pub struct VerificationResult {
    pub instruction_count: usize,
    pub pc_final: usize,
    pub halted: bool,
    pub unsupported_opcode_seen: bool,
    pub execution_status: &'static str,
    pub expected_hash: [u8; 32],
    pub actual_hash: [u8; 32],
    pub hash_match: bool,
    pub data_accepted: bool,
    pub data_rejected: bool,
}

/// App bundle manifest metadata
#[derive(Debug, PartialEq, Eq, Clone)]
pub struct AppManifest {
    pub format: &'static str,
}

/// An embedded App Bundle
#[derive(Debug, PartialEq, Eq, Clone)]
pub struct AppBundle {
    pub name: &'static str,
    pub version: &'static str,
    pub bytecode: &'static [u8],
    pub expected_hash: [u8; 32],
    pub manifest: AppManifest,
}

/// The result of verifying and executing an embedded App Bundle
#[derive(Debug, PartialEq, Eq)]
pub struct AppBundleResult {
    pub name: &'static str,
    pub version: &'static str,
    pub present: bool,
    pub expected_hash: [u8; 32],
    pub actual_hash: [u8; 32],
    pub hash_match: bool,
    pub accepted: bool,
    pub rejected: bool,
    pub execution_started: bool,
    pub execution_status: &'static str,
    pub halted: bool,
}

impl AppBundle {
    pub fn verify_and_execute(&self) -> AppBundleResult {
        let actual_hash = sha256(self.bytecode);
        let hash_match = actual_hash == self.expected_hash;

        let (accepted, rejected) = if hash_match {
            (true, false)
        } else {
            (false, true)
        };

        if accepted {
            let result = MinimalExecutor::execute(self.bytecode);
            AppBundleResult {
                name: self.name,
                version: self.version,
                present: true,
                expected_hash: self.expected_hash,
                actual_hash,
                hash_match,
                accepted,
                rejected,
                execution_started: true,
                execution_status: result.execution_status,
                halted: result.halted,
            }
        } else {
            AppBundleResult {
                name: self.name,
                version: self.version,
                present: true,
                expected_hash: self.expected_hash,
                actual_hash,
                hash_match,
                accepted,
                rejected,
                execution_started: false,
                execution_status: "rejected",
                halted: false,
            }
        }
    }
}

/// A minimal BOGVM executor supporting only NOOP and HALT.
pub struct MinimalExecutor;


impl MinimalExecutor {
    /// Executes a bytecode program.
    pub fn execute(program: &[u8]) -> ExecutionResult {
        let mut pc = 0;
        let mut instruction_count = 0;
        let mut halted = false;
        let mut unsupported_opcode_seen = false;

        while pc + INSTRUCTION_WIDTH <= program.len() {
            let instr_bytes = &program[pc..pc + INSTRUCTION_WIDTH];
            let instr = match Instruction::decode(instr_bytes) {
                Some(i) => i,
                None => break, // Should not happen due to loop condition
            };

            instruction_count += 1;
            pc += INSTRUCTION_WIDTH;

            match instr.opcode {
                Opcode::Noop => {
                    // Check if it was actually a NOOP or an unknown opcode mapped to NOOP
                    if instr.opcode_raw != 0x00 {
                        unsupported_opcode_seen = true;
                        break;
                    }
                }
                Opcode::Halt => {
                    halted = true;
                    break;
                }
                _ => {
                    unsupported_opcode_seen = true;
                    break;
                }
            }
        }

        let status = if halted && !unsupported_opcode_seen {
            "completed"
        } else {
            "failed"
        };

        ExecutionResult {
            instruction_count,
            pc_final: pc,
            halted,
            unsupported_opcode_seen,
            execution_status: status,
        }
    }

    /// Executes a bytecode program and performs payload verification.
    pub fn execute_verify(
        program: &[u8],
        payload: &[u8],
        expected_hash: [u8; 32],
    ) -> VerificationResult {
        let mut pc = 0;
        let mut instruction_count = 0;
        let mut halted = false;
        let mut unsupported_opcode_seen = false;
        let mut hash_match = false;
        let mut data_accepted = false;
        let mut data_rejected = false;
        let mut actual_hash = [0u8; 32];

        while pc + INSTRUCTION_WIDTH <= program.len() {
            let instr_bytes = &program[pc..pc + INSTRUCTION_WIDTH];
            let instr = match Instruction::decode(instr_bytes) {
                Some(i) => i,
                None => break,
            };

            instruction_count += 1;
            pc += INSTRUCTION_WIDTH;

            match instr.opcode {
                Opcode::Noop => {
                    if instr.opcode_raw != 0x00 {
                        unsupported_opcode_seen = true;
                        break;
                    }
                }
                Opcode::Halt => {
                    halted = true;
                    break;
                }
                Opcode::VerifyHash => {
                    actual_hash = sha256(payload);
                    hash_match = actual_hash == expected_hash;
                }
                Opcode::AcceptData => {
                    if hash_match {
                        data_accepted = true;
                    }
                }
                Opcode::RejectData => {
                    if !hash_match {
                        data_rejected = true;
                    }
                }
                _ => {
                    unsupported_opcode_seen = true;
                    break;
                }
            }
        }

        let status = if halted && !unsupported_opcode_seen {
            "completed"
        } else {
            "failed"
        };

        VerificationResult {
            instruction_count,
            pc_final: pc,
            halted,
            unsupported_opcode_seen,
            execution_status: status,
            expected_hash,
            actual_hash,
            hash_match,
            data_accepted,
            data_rejected,
        }
    }
}

const K: [u32; 64] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

pub fn sha256(data: &[u8]) -> [u8; 32] {
    let mut h0 = 0x6a09e667;
    let mut h1 = 0xbb67ae85;
    let mut h2 = 0x3c6ef372;
    let mut h3 = 0xa54ff53a;
    let mut h4 = 0x510e527f;
    let mut h5 = 0x9b05688c;
    let mut h6 = 0x1f83d9ab;
    let mut h7 = 0x5be0cd19;

    let mut block = [0u8; 64];
    let mut block_len = 0;
    let total_len_bits = (data.len() as u64) * 8;

    let mut i = 0;
    while i < data.len() || block_len > 0 {
        if block_len < 64 && i < data.len() {
            block[block_len] = data[i];
            block_len += 1;
            i += 1;
        } else {
            if block_len == 64 {
                process_block(&block, &mut h0, &mut h1, &mut h2, &mut h3, &mut h4, &mut h5, &mut h6, &mut h7);
                block_len = 0;
            } else {
                block[block_len] = 0x80;
                block_len += 1;
                if block_len > 56 {
                    while block_len < 64 {
                        block[block_len] = 0;
                        block_len += 1;
                    }
                    process_block(&block, &mut h0, &mut h1, &mut h2, &mut h3, &mut h4, &mut h5, &mut h6, &mut h7);
                    block_len = 0;
                }
                while block_len < 56 {
                    block[block_len] = 0;
                    block_len += 1;
                }
                let len_bytes = total_len_bits.to_be_bytes();
                block[56..64].copy_from_slice(&len_bytes);
                process_block(&block, &mut h0, &mut h1, &mut h2, &mut h3, &mut h4, &mut h5, &mut h6, &mut h7);
                block_len = 0;
            }
        }
    }

    if data.is_empty() {
        block[0] = 0x80;
        for j in 1..56 {
            block[j] = 0;
        }
        let len_bytes = 0_u64.to_be_bytes();
        block[56..64].copy_from_slice(&len_bytes);
        process_block(&block, &mut h0, &mut h1, &mut h2, &mut h3, &mut h4, &mut h5, &mut h6, &mut h7);
    }

    let mut out = [0u8; 32];
    out[0..4].copy_from_slice(&h0.to_be_bytes());
    out[4..8].copy_from_slice(&h1.to_be_bytes());
    out[8..12].copy_from_slice(&h2.to_be_bytes());
    out[12..16].copy_from_slice(&h3.to_be_bytes());
    out[16..20].copy_from_slice(&h4.to_be_bytes());
    out[20..24].copy_from_slice(&h5.to_be_bytes());
    out[24..28].copy_from_slice(&h6.to_be_bytes());
    out[28..32].copy_from_slice(&h7.to_be_bytes());
    out
}

static mut W: [u32; 64] = [0; 64];

fn process_block(
    block: &[u8; 64],
    h0: &mut u32,
    h1: &mut u32,
    h2: &mut u32,
    h3: &mut u32,
    h4: &mut u32,
    h5: &mut u32,
    h6: &mut u32,
    h7: &mut u32,
) {
    unsafe {
        for j in 0..16 {
            W[j] = u32::from_be_bytes([
                block[j * 4],
                block[j * 4 + 1],
                block[j * 4 + 2],
                block[j * 4 + 3],
            ]);
        }
        for j in 16..64 {
            let s0 = W[j - 15].rotate_right(7) ^ W[j - 15].rotate_right(18) ^ (W[j - 15] >> 3);
            let s1 = W[j - 2].rotate_right(17) ^ W[j - 2].rotate_right(19) ^ (W[j - 2] >> 10);
            W[j] = W[j - 16]
                .wrapping_add(s0)
                .wrapping_add(W[j - 7])
                .wrapping_add(s1);
        }

        let mut a = *h0;
        let mut b = *h1;
        let mut c = *h2;
        let mut d = *h3;
        let mut e = *h4;
        let mut f = *h5;
        let mut g = *h6;
        let mut h = *h7;

        for j in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ (!e & g);
            let temp1 = h
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(K[j])
                .wrapping_add(W[j]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let temp2 = s0.wrapping_add(maj);

            h = g;
            g = f;
            f = e;
            e = d.wrapping_add(temp1);
            d = c;
            c = b;
            b = a;
            a = temp1.wrapping_add(temp2);
        }

        *h0 = h0.wrapping_add(a);
        *h1 = h1.wrapping_add(b);
        *h2 = h2.wrapping_add(c);
        *h3 = h3.wrapping_add(d);
        *h4 = h4.wrapping_add(e);
        *h5 = h5.wrapping_add(f);
        *h6 = h6.wrapping_add(g);
        *h7 = h7.wrapping_add(h);
    }
}

/// A deterministic boot receipt record for BogKernel.
pub struct BootReceipt {
    pub format: &'static str,
    pub platform: &'static str,
    pub execution_status: &'static str,
}

impl BootReceipt {
    pub const fn v16_qemu() -> Self {
        Self {
            format: "BOGKERNEL-boot-receipt-16.0",
            platform: "qemu",
            execution_status: "completed",
        }
    }
}

/// A simple deterministic check to ensure fixed-point math matches expectations.
pub fn check_fixed_point(value: u16, factor: u16) -> u16 {
    ((value as u32 * factor as u32) / SCALE as u32) as u16
}

/// The result of verifying and executing an embedded App Bundle in v20
#[derive(Debug, PartialEq, Eq, Clone)]
pub struct AppLoaderResult {
    pub app_name: &'static str,
    pub app_version: &'static str,
    pub app_path: &'static str,
    pub app_present: bool,
    pub hash_expected: [u8; 32],
    pub hash_actual: [u8; 32],
    pub hash_match: bool,
    pub accepted: bool,
    pub rejected: bool,
    pub execution_started: bool,
    pub execution_status: &'static str,
    pub halted: bool,
    pub output_event: &'static str,
}

/// App bundle manifest metadata (extended or simple)
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PseudoFileEntry {
    pub path: &'static str,
    pub kind: &'static str, // "system", "receipt", "app"
    pub byte_length: usize,
    pub expected_hash: Option<[u8; 32]>,
    pub app_manifest_reference: Option<&'static str>,
}

pub const HELLO_APP_HASH: [u8; 32] = [
    0x9d, 0x34, 0x14, 0x9f, 0xbd, 0x1f, 0xe7, 0x77,
    0xeb, 0x23, 0x87, 0x99, 0x05, 0x4c, 0x8c, 0xbf,
    0xbc, 0xe3, 0x72, 0x25, 0x5f, 0x21, 0x9f, 0x87,
    0x40, 0x83, 0x8d, 0xef, 0x9b, 0xfd, 0x02, 0xdb,
];

pub const BAD_HELLO_APP_HASH: [u8; 32] = [0u8; 32];

pub const HELLO_BYTECODE: &[u8] = &[
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // NOOP
    0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // HALT
];

pub const PSEUDO_FILESYSTEM: &[PseudoFileEntry] = &[
    PseudoFileEntry {
        path: "/system/status",
        kind: "system",
        byte_length: 164,
        expected_hash: None,
        app_manifest_reference: None,
    },
    PseudoFileEntry {
        path: "/system/memory",
        kind: "system",
        byte_length: 128,
        expected_hash: None,
        app_manifest_reference: None,
    },
    PseudoFileEntry {
        path: "/receipts/last",
        kind: "receipt",
        byte_length: 0,
        expected_hash: None,
        app_manifest_reference: None,
    },
    PseudoFileEntry {
        path: "/apps/hello.bogapp",
        kind: "app",
        byte_length: 16,
        expected_hash: Some(HELLO_APP_HASH),
        app_manifest_reference: Some("BOGKERNEL-app-manifest-19.0"),
    },
    PseudoFileEntry {
        path: "/apps/bad-hello.bogapp",
        kind: "app",
        byte_length: 16,
        expected_hash: Some(BAD_HELLO_APP_HASH),
        app_manifest_reference: Some("BOGKERNEL-app-manifest-19.0"),
    },
];

pub fn lookup_app(path: &str) -> Option<PseudoFileEntry> {
    for entry in PSEUDO_FILESYSTEM {
        if entry.path == path && entry.kind == "app" {
            return Some(entry.clone());
        }
    }
    None
}

pub fn load_and_verify_app(
    path: &'static str,
    bytecode: &[u8],
    expected_hash: [u8; 32],
    app_name: &'static str,
    app_version: &'static str,
) -> AppLoaderResult {
    let actual_hash = sha256(bytecode);
    let hash_match = actual_hash == expected_hash;
    let (accepted, rejected) = if hash_match { (true, false) } else { (false, true) };

    if accepted {
        let exec_result = MinimalExecutor::execute(bytecode);
        let output_event = if app_name == "hello-bogos" {
            "hello_from_verified_bogos_app"
        } else {
            "none"
        };
        AppLoaderResult {
            app_name,
            app_version,
            app_path: path,
            app_present: true,
            hash_expected: expected_hash,
            hash_actual: actual_hash,
            hash_match,
            accepted,
            rejected,
            execution_started: true,
            execution_status: exec_result.execution_status,
            halted: exec_result.halted,
            output_event,
        }
    } else {
        AppLoaderResult {
            app_name,
            app_version,
            app_path: path,
            app_present: true,
            hash_expected: expected_hash,
            hash_actual: actual_hash,
            hash_match,
            accepted,
            rejected,
            execution_started: false,
            execution_status: "rejected",
            halted: false,
            output_event: "none",
        }
    }
}

pub fn load_missing_app(path: &'static str) -> AppLoaderResult {
    AppLoaderResult {
        app_name: "none",
        app_version: "0.0.0",
        app_path: path,
        app_present: false,
        hash_expected: [0u8; 32],
        hash_actual: [0u8; 32],
        hash_match: false,
        accepted: false,
        rejected: false,
        execution_started: false,
        execution_status: "not_found",
        halted: false,
        output_event: "none",
    }
}

pub struct BufferWriter<'a> {
    buf: &'a mut [u8],
    pos: usize,
}

impl<'a> BufferWriter<'a> {
    pub fn new(buf: &'a mut [u8]) -> Self {
        Self { buf, pos: 0 }
    }

    pub fn write_str(&mut self, s: &str) {
        let bytes = s.as_bytes();
        let len = bytes.len().min(self.buf.len() - self.pos);
        self.buf[self.pos..self.pos + len].copy_from_slice(&bytes[..len]);
        self.pos += len;
    }

    pub fn write_usize(&mut self, mut n: usize) {
        if n == 0 {
            self.write_str("0");
            return;
        }
        let mut temp = [0u8; 20];
        let mut i = 0;
        while n > 0 {
            temp[i] = (n % 10) as u8 + b'0';
            n /= 10;
            i += 1;
        }
        for j in (0..i).rev() {
            let s = &[temp[j]];
            self.write_str(core::str::from_utf8(s).unwrap_or("?"));
        }
    }

    pub fn as_str(self) -> &'a str {
        core::str::from_utf8(&self.buf[..self.pos]).unwrap_or("")
    }
}

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum ShellCommand<'a> {
    Help,
    Status,
    Ls,
    CatSystemStatus,
    CatReceiptsLast,
    Run(&'a str),
    Cat(&'a str),
    Clear,
    Panic,
    Unknown,
}

impl<'a> ShellCommand<'a> {
    pub fn parse(input: &'a str) -> Self {
        let trimmed = input.trim();
        if trimmed == "help" {
            ShellCommand::Help
        } else if trimmed == "status" {
            ShellCommand::Status
        } else if trimmed == "ls" {
            ShellCommand::Ls
        } else if trimmed == "clear" {
            ShellCommand::Clear
        } else if trimmed == "panic" {
            ShellCommand::Panic
        } else if trimmed == "cat /system/status" {
            ShellCommand::CatSystemStatus
        } else if trimmed == "cat /receipts/last" {
            ShellCommand::CatReceiptsLast
        } else if trimmed.starts_with("cat ") {
            ShellCommand::Cat(trimmed["cat ".len()..].trim())
        } else if trimmed == "run hello" {
            ShellCommand::Run("hello")
        } else if trimmed == "run bad-hello" {
            ShellCommand::Run("bad-hello")
        } else if trimmed.starts_with("run ") {
            ShellCommand::Run(trimmed["run ".len()..].trim())
        } else {
            ShellCommand::Unknown
        }
    }
}

extern "C" {
    pub fn kernel_lookup_file(path_ptr: *const u8, path_len: usize, out_len: *mut usize) -> *const u8;
    pub fn kernel_list_files(buf_ptr: *mut u8, buf_len: usize) -> usize;
}

pub fn format_ls<'a>(buf: &'a mut [u8]) -> &'a str {
    unsafe {
        let len = kernel_list_files(buf.as_mut_ptr(), buf.len());
        core::str::from_utf8(&buf[..len]).unwrap_or("")
    }
}

pub fn format_status<'a>(
    verified_app_count: usize,
    rejected_app_count: usize,
    last_receipt_available: bool,
    buf: &'a mut [u8],
) -> &'a str {
    let mut writer = BufferWriter::new(buf);
    writer.write_str("BOGOS STATUS\n");
    writer.write_str("kernel_verified=true\n");
    writer.write_str("vga_online=true\n");
    writer.write_str("shell_online=true\n");
    writer.write_str("embedded_table_present=true\n");
    writer.write_str("verified_app_count=");
    writer.write_usize(verified_app_count);
    writer.write_str("\n");
    writer.write_str("rejected_app_count=");
    writer.write_usize(rejected_app_count);
    writer.write_str("\n");
    writer.write_str("last_receipt_available=");
    writer.write_str(if last_receipt_available { "true" } else { "false" });
    writer.as_str()
}

pub fn format_memory_stats<'a>(
    allocated_bytes: usize,
    freed_bytes: usize,
    alloc_count: usize,
    free_count: usize,
    buf: &'a mut [u8],
) -> &'a str {
    let mut writer = BufferWriter::new(buf);
    writer.write_str("BOGOS MEMORY STATS\n");
    writer.write_str("total_allocated=");
    writer.write_usize(allocated_bytes);
    writer.write_str("\n");
    writer.write_str("total_freed=");
    writer.write_usize(freed_bytes);
    writer.write_str("\n");
    writer.write_str("active_allocated=");
    writer.write_usize(allocated_bytes.saturating_sub(freed_bytes));
    writer.write_str("\n");
    writer.write_str("alloc_calls=");
    writer.write_usize(alloc_count);
    writer.write_str("\n");
    writer.write_str("free_calls=");
    writer.write_usize(free_count);
    writer.as_str()
}

pub fn format_app_receipt<'a>(
    command: &str,
    res: &AppLoaderResult,
    buf: &'a mut [u8],
) -> &'a str {
    let mut writer = BufferWriter::new(buf);
    writer.write_str("COMMAND=");
    writer.write_str(command);
    writer.write_str("\n");
    writer.write_str("APP_PATH=");
    writer.write_str(res.app_path);
    writer.write_str("\n");
    writer.write_str("APP_NAME=");
    writer.write_str(res.app_name);
    writer.write_str("\n");
    writer.write_str("APP_VERSION=");
    writer.write_str(res.app_version);
    writer.write_str("\n");
    writer.write_str("APP_PRESENT=");
    writer.write_str(if res.app_present { "true" } else { "false" });
    writer.write_str("\n");
    writer.write_str("APP_HASH_MATCH=");
    writer.write_str(if res.hash_match { "true" } else { "false" });
    writer.write_str("\n");
    writer.write_str("APP_ACCEPTED=");
    writer.write_str(if res.accepted { "true" } else { "false" });
    writer.write_str("\n");
    writer.write_str("APP_REJECTED=");
    writer.write_str(if res.rejected { "true" } else { "false" });
    writer.write_str("\n");
    writer.write_str("APP_EXECUTION_STARTED=");
    writer.write_str(if res.execution_started { "true" } else { "false" });
    writer.write_str("\n");
    writer.write_str("APP_OUTPUT_EVENT=");
    writer.write_str(res.output_event);
    writer.write_str("\n");
    writer.write_str("APP_EXECUTION_STATUS=");
    writer.write_str(res.execution_status);
    writer.write_str("\n");
    writer.write_str("APP_HALTED=");
    writer.write_str(if res.halted { "true" } else { "false" });
    writer.as_str()
}

pub fn read_pseudo_file<'a>(
    path: &str,
    verified_app_count: usize,
    rejected_app_count: usize,
    last_receipt_available: bool,
    last_receipt_buf: &'a str,
    memory_stats_buf: &'a str,
    dynamic_status_buf: &'a mut [u8],
) -> Option<&'a [u8]> {
    match path {
        "/system/status" => {
            let s = format_status(
                verified_app_count,
                rejected_app_count,
                last_receipt_available,
                dynamic_status_buf,
            );
            Some(s.as_bytes())
        }
        "/system/memory" => Some(memory_stats_buf.as_bytes()),
        "/receipts/last" => {
            if last_receipt_available {
                Some(last_receipt_buf.as_bytes())
            } else {
                Some(b"no app run yet")
            }
        }
        "/apps/hello.bogapp" => Some(HELLO_BYTECODE),
        "/apps/bad-hello.bogapp" => Some(HELLO_BYTECODE),
        _ => {
            unsafe {
                let mut len = 0;
                let ptr = kernel_lookup_file(path.as_ptr(), path.len(), &mut len);
                if !ptr.is_null() {
                    Some(core::slice::from_raw_parts(ptr, len))
                } else {
                    None
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[no_mangle]
    pub extern "C" fn kernel_lookup_file(path_ptr: *const u8, path_len: usize, out_len: *mut usize) -> *const u8 {
        let path = unsafe {
            let slice = core::slice::from_raw_parts(path_ptr, path_len);
            core::str::from_utf8(slice).unwrap_or("")
        };
        if path == "/apps/hello.bogapp" {
            unsafe { *out_len = HELLO_BYTECODE.len(); }
            HELLO_BYTECODE.as_ptr()
        } else if path == "/apps/bad-hello.bogapp" {
            unsafe { *out_len = HELLO_BYTECODE.len(); }
            HELLO_BYTECODE.as_ptr()
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
        writer.write_str("/receipts/last\n");
        writer.write_str("/apps/hello.bogapp\n");
        writer.write_str("/apps/bad-hello.bogapp");
        writer.as_str().len()
    }

    #[test]
    fn test_fixed_point_math() {
        assert_eq!(check_fixed_point(1000, 500), 500);
        assert_eq!(check_fixed_point(100, 500), 50);
        assert_eq!(check_fixed_point(1, 1), 0);
    }

    #[test]
    fn test_decode_noop() {
        let data = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00];
        let instr = Instruction::decode(&data).unwrap();
        assert_eq!(instr.opcode, Opcode::Noop);
        assert_eq!(instr.opcode_raw, 0x00);
    }

    #[test]
    fn test_decode_halt() {
        let data = [0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00];
        let instr = Instruction::decode(&data).unwrap();
        assert_eq!(instr.opcode, Opcode::Halt);
        assert_eq!(instr.opcode_raw, 0x01);
    }

    #[test]
    fn test_execute_noop_halt() {
        let mut program = [0u8; 16];
        program[0] = 0x00; // NOOP
        program[8] = 0x01; // HALT
        
        let result = MinimalExecutor::execute(&program);
        assert_eq!(result.instruction_count, 2);
        assert_eq!(result.pc_final, 16);
        assert!(result.halted);
        assert!(!result.unsupported_opcode_seen);
        assert_eq!(result.execution_status, "completed");
    }

    #[test]
    fn test_reject_unsupported_opcode() {
        let mut program = [0u8; 8];
        program[0] = 0xFF; // Unsupported
        
        let result = MinimalExecutor::execute(&program);
        assert_eq!(result.instruction_count, 1);
        assert!(result.unsupported_opcode_seen);
        assert_eq!(result.execution_status, "failed");
    }

    #[test]
    fn test_enforce_instruction_width() {
        let program = [0x00; 7]; // Incomplete instruction
        let result = MinimalExecutor::execute(&program);
        assert_eq!(result.instruction_count, 0);
        assert_eq!(result.pc_final, 0);
    }

    #[test]
    fn test_sha256_hashing() {
        let empty_hash = sha256(&[]);
        let expected_empty = [
            0xe3, 0xb0, 0xc4, 0x42, 0x98, 0xfc, 0x1c, 0x14,
            0x9a, 0xfb, 0xf4, 0xc8, 0x99, 0x6f, 0xb9, 0x24,
            0x27, 0xae, 0x41, 0xe4, 0x64, 0x9b, 0x93, 0x4c,
            0xa4, 0x95, 0x99, 0x1b, 0x78, 0x52, 0xb8, 0x55,
        ];
        assert_eq!(empty_hash, expected_empty);

        let payload_hash = sha256(b"BOGBIN-v18-payload");
        let expected_payload = [
            0x34, 0x57, 0xc1, 0x9c, 0x98, 0x0b, 0x8b, 0x9e,
            0x58, 0xac, 0x59, 0x57, 0xd7, 0x12, 0xcb, 0xdb,
            0x9f, 0x2d, 0x88, 0x7e, 0x19, 0x64, 0x2a, 0xc5,
            0xea, 0xce, 0x42, 0x6c, 0xf3, 0x97, 0x83, 0xe3,
        ];
        assert_eq!(payload_hash, expected_payload);
    }

    #[test]
    fn test_execute_verify_success() {
        let program = [
            0x13, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
            0x14, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x17, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        ];
        let payload = b"BOGBIN-v18-payload";
        let correct_hash = [
            0x34, 0x57, 0xc1, 0x9c, 0x98, 0x0b, 0x8b, 0x9e,
            0x58, 0xac, 0x59, 0x57, 0xd7, 0x12, 0xcb, 0xdb,
            0x9f, 0x2d, 0x88, 0x7e, 0x19, 0x64, 0x2a, 0xc5,
            0xea, 0xce, 0x42, 0x6c, 0xf3, 0x97, 0x83, 0xe3,
        ];
        let result = MinimalExecutor::execute_verify(&program, payload, correct_hash);
        assert_eq!(result.instruction_count, 4);
        assert!(result.halted);
        assert!(!result.unsupported_opcode_seen);
        assert_eq!(result.execution_status, "completed");
        assert!(result.hash_match);
        assert!(result.data_accepted);
        assert!(!result.data_rejected);
    }

    #[test]
    fn test_execute_verify_failure() {
        let program = [
            0x13, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
            0x14, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x17, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        ];
        let payload = b"BOGBIN-v18-payload";
        let wrong_hash = [0u8; 32];
        let result = MinimalExecutor::execute_verify(&program, payload, wrong_hash);
        assert_eq!(result.instruction_count, 4);
        assert!(result.halted);
        assert!(!result.unsupported_opcode_seen);
        assert_eq!(result.execution_status, "completed");
        assert!(!result.hash_match);
        assert!(!result.data_accepted);
        assert!(result.data_rejected);
    }

    #[test]
    fn test_app_bundle_success() {
        static BYTECODE: [u8; 16] = [
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // NOOP
            0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // HALT
        ];
        let hash = sha256(&BYTECODE);
        let bundle = AppBundle {
            name: "hello-bogos",
            version: "19.0.0",
            bytecode: &BYTECODE,
            expected_hash: hash,
            manifest: AppManifest {
                format: "BOGKERNEL-app-manifest-19.0",
            },
        };
        let result = bundle.verify_and_execute();
        assert_eq!(result.name, "hello-bogos");
        assert_eq!(result.version, "19.0.0");
        assert!(result.present);
        assert_eq!(result.expected_hash, hash);
        assert_eq!(result.actual_hash, hash);
        assert!(result.hash_match);
        assert!(result.accepted);
        assert!(!result.rejected);
        assert!(result.execution_started);
        assert_eq!(result.execution_status, "completed");
        assert!(result.halted);
    }

    #[test]
    fn test_app_bundle_failure() {
        static BYTECODE: [u8; 16] = [
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // NOOP
            0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // HALT
        ];
        let actual_hash = sha256(&BYTECODE);
        let wrong_hash = [0u8; 32];
        let bundle = AppBundle {
            name: "bad-hello-bogos",
            version: "19.0.0",
            bytecode: &BYTECODE,
            expected_hash: wrong_hash,
            manifest: AppManifest {
                format: "BOGKERNEL-app-manifest-19.0",
            },
        };
        let result = bundle.verify_and_execute();
        assert_eq!(result.name, "bad-hello-bogos");
        assert_eq!(result.version, "19.0.0");
        assert!(result.present);
        assert_eq!(result.expected_hash, wrong_hash);
        assert_eq!(result.actual_hash, actual_hash);
        assert!(!result.hash_match);
        assert!(!result.accepted);
        assert!(result.rejected);
        assert!(!result.execution_started);
        assert_eq!(result.execution_status, "rejected");
        assert!(!result.halted);
    }

    #[test]
    fn test_embedded_pseudo_file_table_contains_required_paths() {
        let required_paths = [
            "/system/status",
            "/system/memory",
            "/receipts/last",
            "/apps/hello.bogapp",
            "/apps/bad-hello.bogapp",
        ];
        for path in &required_paths {
            let found = PSEUDO_FILESYSTEM.iter().any(|entry| entry.path == *path);
            assert!(found, "Required path {} not found in pseudo-filesystem", path);
        }
    }

    #[test]
    fn test_status_command_result() {
        let mut buf = [0u8; 512];
        let status_str = format_status(1, 1, true, &mut buf);
        let expected = "BOGOS STATUS\n\
                        kernel_verified=true\n\
                        vga_online=true\n\
                        shell_online=true\n\
                        embedded_table_present=true\n\
                        verified_app_count=1\n\
                        rejected_app_count=1\n\
                        last_receipt_available=true";
        assert_eq!(status_str, expected);
    }

    #[test]
    fn test_ls_command_result() {
        let mut buf = [0u8; 256];
        let ls_str = format_ls(&mut buf);
        let expected = "/system/status\n\
                        /system/memory\n\
                        /receipts/last\n\
                        /apps/hello.bogapp\n\
                        /apps/bad-hello.bogapp";
        assert_eq!(ls_str, expected);
    }

    #[test]
    fn test_app_lookup_success() {
        let entry = lookup_app("/apps/hello.bogapp");
        assert!(entry.is_some());
        assert_eq!(entry.unwrap().path, "/apps/hello.bogapp");
    }

    #[test]
    fn test_app_lookup_failure() {
        let entry = lookup_app("/apps/nonexistent");
        assert!(entry.is_none());
    }

    #[test]
    fn test_good_app_verification_success() {
        let res = load_and_verify_app(
            "/apps/hello.bogapp",
            HELLO_BYTECODE,
            HELLO_APP_HASH,
            "hello-bogos",
            "20.0.0",
        );
        assert!(res.hash_match);
        assert!(res.accepted);
        assert!(!res.rejected);
        assert!(res.execution_started);
        assert_eq!(res.execution_status, "completed");
    }

    #[test]
    fn test_bad_app_verification_failure() {
        let res = load_and_verify_app(
            "/apps/bad-hello.bogapp",
            HELLO_BYTECODE,
            BAD_HELLO_APP_HASH,
            "bad-hello-bogos",
            "20.0.0",
        );
        assert!(!res.hash_match);
        assert!(!res.accepted);
        assert!(res.rejected);
        assert!(!res.execution_started);
        assert_eq!(res.execution_status, "rejected");
    }

    #[test]
    fn test_accepted_app_output_event_exists() {
        let res = load_and_verify_app(
            "/apps/hello.bogapp",
            HELLO_BYTECODE,
            HELLO_APP_HASH,
            "hello-bogos",
            "20.0.0",
        );
        assert_eq!(res.output_event, "hello_from_verified_bogos_app");
    }

    #[test]
    fn test_rejected_app_output_event_is_none() {
        let res = load_and_verify_app(
            "/apps/bad-hello.bogapp",
            HELLO_BYTECODE,
            BAD_HELLO_APP_HASH,
            "bad-hello-bogos",
            "20.0.0",
        );
        assert_eq!(res.output_event, "none");
    }

    #[test]
    fn test_shell_command_parser_for_required_commands() {
        assert_eq!(ShellCommand::parse("help"), ShellCommand::Help);
        assert_eq!(ShellCommand::parse("status"), ShellCommand::Status);
        assert_eq!(ShellCommand::parse("ls"), ShellCommand::Ls);
        assert_eq!(ShellCommand::parse("clear"), ShellCommand::Clear);
        assert_eq!(ShellCommand::parse("cat /system/status"), ShellCommand::CatSystemStatus);
        assert_eq!(ShellCommand::parse("cat /receipts/last"), ShellCommand::CatReceiptsLast);
        assert_eq!(ShellCommand::parse("run hello"), ShellCommand::Run("hello"));
        assert_eq!(ShellCommand::parse("run bad-hello"), ShellCommand::Run("bad-hello"));
        assert_eq!(ShellCommand::parse("run other"), ShellCommand::Run("other"));
        assert_eq!(ShellCommand::parse("cat /other/path"), ShellCommand::Cat("/other/path"));
        assert_eq!(ShellCommand::parse("unknown_command"), ShellCommand::Unknown);
    }

    #[test]
    fn test_receipt_result_structure_is_deterministic() {
        let res = AppLoaderResult {
            app_name: "hello-bogos",
            app_version: "20.0.0",
            app_path: "/apps/hello.bogapp",
            app_present: true,
            hash_expected: HELLO_APP_HASH,
            hash_actual: HELLO_APP_HASH,
            hash_match: true,
            accepted: true,
            rejected: false,
            execution_started: true,
            execution_status: "completed",
            halted: true,
            output_event: "hello_from_verified_bogos_app",
        };
        let mut buf = [0u8; 1024];
        let receipt_str = format_app_receipt("run hello", &res, &mut buf);
        let expected = "COMMAND=run hello\n\
                        APP_PATH=/apps/hello.bogapp\n\
                        APP_NAME=hello-bogos\n\
                        APP_VERSION=20.0.0\n\
                        APP_PRESENT=true\n\
                        APP_HASH_MATCH=true\n\
                        APP_ACCEPTED=true\n\
                        APP_REJECTED=false\n\
                        APP_EXECUTION_STARTED=true\n\
                        APP_OUTPUT_EVENT=hello_from_verified_bogos_app\n\
                        APP_EXECUTION_STATUS=completed\n\
                        APP_HALTED=true";
        assert_eq!(receipt_str, expected);
    }
}


