import json
import struct
from pathlib import Path

from .instruction import Instruction
from .opcodes import OPS, EDGE_TYPES

MAGIC = b"BOGBIN01"


class AssemblerError(Exception):
    pass


def _strip(line: str) -> str:
    return line.split("#", 1)[0].strip()


class Assembler:
    def __init__(self) -> None:
        self.nodes: dict[str, int] = {}
        self.claims: dict[str, int] = {}
        self.claim_meta: dict[str, dict] = {}
        self.edge_count = 0
        self.data_names: dict[str, int] = {}
        self.constants: dict[str, str] = {}
        self.constant_ids: dict[str, int] = {}
        self.instructions: list[Instruction] = []

    def require_node(self, name: str) -> int:
        if name not in self.nodes:
            raise AssemblerError(f"Unknown node: {name}")
        return self.nodes[name]

    def require_claim(self, name: str) -> int:
        if name not in self.claims:
            raise AssemblerError(f"Unknown claim: {name}")
        return self.claims[name]

    def add_node(self, name: str) -> int:
        if name in self.nodes:
            return self.nodes[name]
        node_id = len(self.nodes)
        if node_id > 65535:
            raise AssemblerError("Too many nodes for BOGBIN-0.1")
        self.nodes[name] = node_id
        return node_id

    def add_claim(self, name: str, source: int, target: int) -> int:
        if name in self.claims:
            return self.claims[name]
        claim_id = len(self.claims)
        if claim_id > 65535:
            raise AssemblerError("Too many claims for BOGBIN-0.1")
        self.claims[name] = claim_id
        self.claim_meta[str(claim_id)] = {
            "id": claim_id,
            "name": name,
            "source": source,
            "target": target,
        }
        return claim_id


    def add_data(self, name: str) -> int:
        if name in self.data_names:
            return self.data_names[name]
        data_id = len(self.data_names)
        if data_id > 65535:
            raise AssemblerError("Too many data blocks for BOGBIN-0.2")
        self.data_names[name] = data_id
        return data_id

    def require_data(self, name: str) -> int:
        if name not in self.data_names:
            raise AssemblerError(f"Unknown data block: {name}")
        return self.data_names[name]

    def add_constant(self, value: str) -> int:
        if value in self.constant_ids:
            return self.constant_ids[value]
        const_id = len(self.constant_ids)
        if const_id > 65535:
            raise AssemblerError("Too many constants for BOGBIN-0.2")
        self.constant_ids[value] = const_id
        self.constants[str(const_id)] = value
        return const_id

    def emit(self, op: str, flags: int = 0, target: int = 0, source: int = 0, param: int = 0) -> None:
        for value_name, value in {
            "flags": flags,
            "target": target,
            "source": source,
            "param": param,
        }.items():
            if not 0 <= value <= 65535:
                raise AssemblerError(f"{value_name} out of uint16 range: {value}")
        self.instructions.append(Instruction(OPS[op], flags, target, source, param))

    def parse_line(self, line: str) -> None:
        line = _strip(line)
        if not line:
            return

        parts = line.split()
        op = parts[0].upper()

        if op == "CREATE_NODE":
            if len(parts) != 2:
                raise AssemblerError("CREATE_NODE needs: CREATE_NODE <name>")
            node_id = self.add_node(parts[1])
            self.emit("CREATE_NODE", target=node_id)

        elif op == "CREATE_EDGE":
            if len(parts) != 4:
                raise AssemblerError("CREATE_EDGE needs: CREATE_EDGE <source> <target> <support|conflict>")
            src = self.require_node(parts[1])
            dst = self.require_node(parts[2])
            edge_type = parts[3].lower()
            if edge_type not in EDGE_TYPES:
                raise AssemblerError(f"Unknown edge type: {edge_type}")
            edge_id = self.edge_count
            self.edge_count += 1
            self.emit("CREATE_EDGE", flags=EDGE_TYPES[edge_type], target=edge_id, source=src, param=dst)

        elif op == "CREATE_CLAIM":
            if len(parts) != 4:
                raise AssemblerError("CREATE_CLAIM needs: CREATE_CLAIM <claim_name> <source> <target>")
            src = self.require_node(parts[2])
            dst = self.require_node(parts[3])
            claim_id = self.add_claim(parts[1], src, dst)
            self.emit("CREATE_CLAIM", target=claim_id, source=src, param=dst)

        elif op == "ACTIVATE":
            if len(parts) != 3:
                raise AssemblerError("ACTIVATE needs: ACTIVATE <node> <strength_0_to_1000>")
            node_id = self.require_node(parts[1])
            strength = int(parts[2])
            self.emit("ACTIVATE", target=node_id, param=strength)

        elif op == "PROPAGATE":
            if len(parts) != 4:
                raise AssemblerError("PROPAGATE needs: PROPAGATE <source> <support|conflict> <depth>")
            src = self.require_node(parts[1])
            edge_type = parts[2].lower()
            depth = int(parts[3])
            self.emit("PROPAGATE", flags=EDGE_TYPES[edge_type], source=src, param=depth)

        elif op == "DECAY":
            if len(parts) != 2:
                raise AssemblerError("DECAY needs: DECAY <factor_0_to_1000>")
            self.emit("DECAY", param=int(parts[1]))

        elif op in {"INTERFERE", "COMPUTE_TENSION", "VERIFY", "ACCEPT", "REJECT", "QUARANTINE"}:
            if len(parts) != 2:
                raise AssemblerError(f"{op} needs: {op} <claim_name>")
            claim_id = self.require_claim(parts[1])
            self.emit(op, target=claim_id)

        elif op == "LOG_RECEIPT":
            self.emit("LOG_RECEIPT")

        elif op == "EMIT_RECEIPT":
            self.emit("EMIT_RECEIPT")

        elif op == "HALT":
            self.emit("HALT")

        elif op == "DECLARE_BASIS":
            if len(parts) != 2:
                raise AssemblerError("DECLARE_BASIS needs: DECLARE_BASIS <basis_name>")
            basis_id = self.add_constant(parts[1])
            self.emit("DECLARE_BASIS", target=basis_id)

        elif op == "DATA_BLOCK":
            if len(parts) != 2:
                raise AssemblerError("DATA_BLOCK needs: DATA_BLOCK <name>")
            self.add_data(parts[1])

        elif op == "LOAD_COEFFICIENTS":
            if len(parts) not in {4, 5}:
                raise AssemblerError("LOAD_COEFFICIENTS needs: LOAD_COEFFICIENTS <data_name> <byte_0_to_255> <length> [delta_0_to_255]")
            data_id = self.require_data(parts[1])
            byte_value = int(parts[2])
            length = int(parts[3])
            delta = int(parts[4]) if len(parts) == 5 else 0
            if not 0 <= byte_value <= 255:
                raise AssemblerError("byte must be 0..255")
            if not 0 <= delta <= 255:
                raise AssemblerError("delta must be 0..255")
            self.emit("LOAD_COEFFICIENTS", flags=delta, target=data_id, source=byte_value, param=length)

        elif op == "SYNTHESIZE":
            if len(parts) != 2:
                raise AssemblerError("SYNTHESIZE needs: SYNTHESIZE <data_name>")
            data_id = self.require_data(parts[1])
            self.emit("SYNTHESIZE", target=data_id)

        elif op == "VERIFY_HASH":
            if len(parts) != 3:
                raise AssemblerError("VERIFY_HASH needs: VERIFY_HASH <data_name> <sha256_hex>")
            data_id = self.require_data(parts[1])
            hash_id = self.add_constant(parts[2])
            self.emit("VERIFY_HASH", target=data_id, source=hash_id)

        elif op == "ACCEPT_DATA":
            if len(parts) != 2:
                raise AssemblerError("ACCEPT_DATA needs: ACCEPT_DATA <data_name>")
            data_id = self.require_data(parts[1])
            self.emit("ACCEPT_DATA", target=data_id)

        elif op == "REJECT_DATA":
            if len(parts) != 2:
                raise AssemblerError("REJECT_DATA needs: REJECT_DATA <data_name>")
            data_id = self.require_data(parts[1])
            self.emit("REJECT_DATA", target=data_id)

        elif op == "STORE_RESIDUAL":
            if len(parts) != 4:
                raise AssemblerError("STORE_RESIDUAL needs: STORE_RESIDUAL <data_name> <offset> <byte_0_to_255>")
            data_id = self.require_data(parts[1])
            offset = int(parts[2])
            byte_value = int(parts[3])
            if not 0 <= byte_value <= 255:
                raise AssemblerError("residual byte must be 0..255")
            self.emit("STORE_RESIDUAL", target=data_id, source=offset, param=byte_value)

        elif op == "APPLY_RESIDUAL":
            if len(parts) != 2:
                raise AssemblerError("APPLY_RESIDUAL needs: APPLY_RESIDUAL <data_name>")
            data_id = self.require_data(parts[1])
            self.emit("APPLY_RESIDUAL", target=data_id)

        elif op == "NOOP":
            self.emit("NOOP")

        else:
            raise AssemblerError(f"Unknown op: {op}")

    def assemble_text(self, text: str) -> bytes:
        for line in text.splitlines():
            self.parse_line(line)

        manifest = {
            "version": "0.1",
            "scale": 1000,
            "nodes": {str(v): k for k, v in sorted(self.nodes.items(), key=lambda x: x[1])},
            "claims": self.claim_meta,
            "data_blocks": {str(v): k for k, v in sorted(self.data_names.items(), key=lambda x: x[1])},
            "constants": self.constants,
            "instruction_count": len(self.instructions),
        }
        manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        instruction_bytes = b"".join(i.pack() for i in self.instructions)

        return MAGIC + struct.pack(">I", len(manifest_bytes)) + manifest_bytes + instruction_bytes


def assemble_file(src: str | Path, dst: str | Path) -> None:
    src = Path(src)
    dst = Path(dst)
    assembler = Assembler()
    dst.write_bytes(assembler.assemble_text(src.read_text()))
