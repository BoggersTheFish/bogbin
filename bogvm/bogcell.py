from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .signing import canonical_bytes, sign_object, verify_object_signature
from .schema import validate_schema


PROGRAM_FORMAT = "BOGCELL-program-10.0"
BUILD_FORMAT = "BOGBUILD-receipt-10.0"


class BogCellError(Exception):
    pass


def compile_source(source_path: str | Path, output_dir: str | Path, signing_key: str | Path) -> dict:
    source_path = Path(source_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    instructions = []
    capabilities = {"read": [], "write": [], "env": [], "dependencies": []}
    registers: dict[str, str] = {}
    for number, raw in enumerate(source_path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 4 and parts[0] == "read" and parts[2] == "as":
            instructions.append(["READ", parts[1], parts[3]])
            capabilities["read"].append(parts[1])
            registers[parts[3]] = "bytes"
        elif len(parts) == 4 and parts[0] == "env" and parts[2] == "as":
            instructions.append(["ENV", parts[1], parts[3]])
            capabilities["env"].append(parts[1])
            registers[parts[3]] = "text"
        elif len(parts) == 4 and parts[0] == "dependency" and parts[2] == "as":
            instructions.append(["DEPENDENCY", parts[1], parts[3]])
            capabilities["dependencies"].append(parts[1])
            registers[parts[3]] = "receipt"
        elif len(parts) >= 3 and parts[0] == "write":
            value = " ".join(parts[2:])
            instructions.append(["WRITE", parts[1], {"register": value[1:]} if value.startswith("$") else value])
            capabilities["write"].append(parts[1])
        elif len(parts) == 2 and parts[0] == "exit" and parts[1].lstrip("-").isdigit():
            instructions.append(["EXIT", int(parts[1])])
        else:
            raise BogCellError(f"invalid Bog source line {number}: {raw}")
    if not instructions or instructions[-1][0] != "EXIT":
        instructions.append(["EXIT", 0])
    program = {"format": PROGRAM_FORMAT, "instructions": instructions}
    validate_schema(program, "bogcell-program.schema.json")
    program_path = output / "program.bogcell"
    _write_json(program_path, program)
    source_hash = _file_hash(source_path)
    bytecode_hash = _file_hash(program_path)
    compiler = {
        "name": "BogBuild reference compiler",
        "format": BUILD_FORMAT,
        "implementation_sha256": _file_hash(Path(__file__)),
        "compiler_package_sha256": _file_hash(Path(__file__)),
    }
    unsigned = {
        "format": BUILD_FORMAT,
        "source_sha256": source_hash,
        "compiler": compiler,
        "bytecode_sha256": bytecode_hash,
        "capabilities": {key: sorted(set(value)) for key, value in capabilities.items()},
    }
    receipt = {**unsigned, "compiler_signature": sign_object(unsigned, signing_key)}
    validate_schema(receipt, "bogbuild-receipt.schema.json")
    _write_json(output / "build_receipt.json", receipt)
    return receipt


class BogCell:
    """Deterministic capability-only VM. It has no subprocess or raw host-I/O instructions."""

    def __init__(self, workspace: Any, genesis: Any) -> None:
        self.workspace = workspace
        self.genesis = genesis

    def run(self, app: str) -> dict:
        self.workspace.state = self.workspace._read_state()
        app_info = self.workspace.state.get("apps", {}).get(app)
        failures = []
        if not app_info or not app_info.get("cell_program"):
            failures.append({"path": app, "reason": "installed app is not a BogCell app"})
            return self._receipt(app, None, None, [], {}, failures, None)
        verification = self.workspace._verify_installed_package(app_info["package"])
        failures.extend(verification.get("failures", []))
        install_dir = Path(app_info["install_dir"])
        program_path = install_dir / app_info["cell_program"]
        build_verification = None
        build_path = install_dir / app_info.get("build_receipt", "build_receipt.json")
        try:
            build_receipt = json.loads(build_path.read_text())
            build_verification = verify_build_receipt(build_receipt, self.workspace._trusted_public_keys())
            failures.extend(build_verification["failures"])
            if build_receipt.get("bytecode_sha256") != _file_hash(program_path):
                failures.append({"path": str(program_path), "reason": "BogCell bytecode does not match signed build receipt"})
        except (OSError, json.JSONDecodeError) as exc:
            failures.append({"path": str(build_path), "reason": f"invalid BogBuild receipt: {exc}"})
        try:
            program = json.loads(program_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            failures.append({"path": str(program_path), "reason": f"invalid BogCell program: {exc}"})
            return self._receipt(app, verification, build_verification, [], {}, failures, None)
        if program.get("format") != PROGRAM_FORMAT:
            failures.append({"path": str(program_path), "reason": "unsupported BogCell program format"})
        else:
            try:
                validate_schema(program, "bogcell-program.schema.json")
            except Exception as exc:
                failures.append({"path": str(program_path), "reason": str(exc)})
        capabilities = app_info.get("cell_capabilities", {})
        calls = []
        registers = {}
        exit_code = None
        if not failures:
            for sequence, instruction in enumerate(program.get("instructions", []), 1):
                call, value = self._execute(app_info, capabilities, instruction, sequence, registers)
                calls.append(call)
                if call["execution_status"] == "blocked":
                    failures.extend(call["failures"])
                    break
                if value is not None and len(instruction) >= 3:
                    registers[instruction[-1]] = value
                if instruction[0] == "EXIT":
                    exit_code = instruction[1]
                    if exit_code != 0:
                        failures.append({"path": app, "reason": f"BogCell exited with code {exit_code}"})
                    break
        return self._receipt(app, verification, build_verification, calls, registers, failures, exit_code, program=program)

    def _execute(self, app_info: dict, capabilities: dict, instruction: list, sequence: int, registers: dict) -> tuple[dict, Any]:
        operation = instruction[0] if instruction else "INVALID"
        evidence: dict[str, Any] = {"operation": operation, "instruction": instruction}
        failures = []
        value = None
        if operation == "READ" and len(instruction) == 3:
            path = instruction[1]
            evidence["allowed"] = path in capabilities.get("read", [])
            target = Path(app_info["install_dir"]) / path
            if not evidence["allowed"] or not target.is_file() or not target.resolve().is_relative_to(Path(app_info["install_dir"]).resolve()):
                failures.append({"path": path, "reason": "BogCell read blocked by capability manifest"})
            else:
                value = target.read_bytes()
                evidence["sha256"] = hashlib.sha256(value).hexdigest()
        elif operation == "WRITE" and len(instruction) == 3:
            path, raw = instruction[1], instruction[2]
            evidence["allowed"] = path in capabilities.get("write", [])
            if not evidence["allowed"]:
                failures.append({"path": path, "reason": "BogCell write blocked by capability manifest"})
            else:
                value_data = registers.get(raw["register"]) if isinstance(raw, dict) and "register" in raw else raw
                if isinstance(value_data, dict):
                    value_data = json.dumps(value_data, sort_keys=True)
                write = self.genesis.fs_write(path, value_data if value_data is not None else "", capability=app_info["name"])
                evidence.update(object_sha256=write["object_sha256"], state_root_sha256=write["after_root_sha256"])
        elif operation == "ENV" and len(instruction) == 3:
            name = instruction[1]
            evidence["allowed"] = name in capabilities.get("env", [])
            if not evidence["allowed"]:
                failures.append({"path": name, "reason": "BogCell environment access blocked by capability manifest"})
            else:
                value = app_info.get("cell_environment", {}).get(name)
                evidence["value_sha256"] = hashlib.sha256(str(value).encode()).hexdigest()
        elif operation == "DEPENDENCY" and len(instruction) == 3:
            package = instruction[1]
            evidence["allowed"] = package in capabilities.get("dependencies", [])
            value = self.workspace._verify_installed_package(package) if evidence["allowed"] else None
            if not evidence["allowed"] or value["execution_status"] != "completed":
                failures.append({"path": package, "reason": "BogCell dependency access blocked or unverified"})
            else:
                evidence["bundle_sha256"] = value["bundle_sha256"]
        elif operation == "EXIT" and len(instruction) == 2 and isinstance(instruction[1], int):
            evidence["exit_code"] = instruction[1]
        else:
            failures.append({"path": str(instruction), "reason": "unknown or malformed BogCell instruction"})
        evidence["execution_status"] = "completed" if not failures else "blocked"
        call = {
            "format": "BOGCELL-capability-receipt-10.0",
            "sequence": sequence,
            **evidence,
            "evidence_sha256": _stable_hash(evidence),
            "failures": failures,
            "execution_status": evidence["execution_status"],
        }
        return call, value

    def _receipt(self, app: str, verification: dict | None, build_verification: dict | None, calls: list, registers: dict, failures: list, exit_code: int | None, program: dict | None = None) -> dict:
        proof = {
            "app": app,
            "package_bundle_sha256": verification.get("bundle_sha256") if verification else None,
            "program_sha256": _stable_hash(program) if program else None,
            "call_evidence": [call["evidence_sha256"] for call in calls],
            "final_state_root_sha256": self.genesis.current_root(),
            "exit_code": exit_code,
        }
        return {
            "format": "BOGCELL-process-receipt-10.0",
            "app": app,
            "package_verification": verification,
            "build_verification": build_verification,
            "raw_syscall_surface": [],
            "capability_receipts": calls,
            "register_hashes": {key: hashlib.sha256(_bytes(value)).hexdigest() for key, value in sorted(registers.items())},
            "final_state_root_sha256": self.genesis.current_root(),
            "exit_code": exit_code,
            "proof_material": proof,
            "proof_sha256": _stable_hash(proof),
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }


def verify_build_receipt(receipt: dict, trusted_keys: list[str | Path]) -> dict:
    unsigned = dict(receipt)
    signature = unsigned.pop("compiler_signature", {})
    result = verify_object_signature(unsigned, signature, trusted_keys)
    return {
        "compiler_signature_verified": result["verified"],
        "source_sha256": receipt.get("source_sha256"),
        "bytecode_sha256": receipt.get("bytecode_sha256"),
        "failures": [] if result["verified"] else [{"path": "build_receipt.json", "reason": result["reason"]}],
        "execution_status": "completed" if result["verified"] else "blocked",
    }


def _bytes(value: Any) -> bytes:
    return value if isinstance(value, bytes) else canonical_bytes(value) if isinstance(value, dict) else str(value).encode()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
