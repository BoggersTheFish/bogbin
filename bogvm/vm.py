from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import hashlib
import json
import struct
from pathlib import Path

from .instruction import Instruction, INSTRUCTION_STRUCT
from .opcodes import OPS, OP_NAMES, EDGE_TYPE_NAMES, SCALE
from .assembler import MAGIC


class VMError(Exception):
    pass


def canonical_hash(obj) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


@dataclass
class VMState:
    manifest: dict
    program_hash: str

    node_table: dict[int, dict] = field(default_factory=dict)
    edge_table: dict[int, dict] = field(default_factory=dict)
    claim_table: dict[int, dict] = field(default_factory=dict)

    adjacency_out: dict[int, list[int]] = field(default_factory=lambda: defaultdict(list))
    adjacency_in: dict[int, list[int]] = field(default_factory=lambda: defaultdict(list))

    activation_current: dict[int, int] = field(default_factory=dict)
    activation_scratch: dict[int, int] = field(default_factory=dict)

    tension_current: dict[int, int] = field(default_factory=dict)
    pressure_current: dict[int, dict] = field(default_factory=dict)

    verifier_results: dict[int, str] = field(default_factory=dict)
    accepted_claims: list[int] = field(default_factory=list)
    rejected_claims: list[int] = field(default_factory=list)
    quarantined_claims: list[int] = field(default_factory=list)

    receipt_ledger: list[dict] = field(default_factory=list)
    receipt_emitted: bool = False

    def node_name(self, node_id: int) -> str:
        return self.node_table[node_id]["name"]

    def claim_name(self, claim_id: int) -> str:
        return self.claim_table[claim_id]["name"]

    def log(self, pc: int, opcode: str, **details) -> None:
        self.receipt_ledger.append({
            "pc": pc,
            "opcode": opcode,
            "details": details,
        })

    def final_state(self) -> dict:
        return {
            "nodes": self.node_table,
            "edges": self.edge_table,
            "claims": self.claim_table,
            "activation_current": self.activation_current,
            "tension_current": self.tension_current,
            "pressure_current": self.pressure_current,
            "verifier_results": self.verifier_results,
            "accepted_claims": self.accepted_claims,
            "rejected_claims": self.rejected_claims,
            "quarantined_claims": self.quarantined_claims,
        }

    def receipt(self) -> dict:
        body = {
            "vm": "BOGVM-0.1",
            "bogbin": "BOGBIN-0.1",
            "fixed_point_scale": SCALE,
            "program_hash": self.program_hash,
            "events": self.receipt_ledger,
            "final_state_hash": canonical_hash(self.final_state()),
            "accepted_claim_names": [self.claim_name(c) for c in self.accepted_claims],
            "rejected_claim_names": [self.claim_name(c) for c in self.rejected_claims],
            "quarantined_claim_names": [self.claim_name(c) for c in self.quarantined_claims],
            "accepted_without_verify": 0,
            "candidate_graph_contamination": 0,
        }
        body["receipt_hash"] = canonical_hash(body)
        return body


def load_bogbin(path: str | Path) -> tuple[dict, list[Instruction], str]:
    data = Path(path).read_bytes()
    if not data.startswith(MAGIC):
        raise VMError("Invalid BOGBIN magic header")

    program_hash = hashlib.sha256(data).hexdigest()
    offset = len(MAGIC)
    manifest_len = struct.unpack(">I", data[offset:offset + 4])[0]
    offset += 4

    manifest = json.loads(data[offset:offset + manifest_len].decode("utf-8"))
    offset += manifest_len

    stream = data[offset:]
    if len(stream) % INSTRUCTION_STRUCT.size != 0:
        raise VMError("Instruction stream length is not a multiple of 8 bytes")

    instructions = [
        Instruction.unpack(stream[i:i + INSTRUCTION_STRUCT.size])
        for i in range(0, len(stream), INSTRUCTION_STRUCT.size)
    ]
    return manifest, instructions, program_hash


class BOGVM:
    ENERGY_LIMIT = 1_000_000_000

    def __init__(self, manifest: dict, program_hash: str) -> None:
        self.state = VMState(manifest=manifest, program_hash=program_hash)

    def run(self, instructions: list[Instruction]) -> dict:
        pc = 0
        halted = False

        while pc < len(instructions):
            instr = instructions[pc]
            opcode_name = OP_NAMES.get(instr.opcode)
            if opcode_name is None:
                raise VMError(f"Unknown opcode at pc={pc}: {instr.opcode}")

            if opcode_name == "NOOP":
                self.state.log(pc, opcode_name)

            elif opcode_name == "HALT":
                self.state.log(pc, opcode_name)
                halted = True
                break

            elif opcode_name == "CREATE_NODE":
                name = self.state.manifest["nodes"].get(str(instr.target))
                if name is None:
                    raise VMError(f"Missing node symbol for id {instr.target}")
                self.state.node_table[instr.target] = {"id": instr.target, "name": name}
                self.state.log(pc, opcode_name, node_id=instr.target, name=name)

            elif opcode_name == "CREATE_EDGE":
                if instr.source not in self.state.node_table or instr.param not in self.state.node_table:
                    raise VMError("CREATE_EDGE references unknown node")
                edge_type = EDGE_TYPE_NAMES.get(instr.flags)
                if edge_type is None:
                    raise VMError(f"Unknown edge type flag: {instr.flags}")

                edge = {
                    "id": instr.target,
                    "source": instr.source,
                    "target": instr.param,
                    "type": edge_type,
                    "weight": SCALE,
                }
                self.state.edge_table[instr.target] = edge
                self.state.adjacency_out[instr.source].append(instr.target)
                self.state.adjacency_in[instr.param].append(instr.target)

                self.state.adjacency_out[instr.source].sort()
                self.state.adjacency_in[instr.param].sort()

                self.state.log(
                    pc,
                    opcode_name,
                    edge_id=instr.target,
                    source=self.state.node_name(instr.source),
                    target=self.state.node_name(instr.param),
                    edge_type=edge_type,
                )

            elif opcode_name == "CREATE_CLAIM":
                meta = self.state.manifest["claims"].get(str(instr.target))
                if meta is None:
                    raise VMError(f"Missing claim symbol for id {instr.target}")
                self.state.claim_table[instr.target] = {
                    "id": instr.target,
                    "name": meta["name"],
                    "source": instr.source,
                    "target": instr.param,
                }
                self.state.log(
                    pc,
                    opcode_name,
                    claim_id=instr.target,
                    name=meta["name"],
                    source=self.state.node_name(instr.source),
                    target=self.state.node_name(instr.param),
                )

            elif opcode_name == "ACTIVATE":
                if instr.target not in self.state.node_table:
                    raise VMError("ACTIVATE references unknown node")
                if not 0 <= instr.param <= SCALE:
                    raise VMError(f"Activation must be 0..{SCALE}")
                self.state.activation_current[instr.target] = instr.param
                self.state.log(
                    pc,
                    opcode_name,
                    node=self.state.node_name(instr.target),
                    strength=instr.param,
                )

            elif opcode_name == "PROPAGATE":
                edge_type = EDGE_TYPE_NAMES.get(instr.flags)
                if edge_type is None:
                    raise VMError(f"Unknown propagation edge type: {instr.flags}")

                current = dict(self.state.activation_current)
                total_energy = 0
                reached = set()

                for tick in range(instr.param):
                    scratch = defaultdict(int)

                    for node_id in sorted(current.keys()):
                        activation = current[node_id]
                        for edge_id in sorted(self.state.adjacency_out.get(node_id, [])):
                            edge = self.state.edge_table[edge_id]
                            if edge["type"] != edge_type:
                                continue

                            next_value = (activation * edge["weight"]) // SCALE
                            if next_value <= 0:
                                continue

                            total_energy += next_value
                            if total_energy > self.ENERGY_LIMIT:
                                raise VMError("PROPAGATE energy limit exceeded")

                            scratch[edge["target"]] += next_value
                            reached.add(edge["target"])

                    current = dict(sorted(scratch.items()))

                self.state.activation_scratch = current
                self.state.activation_current = self.state.activation_scratch
                self.state.activation_scratch = {}

                self.state.log(
                    pc,
                    opcode_name,
                    source=self.state.node_name(instr.source) if instr.source in self.state.node_table else instr.source,
                    edge_type=edge_type,
                    depth=instr.param,
                    energy_spent=total_energy,
                    nodes_reached=[self.state.node_name(n) for n in sorted(reached)],
                )

            elif opcode_name == "DECAY":
                if not 0 <= instr.param <= SCALE:
                    raise VMError(f"DECAY factor must be 0..{SCALE}")
                decayed = {}
                for node_id in sorted(self.state.activation_current.keys()):
                    value = (self.state.activation_current[node_id] * instr.param) // SCALE
                    if value > 0:
                        decayed[node_id] = value
                self.state.activation_current = decayed
                self.state.log(pc, opcode_name, factor=instr.param)

            elif opcode_name == "INTERFERE":
                claim = self.state.claim_table[instr.target]
                target_node = claim["target"]

                support_pressure = self.state.activation_current.get(target_node, 0)
                conflict_pressure = 0

                for edge_id in sorted(self.state.adjacency_in.get(target_node, [])):
                    edge = self.state.edge_table[edge_id]
                    if edge["type"] != "conflict":
                        continue
                    source_activation = self.state.activation_current.get(edge["source"], 0)
                    conflict_pressure += (source_activation * edge["weight"]) // SCALE

                net_pressure = support_pressure - conflict_pressure
                tension = min(support_pressure, conflict_pressure)

                self.state.pressure_current[instr.target] = {
                    "support_pressure": support_pressure,
                    "conflict_pressure": conflict_pressure,
                    "net_pressure": net_pressure,
                }
                self.state.tension_current[instr.target] = tension

                self.state.log(
                    pc,
                    opcode_name,
                    claim=self.state.claim_name(instr.target),
                    support_pressure=support_pressure,
                    conflict_pressure=conflict_pressure,
                    net_pressure=net_pressure,
                    tension=tension,
                )

            elif opcode_name == "COMPUTE_TENSION":
                pressure = self.state.pressure_current.get(instr.target)
                if pressure is None:
                    tension = 0
                else:
                    tension = min(pressure["support_pressure"], pressure["conflict_pressure"])
                self.state.tension_current[instr.target] = tension
                self.state.log(
                    pc,
                    opcode_name,
                    claim=self.state.claim_name(instr.target),
                    tension=tension,
                )

            elif opcode_name == "VERIFY":
                status = self._verify_claim(instr.target)
                self.state.verifier_results[instr.target] = status
                self.state.log(
                    pc,
                    opcode_name,
                    claim=self.state.claim_name(instr.target),
                    result=status,
                )

            elif opcode_name == "ACCEPT":
                if self.state.verifier_results.get(instr.target) != "verified":
                    raise VMError(f"ACCEPT without VERIFY is blocked for claim {self.state.claim_name(instr.target)}")
                if instr.target not in self.state.accepted_claims:
                    self.state.accepted_claims.append(instr.target)
                    self.state.accepted_claims.sort()
                self.state.log(
                    pc,
                    opcode_name,
                    claim=self.state.claim_name(instr.target),
                    result="accepted",
                )

            elif opcode_name == "REJECT":
                if instr.target not in self.state.rejected_claims:
                    self.state.rejected_claims.append(instr.target)
                    self.state.rejected_claims.sort()
                self.state.log(
                    pc,
                    opcode_name,
                    claim=self.state.claim_name(instr.target),
                    result="rejected",
                )

            elif opcode_name == "QUARANTINE":
                if instr.target not in self.state.quarantined_claims:
                    self.state.quarantined_claims.append(instr.target)
                    self.state.quarantined_claims.sort()
                self.state.log(
                    pc,
                    opcode_name,
                    claim=self.state.claim_name(instr.target),
                    result="quarantined",
                )

            elif opcode_name == "LOG_RECEIPT":
                self.state.log(pc, opcode_name, note="manual receipt checkpoint")

            elif opcode_name == "EMIT_RECEIPT":
                self.state.receipt_emitted = True
                self.state.log(pc, opcode_name, result="receipt_ready")

            else:
                raise VMError(f"Unhandled opcode: {opcode_name}")

            pc += 1

        if not halted:
            raise VMError("Program ended without HALT")

        if not self.state.receipt_emitted:
            self.state.log(pc, "AUTO_RECEIPT", result="receipt_emitted_by_vm")

        return self.state.receipt()

    def _verify_claim(self, claim_id: int) -> str:
        claim = self.state.claim_table[claim_id]
        source = claim["source"]
        target = claim["target"]

        conflict_pressure = self.state.pressure_current.get(claim_id, {}).get("conflict_pressure", 0)
        if conflict_pressure > 0:
            return "rejected"

        if self._support_path_exists(source, target):
            return "verified"

        return "abstained"

    def _support_path_exists(self, source: int, target: int) -> bool:
        queue = deque([source])
        visited = set()

        while queue:
            node_id = queue.popleft()
            if node_id == target:
                return True
            if node_id in visited:
                continue
            visited.add(node_id)

            for edge_id in sorted(self.state.adjacency_out.get(node_id, [])):
                edge = self.state.edge_table[edge_id]
                if edge["type"] == "support" and edge["target"] not in visited:
                    queue.append(edge["target"])

        return False


def run_file(path: str | Path) -> dict:
    manifest, instructions, program_hash = load_bogbin(path)
    vm = BOGVM(manifest, program_hash)
    return vm.run(instructions)
