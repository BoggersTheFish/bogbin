#![no_std]

/// The fixed-point scale used for all BOGVM wave-state math.
pub const SCALE: u16 = 1000;

/// BOGVM Opcodes as defined in docs/bogvm_bytecode_contract.md
#[repr(u8)]
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
}
