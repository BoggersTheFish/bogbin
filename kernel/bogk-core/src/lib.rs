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
}
