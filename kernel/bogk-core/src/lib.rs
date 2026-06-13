#![no_std]

#[cfg(test)]
extern crate std;

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
    let mut w = [0u32; 64];
    for j in 0..16 {
        w[j] = u32::from_be_bytes([
            block[j * 4],
            block[j * 4 + 1],
            block[j * 4 + 2],
            block[j * 4 + 3],
        ]);
    }
    for j in 16..64 {
        let s0 = w[j - 15].rotate_right(7) ^ w[j - 15].rotate_right(18) ^ (w[j - 15] >> 3);
        let s1 = w[j - 2].rotate_right(17) ^ w[j - 2].rotate_right(19) ^ (w[j - 2] >> 10);
        w[j] = w[j - 16]
            .wrapping_add(s0)
            .wrapping_add(w[j - 7])
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
            .wrapping_add(w[j]);
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
        path: "/system/processes",
        kind: "system",
        byte_length: 0,
        expected_hash: None,
        app_manifest_reference: None,
    },
    PseudoFileEntry {
        path: "/system/scheduler",
        kind: "system",
        byte_length: 0,
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

pub type ProcessId = u32;

pub const MAX_PROCESSES: usize = 32;
pub const MAX_PROCESS_PATH: usize = 128;

#[repr(C)]
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub struct SavedContext {
    pub eip: u32,
    pub esp: u32,
    pub eflags: u32,
    pub eax: u32,
    pub ebx: u32,
    pub ecx: u32,
    pub edx: u32,
    pub esi: u32,
    pub edi: u32,
    pub ebp: u32,
    pub valid: bool,
}

impl SavedContext {
    pub const fn empty() -> Self {
        Self {
            eip: 0,
            esp: 0,
            eflags: 0,
            eax: 0,
            ebx: 0,
            ecx: 0,
            edx: 0,
            esi: 0,
            edi: 0,
            ebp: 0,
            valid: false,
        }
    }
}

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub struct ProcessExecutionMemory {
    pub code_base: u32,
    pub code_length: usize,
    pub stack_base: u32,
    pub stack_top: u32,
    pub slot_index: usize,
    pub assigned: bool,
}

impl ProcessExecutionMemory {
    pub const fn unassigned() -> Self {
        Self {
            code_base: 0,
            code_length: 0,
            stack_base: 0,
            stack_top: 0,
            slot_index: 0,
            assigned: false,
        }
    }
}

pub type AddressSpaceId = u32;

pub const PAGE_SIZE: u32 = 4096;

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum AddressSpaceVerificationStatus {
    Unassigned,
    MetadataVerified,
    KernelPagingEnabled,
    PerProcessCr3IdentityMap,
    KernelProtectedProcessIdentity,
    PrivateUserMappings,
    HardwareVerified,
    Faulted,
}

impl AddressSpaceVerificationStatus {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Unassigned => "unassigned",
            Self::MetadataVerified => "metadata_verified",
            Self::KernelPagingEnabled => "kernel_paging_enabled",
            Self::PerProcessCr3IdentityMap => "per_process_cr3_identity_map",
            Self::KernelProtectedProcessIdentity => "kernel_protected_process_identity",
            Self::PrivateUserMappings => "private_user_mappings",
            Self::HardwareVerified => "verified",
            Self::Faulted => "faulted",
        }
    }
}

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum PageDirectoryKind {
    Unassigned,
    GlobalShared,
    PerProcessIdentity,
    PerProcessProtectedKernel,
    PerProcessIsolated,
}

impl PageDirectoryKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Unassigned => "unassigned",
            Self::GlobalShared => "global_shared",
            Self::PerProcessIdentity => "per_process_identity",
            Self::PerProcessProtectedKernel => "per_process_protected_kernel",
            Self::PerProcessIsolated => "per_process_isolated",
        }
    }
}

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub struct AddressSpaceMetadata {
    pub id: AddressSpaceId,
    pub cr3: u32,
    pub page_directory_kind: PageDirectoryKind,
    pub user_code_base: u32,
    pub user_code_pages: usize,
    pub user_code_phys_base: u32,
    pub user_stack_base: u32,
    pub user_stack_pages: usize,
    pub user_stack_phys_base: u32,
    pub kernel_mapping_base: u32,
    pub kernel_mapping_pages: usize,
    pub kernel_supervisor_only: bool,
    pub paging_enabled: bool,
    pub process_isolation_enforced: bool,
    pub kernel_protection_enforced: bool,
    pub user_code_user_accessible: bool,
    pub user_stack_user_accessible: bool,
    pub private_user_mappings: bool,
    pub writable_code_blocked: bool,
    pub cross_process_isolation_enforced: bool,
    pub address_space_hash: [u8; 32],
    pub verification_status: AddressSpaceVerificationStatus,
    pub fault_count: usize,
}

impl AddressSpaceMetadata {
    pub const fn unassigned() -> Self {
        Self {
            id: 0,
            cr3: 0,
            page_directory_kind: PageDirectoryKind::Unassigned,
            user_code_base: 0,
            user_code_pages: 0,
            user_code_phys_base: 0,
            user_stack_base: 0,
            user_stack_pages: 0,
            user_stack_phys_base: 0,
            kernel_mapping_base: 0,
            kernel_mapping_pages: 0,
            kernel_supervisor_only: false,
            paging_enabled: false,
            process_isolation_enforced: false,
            kernel_protection_enforced: false,
            user_code_user_accessible: false,
            user_stack_user_accessible: false,
            private_user_mappings: false,
            writable_code_blocked: false,
            cross_process_isolation_enforced: false,
            address_space_hash: [0; 32],
            verification_status: AddressSpaceVerificationStatus::Unassigned,
            fault_count: 0,
        }
    }

    pub fn scaffolded(
        id: AddressSpaceId,
        memory: ProcessExecutionMemory,
        app_hash: [u8; 32],
    ) -> Self {
        let mut metadata = Self {
            id,
            cr3: 0,
            page_directory_kind: PageDirectoryKind::Unassigned,
            user_code_base: memory.code_base,
            user_code_pages: pages_for(memory.code_length),
            user_code_phys_base: memory.code_base,
            user_stack_base: memory.stack_base,
            user_stack_pages: pages_for(memory.stack_top.saturating_sub(memory.stack_base) as usize),
            user_stack_phys_base: memory.stack_base,
            kernel_mapping_base: 0,
            kernel_mapping_pages: 0,
            kernel_supervisor_only: false,
            paging_enabled: false,
            process_isolation_enforced: false,
            kernel_protection_enforced: false,
            user_code_user_accessible: false,
            user_stack_user_accessible: false,
            private_user_mappings: false,
            writable_code_blocked: false,
            cross_process_isolation_enforced: false,
            address_space_hash: [0; 32],
            verification_status: AddressSpaceVerificationStatus::MetadataVerified,
            fault_count: 0,
        };
        metadata.address_space_hash = metadata.compute_hash(app_hash);
        metadata
    }

    pub fn compute_hash(&self, app_hash: [u8; 32]) -> [u8; 32] {
        let mut canonical = [0u8; 85];
        canonical[0..4].copy_from_slice(&self.id.to_be_bytes());
        canonical[4..8].copy_from_slice(&self.cr3.to_be_bytes());
        canonical[8..12].copy_from_slice(&self.user_code_base.to_be_bytes());
        canonical[12..16].copy_from_slice(&(self.user_code_pages as u32).to_be_bytes());
        canonical[16..20].copy_from_slice(&self.user_stack_base.to_be_bytes());
        canonical[20..24].copy_from_slice(&(self.user_stack_pages as u32).to_be_bytes());
        canonical[24..28].copy_from_slice(&self.kernel_mapping_base.to_be_bytes());
        canonical[28..32].copy_from_slice(&(self.kernel_mapping_pages as u32).to_be_bytes());
        canonical[32] = self.kernel_supervisor_only as u8;
        canonical[33] = self.paging_enabled as u8;
        canonical[34] = self.process_isolation_enforced as u8;
        canonical[35] = self.kernel_protection_enforced as u8;
        canonical[36..40].copy_from_slice(&(self.page_directory_kind as u32).to_be_bytes());
        canonical[40] = self.user_code_user_accessible as u8;
        canonical[41] = self.user_stack_user_accessible as u8;
        canonical[42] = self.writable_code_blocked as u8;
        canonical[43] = self.cross_process_isolation_enforced as u8;
        canonical[44] = self.private_user_mappings as u8;
        canonical[45..49].copy_from_slice(&self.user_code_phys_base.to_be_bytes());
        canonical[49..53].copy_from_slice(&self.user_stack_phys_base.to_be_bytes());
        canonical[53..85].copy_from_slice(&app_hash);
        sha256(&canonical)
    }

    pub fn mark_global_paging(&mut self, kernel_cr3: u32, app_hash: [u8; 32]) -> bool {
        if kernel_cr3 == 0
            || self.verification_status != AddressSpaceVerificationStatus::MetadataVerified
        {
            return false;
        }
        self.cr3 = kernel_cr3;
        self.page_directory_kind = PageDirectoryKind::GlobalShared;
        self.paging_enabled = true;
        self.verification_status = AddressSpaceVerificationStatus::KernelPagingEnabled;
        self.address_space_hash = self.compute_hash(app_hash);
        true
    }

    pub fn mark_kernel_protected_identity(&mut self, cr3: u32, app_hash: [u8; 32]) -> bool {
        if cr3 == 0
            || self.verification_status
                != AddressSpaceVerificationStatus::PerProcessCr3IdentityMap
        {
            return false;
        }
        self.cr3 = cr3;
        self.page_directory_kind = PageDirectoryKind::PerProcessProtectedKernel;
        self.kernel_supervisor_only = true;
        self.paging_enabled = true;
        self.process_isolation_enforced = false;
        self.kernel_protection_enforced = true;
        self.user_code_user_accessible = true;
        self.user_stack_user_accessible = true;
        self.private_user_mappings = false;
        self.writable_code_blocked = false;
        self.cross_process_isolation_enforced = false;
        self.verification_status = AddressSpaceVerificationStatus::KernelProtectedProcessIdentity;
        self.address_space_hash = self.compute_hash(app_hash);
        true
    }

    pub fn mark_private_user_mappings(&mut self, cr3: u32, app_hash: [u8; 32]) -> bool {
        if cr3 == 0
            || self.verification_status
                != AddressSpaceVerificationStatus::KernelProtectedProcessIdentity
        {
            return false;
        }
        self.cr3 = cr3;
        self.page_directory_kind = PageDirectoryKind::PerProcessIsolated;
        self.kernel_supervisor_only = true;
        self.paging_enabled = true;
        self.process_isolation_enforced = false;
        self.kernel_protection_enforced = true;
        self.user_code_user_accessible = true;
        self.user_stack_user_accessible = true;
        self.private_user_mappings = true;
        self.writable_code_blocked = false;
        self.cross_process_isolation_enforced = false;
        self.verification_status = AddressSpaceVerificationStatus::PrivateUserMappings;
        self.address_space_hash = self.compute_hash(app_hash);
        true
    }

    pub fn mark_process_isolation_proven(&mut self, app_hash: [u8; 32]) -> bool {
        if !self.private_user_mappings || !self.kernel_protection_enforced {
            return false;
        }
        self.process_isolation_enforced = true;
        self.writable_code_blocked = true;
        self.cross_process_isolation_enforced = true;
        if self.verification_status != AddressSpaceVerificationStatus::Faulted {
            self.verification_status = AddressSpaceVerificationStatus::HardwareVerified;
        }
        self.address_space_hash = self.compute_hash(app_hash);
        true
    }

    pub fn mark_per_process_identity(&mut self, cr3: u32, app_hash: [u8; 32]) -> bool {
        if cr3 == 0
            || (self.verification_status != AddressSpaceVerificationStatus::MetadataVerified
                && self.verification_status
                    != AddressSpaceVerificationStatus::KernelPagingEnabled)
        {
            return false;
        }
        self.cr3 = cr3;
        self.page_directory_kind = PageDirectoryKind::PerProcessIdentity;
        self.paging_enabled = true;
        self.process_isolation_enforced = false;
        self.verification_status = AddressSpaceVerificationStatus::PerProcessCr3IdentityMap;
        self.address_space_hash = self.compute_hash(app_hash);
        true
    }
}

pub const fn pages_for(byte_length: usize) -> usize {
    byte_length.saturating_add(PAGE_SIZE as usize - 1) / PAGE_SIZE as usize
}

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum ProcessState {
    Created,
    Verified,
    Ready,
    Scheduled,
    Running,
    Yielded,
    Preempted,
    Exited,
    Blocked,
    Rejected,
    Panicked,
}

impl ProcessState {
    pub const fn as_str(self) -> &'static str {
        match self {
            ProcessState::Created => "CREATED",
            ProcessState::Verified => "VERIFIED",
            ProcessState::Ready => "READY",
            ProcessState::Scheduled => "SCHEDULED",
            ProcessState::Running => "RUNNING",
            ProcessState::Yielded => "YIELDED",
            ProcessState::Preempted => "PREEMPTED",
            ProcessState::Exited => "EXITED",
            ProcessState::Blocked => "BLOCKED",
            ProcessState::Rejected => "REJECTED",
            ProcessState::Panicked => "PANICKED",
        }
    }
}

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum ProcessExitStatus {
    None,
    Exited(i32),
    Blocked(i32, &'static str),
    Rejected(&'static str),
    Panicked(&'static str),
}

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub struct ProcessRecord {
    pub pid: ProcessId,
    path: [u8; MAX_PROCESS_PATH],
    path_len: usize,
    pub app_hash: Option<[u8; 32]>,
    pub state: ProcessState,
    pub exit_status: ProcessExitStatus,
    pub context: SavedContext,
    pub execution_memory: ProcessExecutionMemory,
    pub address_space: AddressSpaceMetadata,
    pub dynamic_loader_admitted: bool,
    pub state_created: bool,
    pub state_verified: bool,
    pub state_ready: bool,
    pub state_scheduled: bool,
    pub state_running: bool,
    pub state_yielded: bool,
    pub state_preempted: bool,
    pub state_exited: bool,
    pub state_blocked: bool,
    pub state_rejected: bool,
    pub state_panicked: bool,
}

impl ProcessRecord {
    pub fn new(pid: ProcessId, app_path: &str) -> Self {
        let mut path = [0u8; MAX_PROCESS_PATH];
        let path_len = app_path.len().min(MAX_PROCESS_PATH);
        path[..path_len].copy_from_slice(&app_path.as_bytes()[..path_len]);
        Self {
            pid,
            path,
            path_len,
            app_hash: None,
            state: ProcessState::Created,
            exit_status: ProcessExitStatus::None,
            context: SavedContext::empty(),
            execution_memory: ProcessExecutionMemory::unassigned(),
            address_space: AddressSpaceMetadata::unassigned(),
            dynamic_loader_admitted: false,
            state_created: true,
            state_verified: false,
            state_ready: false,
            state_scheduled: false,
            state_running: false,
            state_yielded: false,
            state_preempted: false,
            state_exited: false,
            state_blocked: false,
            state_rejected: false,
            state_panicked: false,
        }
    }

    pub fn app_path(&self) -> &str {
        core::str::from_utf8(&self.path[..self.path_len]).unwrap_or("")
    }

    pub fn mark_dynamic_loader_admitted(&mut self) {
        self.dynamic_loader_admitted = true;
    }

    pub fn mark_verified(&mut self, app_hash: [u8; 32]) -> bool {
        if self.state != ProcessState::Created {
            return false;
        }
        self.app_hash = Some(app_hash);
        self.state = ProcessState::Verified;
        self.state_verified = true;
        true
    }

    pub fn mark_running(&mut self) -> bool {
        if self.state != ProcessState::Verified && self.state != ProcessState::Scheduled {
            return false;
        }
        self.state = ProcessState::Running;
        self.state_running = true;
        true
    }

    pub fn mark_ready(&mut self) -> bool {
        if self.state != ProcessState::Verified && self.state != ProcessState::Yielded && self.state != ProcessState::Preempted {
            return false;
        }
        self.state = ProcessState::Ready;
        self.state_ready = true;
        true
    }

    pub fn mark_scheduled(&mut self) -> bool {
        if self.state != ProcessState::Ready {
            return false;
        }
        self.state = ProcessState::Scheduled;
        self.state_scheduled = true;
        true
    }

    pub fn mark_yielded(&mut self) -> bool {
        if self.state != ProcessState::Running {
            return false;
        }
        self.state = ProcessState::Yielded;
        self.state_yielded = true;
        true
    }

    pub fn mark_preempted(&mut self) -> bool {
        if self.state != ProcessState::Running {
            return false;
        }
        self.state = ProcessState::Preempted;
        self.state_preempted = true;
        true
    }

    pub fn save_context(&mut self, context: SavedContext) -> bool {
        if self.state != ProcessState::Running || !context.valid {
            return false;
        }
        self.context = context;
        true
    }

    pub fn assign_execution_memory(&mut self, memory: ProcessExecutionMemory) -> bool {
        if memory.assigned && !self.execution_memory.assigned {
            self.execution_memory = memory;
            true
        } else {
            false
        }
    }

    pub fn assign_scaffolded_address_space(&mut self) -> bool {
        if self.address_space.verification_status != AddressSpaceVerificationStatus::Unassigned
            || !self.execution_memory.assigned
        {
            return false;
        }
        if let Some(app_hash) = self.app_hash {
            self.address_space =
                AddressSpaceMetadata::scaffolded(self.pid, self.execution_memory, app_hash);
            true
        } else {
            false
        }
    }

    pub fn record_page_fault(&mut self) {
        self.address_space.fault_count = self.address_space.fault_count.saturating_add(1);
        self.address_space.verification_status = AddressSpaceVerificationStatus::Faulted;
    }

    pub fn mark_global_paging(&mut self, kernel_cr3: u32) -> bool {
        if let Some(app_hash) = self.app_hash {
            self.address_space.mark_global_paging(kernel_cr3, app_hash)
        } else {
            false
        }
    }

    pub fn mark_per_process_identity(&mut self, cr3: u32) -> bool {
        if let Some(app_hash) = self.app_hash {
            self.address_space.mark_per_process_identity(cr3, app_hash)
        } else {
            false
        }
    }

    pub fn mark_kernel_protected_identity(&mut self, cr3: u32) -> bool {
        if let Some(app_hash) = self.app_hash {
            self.address_space.mark_kernel_protected_identity(cr3, app_hash)
        } else {
            false
        }
    }

    pub fn mark_private_user_mappings(&mut self, cr3: u32) -> bool {
        if let Some(app_hash) = self.app_hash {
            self.address_space.mark_private_user_mappings(cr3, app_hash)
        } else {
            false
        }
    }

    pub fn mark_process_isolation_proven(&mut self) -> bool {
        if let Some(app_hash) = self.app_hash {
            self.address_space.mark_process_isolation_proven(app_hash)
        } else {
            false
        }
    }

    pub fn restore_eligible(&self) -> bool {
        self.state == ProcessState::Scheduled && self.context.valid && self.execution_memory.assigned
    }

    pub fn mark_exited(&mut self, code: i32) -> bool {
        if self.state != ProcessState::Running {
            return false;
        }
        self.state = ProcessState::Exited;
        self.exit_status = ProcessExitStatus::Exited(code);
        self.state_exited = true;
        true
    }

    pub fn mark_blocked(&mut self, code: i32, reason: &'static str) -> bool {
        if self.state != ProcessState::Running {
            return false;
        }
        self.state = ProcessState::Blocked;
        self.exit_status = ProcessExitStatus::Blocked(code, reason);
        self.state_blocked = true;
        true
    }

    pub fn mark_rejected(&mut self, reason: &'static str) -> bool {
        if self.state != ProcessState::Created && self.state != ProcessState::Verified {
            return false;
        }
        self.state = ProcessState::Rejected;
        self.exit_status = ProcessExitStatus::Rejected(reason);
        self.state_rejected = true;
        true
    }

    pub fn mark_panicked(&mut self, reason: &'static str) -> bool {
        if self.state != ProcessState::Running {
            return false;
        }
        self.state = ProcessState::Panicked;
        self.exit_status = ProcessExitStatus::Panicked(reason);
        self.state_panicked = true;
        true
    }

    pub const fn execution_status(&self) -> &'static str {
        match self.state {
            ProcessState::Exited => "completed",
            ProcessState::Blocked => "blocked",
            ProcessState::Rejected => "rejected",
            ProcessState::Panicked => "failed",
            ProcessState::Yielded | ProcessState::Ready | ProcessState::Scheduled | ProcessState::Preempted => "yielded",
            _ => "failed",
        }
    }

    pub const fn exit_code(&self) -> i32 {
        match self.exit_status {
            ProcessExitStatus::Exited(code) | ProcessExitStatus::Blocked(code, _) => code,
            _ => -1,
        }
    }

    pub const fn block_reason(&self) -> &'static str {
        match self.exit_status {
            ProcessExitStatus::Blocked(_, reason)
            | ProcessExitStatus::Rejected(reason)
            | ProcessExitStatus::Panicked(reason) => reason,
            _ => "none",
        }
    }
}

pub const SCHEDULER_POLICY: &str = "fifo_round_robin_ready";

#[derive(Debug, PartialEq, Eq)]
pub struct Scheduler {
    pub current_pid: Option<ProcessId>,
    run_queue: [Option<ProcessId>; MAX_PROCESSES],
    run_queue_len: usize,
    pub schedule_step: usize,
    pub last_selected_pid: Option<ProcessId>,
    pub timer_ticks: usize,
    pub quantum_ticks: usize,
    pub preemption_count: usize,
    pub last_preempted_pid: Option<ProcessId>,
}

impl Scheduler {
    pub const fn new() -> Self {
        Self {
            current_pid: None,
            run_queue: [None; MAX_PROCESSES],
            run_queue_len: 0,
            schedule_step: 0,
            last_selected_pid: None,
            timer_ticks: 0,
            quantum_ticks: 0,
            preemption_count: 0,
            last_preempted_pid: None,
        }
    }

    pub const fn policy(&self) -> &'static str {
        SCHEDULER_POLICY
    }

    pub const fn run_queue_len(&self) -> usize {
        self.run_queue_len
    }

    pub fn queued_pids(&self) -> impl Iterator<Item = ProcessId> + '_ {
        self.run_queue[..self.run_queue_len].iter().flatten().copied()
    }

    pub fn enqueue(&mut self, pid: ProcessId, table: &ProcessTable) -> bool {
        if self.run_queue_len == MAX_PROCESSES
            || self.queued_pids().any(|queued| queued == pid)
            || table.get(pid).map(|record| record.state) != Some(ProcessState::Ready)
        {
            return false;
        }
        self.run_queue[self.run_queue_len] = Some(pid);
        self.run_queue_len += 1;
        true
    }

    pub fn select_next(&mut self, table: &mut ProcessTable) -> Option<ProcessId> {
        self.schedule_step = self.schedule_step.saturating_add(1);
        self.current_pid = None;
        while self.run_queue_len > 0 {
            let pid = self.run_queue[0].take().unwrap();
            for index in 1..self.run_queue_len {
                self.run_queue[index - 1] = self.run_queue[index];
            }
            self.run_queue_len -= 1;
            self.run_queue[self.run_queue_len] = None;
            if let Some(record) = table.get_mut(pid) {
                if record.mark_scheduled() {
                    self.current_pid = Some(pid);
                    self.last_selected_pid = Some(pid);
                    return Some(pid);
                }
            }
        }
        None
    }

    pub fn finish_current(&mut self) {
        self.current_pid = None;
    }
}

#[derive(Debug, PartialEq, Eq)]
pub struct ProcessTable {
    records: [Option<ProcessRecord>; MAX_PROCESSES],
    len: usize,
    next_pid: ProcessId,
}

impl ProcessTable {
    pub const fn new() -> Self {
        Self {
            records: [None; MAX_PROCESSES],
            len: 0,
            next_pid: 1,
        }
    }

    pub fn create(&mut self, app_path: &str) -> Option<ProcessId> {
        if self.len == MAX_PROCESSES {
            return None;
        }
        let pid = self.next_pid;
        self.next_pid = self.next_pid.saturating_add(1);
        self.records[self.len] = Some(ProcessRecord::new(pid, app_path));
        self.len += 1;
        Some(pid)
    }

    pub const fn len(&self) -> usize {
        self.len
    }

    pub const fn is_empty(&self) -> bool {
        self.len == 0
    }

    pub fn get(&self, pid: ProcessId) -> Option<&ProcessRecord> {
        self.records[..self.len]
            .iter()
            .flatten()
            .find(|record| record.pid == pid)
    }

    pub fn get_mut(&mut self, pid: ProcessId) -> Option<&mut ProcessRecord> {
        self.records[..self.len]
            .iter_mut()
            .flatten()
            .find(|record| record.pid == pid)
    }

    pub fn records(&self) -> impl Iterator<Item = &ProcessRecord> {
        self.records[..self.len].iter().flatten()
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

    pub fn write_i32(&mut self, n: i32) {
        if n < 0 {
            self.write_str("-");
            self.write_usize(n.unsigned_abs() as usize);
        } else {
            self.write_usize(n as usize);
        }
    }

    pub fn write_hash(&mut self, hash: &[u8; 32]) {
        for byte in hash {
            let high = byte >> 4;
            let low = byte & 0x0f;
            self.write_hex_nibble(high);
            self.write_hex_nibble(low);
        }
    }

    fn write_hex_nibble(&mut self, nibble: u8) {
        let byte = if nibble < 10 {
            b'0' + nibble
        } else {
            b'a' + nibble - 10
        };
        self.write_str(core::str::from_utf8(&[byte]).unwrap_or("?"));
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
    Spawn(&'a str),
    Load(&'a str),
    Ps,
    RunQueue,
    SchedStep,
    SchedDemo,
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
        } else if trimmed == "ps" {
            ShellCommand::Ps
        } else if trimmed == "runq" {
            ShellCommand::RunQueue
        } else if trimmed == "sched step" {
            ShellCommand::SchedStep
        } else if trimmed == "sched demo" {
            ShellCommand::SchedDemo
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
        } else if trimmed.starts_with("spawn ") {
            ShellCommand::Spawn(trimmed["spawn ".len()..].trim())
        } else if trimmed.starts_with("load ") {
            ShellCommand::Load(trimmed["load ".len()..].trim())
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

pub fn format_process_table<'a>(table: &ProcessTable, buf: &'a mut [u8]) -> &'a str {
    let mut writer = BufferWriter::new(buf);
    writer.write_str("BOGOS PROCESS TABLE\n");
    writer.write_str("PROCESS_COUNT=");
    writer.write_usize(table.len());
    for record in table.records() {
        writer.write_str("\nPID=");
        writer.write_usize(record.pid as usize);
        writer.write_str(" APP_PATH=");
        writer.write_str(record.app_path());
        writer.write_str(" APP_HASH=");
        if let Some(hash) = record.app_hash {
            writer.write_hash(&hash);
        } else {
            writer.write_str("none");
        }
        writer.write_str(" STATE=");
        writer.write_str(record.state.as_str());
        writer.write_str(" EXIT_CODE=");
        writer.write_i32(record.exit_code());
        writer.write_str(" BLOCK_REASON=");
        writer.write_str(record.block_reason());
        writer.write_str(" EXECUTION_STATUS=");
        writer.write_str(record.execution_status());
        writer.write_str(" ADDRESS_SPACE_ID=");
        writer.write_usize(record.address_space.id as usize);
        writer.write_str(" ISOLATION_STATUS=");
        writer.write_str(record.address_space.verification_status.as_str());
        writer.write_str(" FAULT_COUNT=");
        writer.write_usize(record.address_space.fault_count);
    }
    writer.as_str()
}

pub fn format_scheduler<'a>(scheduler: &Scheduler, buf: &'a mut [u8]) -> &'a str {
    let mut writer = BufferWriter::new(buf);
    writer.write_str("BOGOS SCHEDULER\ncurrent_pid=");
    write_optional_pid(&mut writer, scheduler.current_pid);
    writer.write_str("\nrun_queue=");
    write_run_queue(&mut writer, scheduler);
    writer.write_str("\nselected_policy=");
    writer.write_str(scheduler.policy());
    writer.write_str("\nschedule_step=");
    writer.write_usize(scheduler.schedule_step);
    writer.write_str("\nlast_selected_pid=");
    write_optional_pid(&mut writer, scheduler.last_selected_pid);
    writer.write_str("\nquantum_ticks=");
    writer.write_usize(scheduler.quantum_ticks);
    writer.write_str("\ntimer_ticks=");
    writer.write_usize(scheduler.timer_ticks);
    writer.write_str("\npreemption_count=");
    writer.write_usize(scheduler.preemption_count);
    writer.write_str("\nlast_preempted_pid=");
    write_optional_pid(&mut writer, scheduler.last_preempted_pid);
    writer.as_str()
}

pub fn write_optional_pid(writer: &mut BufferWriter<'_>, pid: Option<ProcessId>) {
    if let Some(pid) = pid {
        writer.write_usize(pid as usize);
    } else {
        writer.write_str("none");
    }
}

pub fn write_run_queue(writer: &mut BufferWriter<'_>, scheduler: &Scheduler) {
    writer.write_str("[");
    for (index, pid) in scheduler.queued_pids().enumerate() {
        if index > 0 {
            writer.write_str(",");
        }
        writer.write_usize(pid as usize);
    }
    writer.write_str("]");
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
    process_table_buf: &'a str,
    scheduler_buf: &'a str,
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
        "/system/processes" => Some(process_table_buf.as_bytes()),
        "/system/scheduler" => Some(scheduler_buf.as_bytes()),
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
        writer.write_str("/system/processes\n");
        writer.write_str("/system/scheduler\n");
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
    fn test_sha256_parallel_calls_do_not_share_mutable_schedule_state() {
        let expected = sha256(b"BOGBIN-v31-parallel-verifier-regression");
        let mut workers = std::vec::Vec::new();
        for _ in 0..8 {
            workers.push(std::thread::spawn(move || {
                for _ in 0..1000 {
                    assert_eq!(
                        sha256(b"BOGBIN-v31-parallel-verifier-regression"),
                        expected
                    );
                }
            }));
        }
        for worker in workers {
            worker.join().unwrap();
        }
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
            "/system/processes",
            "/system/scheduler",
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
                        /system/processes\n\
                        /system/scheduler\n\
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
        assert_eq!(ShellCommand::parse("spawn other"), ShellCommand::Spawn("other"));
        assert_eq!(ShellCommand::parse("load other"), ShellCommand::Load("other"));
        assert_eq!(ShellCommand::parse("ps"), ShellCommand::Ps);
        assert_eq!(ShellCommand::parse("runq"), ShellCommand::RunQueue);
        assert_eq!(ShellCommand::parse("sched step"), ShellCommand::SchedStep);
        assert_eq!(ShellCommand::parse("sched demo"), ShellCommand::SchedDemo);
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

    #[test]
    fn test_process_completed_transition_sequence() {
        let mut table = ProcessTable::new();
        let pid = table.create("/apps/hello.bogapp").unwrap();
        assert_eq!(pid, 1);
        let record = table.get_mut(pid).unwrap();
        assert!(record.mark_verified(HELLO_APP_HASH));
        assert!(record.mark_running());
        assert!(record.mark_exited(0));
        assert_eq!(record.state, ProcessState::Exited);
        assert!(record.state_created);
        assert!(record.state_verified);
        assert!(record.state_running);
        assert!(record.state_exited);
        assert_eq!(record.execution_status(), "completed");
    }

    #[test]
    fn test_process_rejects_invalid_transition() {
        let mut record = ProcessRecord::new(1, "/apps/bad.bogapp");
        assert!(!record.mark_running());
        assert!(!record.mark_exited(0));
        assert!(record.mark_rejected("not_found_or_unverified"));
        assert!(!record.mark_verified([0u8; 32]));
        assert_eq!(record.state, ProcessState::Rejected);
    }

    #[test]
    fn test_process_blocked_transition_and_deterministic_listing() {
        let mut table = ProcessTable::new();
        let pid = table.create("/apps/bad_app.bogapp").unwrap();
        let record = table.get_mut(pid).unwrap();
        assert!(record.mark_verified([0xabu8; 32]));
        assert!(record.mark_running());
        assert!(record.mark_blocked(1, "gpf"));

        let mut buf = [0u8; 512];
        let listing = format_process_table(&table, &mut buf);
        assert!(listing.starts_with("BOGOS PROCESS TABLE\nPROCESS_COUNT=1\nPID=1 "));
        assert!(listing.contains("STATE=BLOCKED"));
        assert!(listing.contains("BLOCK_REASON=gpf"));
        assert!(listing.contains("EXECUTION_STATUS=blocked"));
        assert!(listing.ends_with("FAULT_COUNT=0"));
    }

    #[test]
    fn test_process_ids_are_monotonic_and_table_is_bounded() {
        let mut table = ProcessTable::new();
        for expected_pid in 1..=MAX_PROCESSES as u32 {
            assert_eq!(table.create("/apps/test.bogapp"), Some(expected_pid));
        }
        assert_eq!(table.create("/apps/overflow.bogapp"), None);
    }

    #[test]
    fn test_dynamic_loader_admission_is_explicit() {
        let mut record = ProcessRecord::new(1, "/apps/dynamic.bogapp");
        assert!(!record.dynamic_loader_admitted);
        record.mark_dynamic_loader_admitted();
        assert!(record.dynamic_loader_admitted);
    }

    #[test]
    fn test_scheduler_fifo_round_robin_selection() {
        let mut table = ProcessTable::new();
        let first = table.create("/apps/first.bogapp").unwrap();
        let second = table.create("/apps/second.bogapp").unwrap();
        for pid in [first, second] {
            let record = table.get_mut(pid).unwrap();
            assert!(record.mark_verified([pid as u8; 32]));
            assert!(record.mark_ready());
        }
        let mut scheduler = Scheduler::new();
        assert!(scheduler.enqueue(first, &table));
        assert!(scheduler.enqueue(second, &table));
        assert_eq!(scheduler.select_next(&mut table), Some(first));
        assert_eq!(table.get(first).unwrap().state, ProcessState::Scheduled);
        scheduler.finish_current();
        assert_eq!(scheduler.select_next(&mut table), Some(second));
        assert_eq!(scheduler.schedule_step, 2);
    }

    #[test]
    fn test_scheduler_yield_requeues_at_tail() {
        let mut table = ProcessTable::new();
        let first = table.create("/apps/first.bogapp").unwrap();
        let second = table.create("/apps/second.bogapp").unwrap();
        for pid in [first, second] {
            let record = table.get_mut(pid).unwrap();
            assert!(record.mark_verified([pid as u8; 32]));
            assert!(record.mark_ready());
        }
        let mut scheduler = Scheduler::new();
        assert!(scheduler.enqueue(first, &table));
        assert!(scheduler.enqueue(second, &table));
        assert_eq!(scheduler.select_next(&mut table), Some(first));
        let record = table.get_mut(first).unwrap();
        assert!(record.mark_running());
        assert!(record.mark_yielded());
        assert!(record.mark_ready());
        scheduler.finish_current();
        assert!(scheduler.enqueue(first, &table));
        assert_eq!(scheduler.select_next(&mut table), Some(second));
        assert_eq!(scheduler.select_next(&mut table), Some(first));
    }

    #[test]
    fn test_scheduler_excludes_terminal_processes() {
        let mut table = ProcessTable::new();
        let blocked = table.create("/apps/blocked.bogapp").unwrap();
        let rejected = table.create("/apps/rejected.bogapp").unwrap();
        let exited = table.create("/apps/exited.bogapp").unwrap();
        let panicked = table.create("/apps/panicked.bogapp").unwrap();
        {
            let record = table.get_mut(blocked).unwrap();
            assert!(record.mark_verified([1; 32]));
            assert!(record.mark_running());
            assert!(record.mark_blocked(1, "gpf"));
        }
        assert!(table.get_mut(rejected).unwrap().mark_rejected("missing"));
        {
            let record = table.get_mut(exited).unwrap();
            assert!(record.mark_verified([2; 32]));
            assert!(record.mark_running());
            assert!(record.mark_exited(0));
        }
        {
            let record = table.get_mut(panicked).unwrap();
            assert!(record.mark_verified([3; 32]));
            assert!(record.mark_running());
            assert!(record.mark_panicked("process_panic"));
        }
        let mut scheduler = Scheduler::new();
        assert!(!scheduler.enqueue(blocked, &table));
        assert!(!scheduler.enqueue(rejected, &table));
        assert!(!scheduler.enqueue(exited, &table));
        assert!(!scheduler.enqueue(panicked, &table));
        assert_eq!(scheduler.select_next(&mut table), None);
    }

    #[test]
    fn test_scheduler_format_is_deterministic() {
        let mut table = ProcessTable::new();
        let pid = table.create("/apps/ready.bogapp").unwrap();
        assert!(table.get_mut(pid).unwrap().mark_verified([3; 32]));
        assert!(table.get_mut(pid).unwrap().mark_ready());
        let mut scheduler = Scheduler::new();
        assert!(scheduler.enqueue(pid, &table));
        let mut buf = [0u8; 256];
        assert_eq!(
            format_scheduler(&scheduler, &mut buf),
            "BOGOS SCHEDULER\ncurrent_pid=none\nrun_queue=[1]\nselected_policy=fifo_round_robin_ready\nschedule_step=0\nlast_selected_pid=none\nquantum_ticks=0\ntimer_ticks=0\npreemption_count=0\nlast_preempted_pid=none"
        );
    }

    #[test]
    fn test_saved_context_requires_running_process_and_valid_context() {
        let mut record = ProcessRecord::new(1, "/apps/context.bogapp");
        let mut context = SavedContext::empty();
        context.eip = 0x1234;
        context.esp = 0x5678;
        context.valid = true;
        assert!(!record.save_context(context));
        assert!(record.mark_verified([4; 32]));
        assert!(record.mark_ready());
        assert!(record.mark_scheduled());
        assert!(record.mark_running());
        assert!(record.save_context(context));
        assert_eq!(record.context.eip, 0x1234);
    }

    #[test]
    fn test_restore_eligibility_requires_scheduled_valid_context_and_memory() {
        let mut record = ProcessRecord::new(1, "/apps/context.bogapp");
        assert!(record.mark_verified([5; 32]));
        assert!(record.assign_execution_memory(ProcessExecutionMemory {
            code_base: 0x1000,
            code_length: 64,
            stack_base: 0x2000,
            stack_top: 0x3000,
            slot_index: 0,
            assigned: true,
        }));
        assert!(record.mark_ready());
        assert!(record.mark_scheduled());
        assert!(!record.restore_eligible());
        record.context = SavedContext {
            eip: 0x1010,
            esp: 0x2ff0,
            eflags: 0x200,
            eax: 0,
            ebx: 1,
            ecx: 2,
            edx: 3,
            esi: 4,
            edi: 5,
            ebp: 6,
            valid: true,
        };
        assert!(record.restore_eligible());
        assert!(record.mark_running());
        assert!(!record.restore_eligible());
    }

    #[test]
    fn test_scaffolded_address_space_metadata_is_deterministic_and_not_hardware_verified() {
        let mut record = ProcessRecord::new(7, "/apps/paging.bogapp");
        assert!(record.mark_verified([0x31; 32]));
        assert!(record.assign_execution_memory(ProcessExecutionMemory {
            code_base: 0x0040_1000,
            code_length: 4097,
            stack_base: 0x0080_0000,
            stack_top: 0x0080_1000,
            slot_index: 6,
            assigned: true,
        }));
        assert!(record.assign_scaffolded_address_space());
        assert!(!record.assign_scaffolded_address_space());

        let address_space = record.address_space;
        assert_eq!(address_space.id, 7);
        assert_eq!(address_space.cr3, 0);
        assert_eq!(address_space.user_code_pages, 2);
        assert_eq!(address_space.user_stack_pages, 1);
        assert!(!address_space.kernel_supervisor_only);
        assert!(!address_space.paging_enabled);
        assert_eq!(
            address_space.verification_status,
            AddressSpaceVerificationStatus::MetadataVerified
        );
        assert_ne!(address_space.address_space_hash, [0; 32]);
    }

    #[test]
    fn test_page_fault_count_and_status_are_receipt_visible() {
        let mut record = ProcessRecord::new(8, "/apps/fault.bogapp");
        assert!(record.mark_verified([0x32; 32]));
        assert!(record.assign_execution_memory(ProcessExecutionMemory {
            code_base: 0x0040_0000,
            code_length: 64,
            stack_base: 0x0080_0000,
            stack_top: 0x0080_1000,
            slot_index: 7,
            assigned: true,
        }));
        assert!(record.assign_scaffolded_address_space());
        record.record_page_fault();
        assert_eq!(record.address_space.fault_count, 1);
        assert_eq!(
            record.address_space.verification_status,
            AddressSpaceVerificationStatus::Faulted
        );
    }

    #[test]
    fn test_global_paging_updates_cr3_without_claiming_process_isolation() {
        let mut record = ProcessRecord::new(9, "/apps/global-paging.bogapp");
        assert!(record.mark_verified([0x33; 32]));
        assert!(record.assign_execution_memory(ProcessExecutionMemory {
            code_base: 0x0040_0000,
            code_length: 64,
            stack_base: 0x0080_0000,
            stack_top: 0x0080_1000,
            slot_index: 8,
            assigned: true,
        }));
        assert!(record.assign_scaffolded_address_space());
        let scaffold_hash = record.address_space.address_space_hash;
        assert!(record.mark_global_paging(0x0012_3000));
        assert_eq!(record.address_space.cr3, 0x0012_3000);
        assert!(record.address_space.paging_enabled);
        assert!(!record.address_space.kernel_supervisor_only);
        assert_eq!(
            record.address_space.verification_status,
            AddressSpaceVerificationStatus::KernelPagingEnabled
        );
        assert_ne!(record.address_space.address_space_hash, scaffold_hash);
    }

    #[test]
    fn test_per_process_identity_directory_has_distinct_cr3_without_isolation() {
        let mut record = ProcessRecord::new(10, "/apps/per-process-cr3.bogapp");
        assert!(record.mark_verified([0x34; 32]));
        assert!(record.assign_execution_memory(ProcessExecutionMemory {
            code_base: 0x0040_0000,
            code_length: 64,
            stack_base: 0x0080_0000,
            stack_top: 0x0080_1000,
            slot_index: 9,
            assigned: true,
        }));
        assert!(record.assign_scaffolded_address_space());
        assert!(record.mark_per_process_identity(0x0012_4000));
        assert_eq!(record.address_space.cr3, 0x0012_4000);
        assert_eq!(
            record.address_space.page_directory_kind,
            PageDirectoryKind::PerProcessIdentity
        );
        assert!(!record.address_space.process_isolation_enforced);
        assert_eq!(
            record.address_space.verification_status,
            AddressSpaceVerificationStatus::PerProcessCr3IdentityMap
        );
        assert!(record.mark_kernel_protected_identity(0x0012_4000));
        assert_eq!(
            record.address_space.page_directory_kind,
            PageDirectoryKind::PerProcessProtectedKernel
        );
        assert!(record.address_space.kernel_supervisor_only);
        assert!(record.address_space.kernel_protection_enforced);
        assert!(record.address_space.user_code_user_accessible);
        assert!(record.address_space.user_stack_user_accessible);
        assert!(!record.address_space.process_isolation_enforced);
        assert_eq!(
            record.address_space.verification_status,
            AddressSpaceVerificationStatus::KernelProtectedProcessIdentity
        );
        assert!(record.mark_private_user_mappings(0x0012_4000));
        assert_eq!(
            record.address_space.page_directory_kind,
            PageDirectoryKind::PerProcessIsolated
        );
        assert!(record.address_space.private_user_mappings);
        assert!(!record.address_space.process_isolation_enforced);
        assert_eq!(
            record.address_space.verification_status,
            AddressSpaceVerificationStatus::PrivateUserMappings
        );
        assert!(record.mark_process_isolation_proven());
        assert!(record.address_space.process_isolation_enforced);
        assert!(record.address_space.cross_process_isolation_enforced);
        assert!(record.address_space.writable_code_blocked);
        assert_eq!(
            record.address_space.verification_status,
            AddressSpaceVerificationStatus::HardwareVerified
        );
        let stable_hash = record.address_space.address_space_hash;
        assert_eq!(
            stable_hash,
            record.address_space.compute_hash(record.app_hash.unwrap())
        );
        assert!(record.mark_process_isolation_proven());
        assert_eq!(record.address_space.address_space_hash, stable_hash);
    }

    #[test]
    fn test_terminal_process_with_context_is_not_restore_eligible() {
        let mut record = ProcessRecord::new(1, "/apps/context.bogapp");
        assert!(record.mark_verified([6; 32]));
        assert!(record.mark_running());
        record.context.valid = true;
        assert!(record.mark_exited(0));
        assert!(!record.restore_eligible());
    }

    #[test]
    fn test_preempted_state_transitions_and_eligibility() {
        let mut table = ProcessTable::new();
        let pid = table.create("/apps/preempt.bogapp").unwrap();
        let record = table.get_mut(pid).unwrap();

        assert!(record.mark_verified([3; 32]));
        assert!(record.mark_running());

        assert!(record.mark_preempted());
        assert_eq!(record.state, ProcessState::Preempted);
        assert!(record.state_preempted);

        assert!(record.mark_ready());
        assert_eq!(record.state, ProcessState::Ready);
        assert!(record.state_ready);

        assert!(record.mark_scheduled());
        assert_eq!(record.state, ProcessState::Scheduled);
    }
}
