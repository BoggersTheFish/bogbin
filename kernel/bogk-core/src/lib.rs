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

#[cfg(test)]
mod tests {
    use super::*;

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
}

