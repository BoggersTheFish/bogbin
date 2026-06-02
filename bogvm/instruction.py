from dataclasses import dataclass
import struct

INSTRUCTION_STRUCT = struct.Struct(">BBHHH")


@dataclass(frozen=True)
class Instruction:
    opcode: int
    flags: int
    target: int
    source: int
    param: int

    def pack(self) -> bytes:
        return INSTRUCTION_STRUCT.pack(
            self.opcode,
            self.flags,
            self.target,
            self.source,
            self.param,
        )

    @staticmethod
    def unpack(data: bytes) -> "Instruction":
        opcode, flags, target, source, param = INSTRUCTION_STRUCT.unpack(data)
        return Instruction(opcode, flags, target, source, param)
