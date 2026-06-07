from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .store import verify_installed_package
from .schema import SchemaError, validate_schema


class BogKernelError(Exception):
    pass


KERNEL_STATE_FORMAT = "BOGK-state-7.0"
KERNEL_RECEIPT_FORMAT = "BOGK-receipt-7.0"


class BogKernel:
    def __init__(self, workspace: Any) -> None:
        self.workspace = workspace
        self.root = workspace.root
        self.kernel_dir = workspace.bogos / "kernel"
        self.state_path = self.kernel_dir / "state.json"
        self.receipts_dir = self.kernel_dir / "receipts"
        self.processes_dir = self.kernel_dir / "processes"
        self.mounts_dir = self.kernel_dir / "mounts"
        self.syscall_log_path = self.kernel_dir / "syscall_log.jsonl"

    def boot(self) -> dict:
        self._ensure_layout()
        if self.state_path.exists():
            state = self._read_state()
            state["booted"] = True
        else:
            state = {
                "format": KERNEL_STATE_FORMAT,
                "workspace": str(self.root),
                "booted": True,
                "process_sequence": 0,
                "processes": {},
                "receipt_sequence": 0,
                "receipts": [],
                "syscall_count": 0,
                "last_receipt": None,
            }
        self._write_state(state)
        self._sync_mounts(state)
        receipt = {
            "format": "BOGK-boot-receipt-7.0",
            "workspace": str(self.root),
            "kernel": str(self.kernel_dir),
            "capabilities": [
                "verified-app-run",
                "mounted-archive-read",
                "policy-controlled-appdata-write",
            ],
            "execution_status": "completed",
        }
        return self._record_receipt("boot", "kernel", receipt, state=state)

    def status(self) -> dict:
        state = self._require_booted_state("status")
        if isinstance(state, dict) and state.get("execution_status") == "blocked":
            return state
        self._sync_mounts(state)
        status = {
            "format": "BOGK-status-receipt-7.0",
            "workspace": str(self.root),
            "kernel": str(self.kernel_dir),
            "booted": state["booted"],
            "process_count": len(state["processes"]),
            "syscall_count": state["syscall_count"],
            "receipt_count": len(state["receipts"]) + 1,
            "processes": state["processes"],
            "mounts": sorted(self.workspace.state.get("mounts", {})),
            "apps": sorted(self.workspace.state.get("apps", {})),
            "last_receipt": state.get("last_receipt"),
            "execution_status": "completed",
        }
        return self._record_receipt("status", "kernel", status, state=state)

    def run(self, app: str, args: list[str] | None = None) -> dict:
        state = self._require_booted_state("run", app)
        if isinstance(state, dict) and state.get("execution_status") == "blocked":
            return state
        self.workspace.state = self.workspace._read_state()
        process_id = self._next_process_id(state)
        app_receipt = self.workspace.run_app(app, extra_args=args or [])
        process = {
            "format": "BOGK-process-7.0",
            "process_id": process_id,
            "app": app,
            "package": app_receipt.get("package"),
            "app_receipt_format": app_receipt.get("format"),
            "app_execution_status": app_receipt["execution_status"],
            "status": "exited" if app_receipt["execution_status"] == "completed" else "blocked",
        }
        _write_json(self.processes_dir / f"{process_id}.json", process)
        state["processes"][process_id] = process
        receipt = {
            "format": "BOGK-process-receipt-7.0",
            "workspace": str(self.root),
            "process": process,
            "delegated_app_receipt": app_receipt,
            "failures": app_receipt.get("failures", []),
            "execution_status": app_receipt["execution_status"],
        }
        return self._record_receipt("run", app, receipt, state=state)

    def syscall_read(self, mount: str, path: str) -> dict:
        state = self._require_booted_state("syscall-read", mount)
        if isinstance(state, dict) and state.get("execution_status") == "blocked":
            return state
        self.workspace.state = self.workspace._read_state()
        failures = []
        data = b""
        delegated_receipt = None
        if not _is_safe_relpath(path):
            failures.append({"path": path, "reason": "unsafe syscall path"})
        elif mount not in self.workspace.state.get("mounts", {}):
            failures.append({"path": mount, "reason": f"unknown mount: {mount}"})
        else:
            data, delegated_receipt = self.workspace.read_mount(mount, path)
            failures.extend(delegated_receipt.get("failures", []))

        receipt = {
            "format": "BOGK-syscall-receipt-7.0",
            "workspace": str(self.root),
            "syscall": "read",
            "capability": "mounted-archive-read",
            "mount": mount,
            "path": path,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest() if not failures else None,
            "data_utf8": data.decode("utf-8", errors="replace") if data else "",
            "delegated_receipt": delegated_receipt,
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }
        return self._record_syscall(receipt, state)

    def syscall_write(self, app: str, path: str, data: str) -> dict:
        state = self._require_booted_state("syscall-write", app)
        if isinstance(state, dict) and state.get("execution_status") == "blocked":
            return state
        self.workspace.state = self.workspace._read_state()
        failures = []
        app_info = self.workspace.state.get("apps", {}).get(app)
        verification = None
        if app_info is None:
            failures.append({"path": app, "reason": f"unknown app: {app}"})
        else:
            verification = verify_installed_package(
                self.workspace.bogos / "store",
                app_info["package"],
                trusted_public_keys=self.workspace._trusted_public_keys(),
                require_signature=True,
            )
            failures.extend(verification.get("failures", []))
            if not _is_safe_relpath(path):
                failures.append({"path": path, "reason": "unsafe syscall path"})
            elif path not in app_info.get("write_policy", {}).get("allow", []):
                failures.append({"path": path, "reason": "write blocked by app write_policy"})

        target = None
        encoded = data.encode("utf-8")
        if not failures:
            runtime_dir = (self.workspace.bogos / "appdata" / app).resolve()
            target = (runtime_dir / path).resolve()
            if not target.is_relative_to(runtime_dir):
                failures.append({"path": path, "reason": "write escaped app runtime directory"})
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(encoded)

        receipt = {
            "format": "BOGK-syscall-receipt-7.0",
            "workspace": str(self.root),
            "syscall": "write",
            "capability": "policy-controlled-appdata-write",
            "app": app,
            "path": path,
            "target": str(target) if target is not None else None,
            "size": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "package_verification": verification,
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }
        return self._record_syscall(receipt, state)

    def syscall(self, name: str, *args: str) -> dict:
        if name == "read" and len(args) == 2:
            return self.syscall_read(args[0], args[1])
        if name == "write" and len(args) == 3:
            return self.syscall_write(args[0], args[1], args[2])
        state = self._require_booted_state("syscall", name)
        if isinstance(state, dict) and state.get("execution_status") == "blocked":
            return state
        receipt = {
            "format": "BOGK-syscall-receipt-7.0",
            "workspace": str(self.root),
            "syscall": name,
            "failures": [{"path": name, "reason": f"unknown syscall: {name}"}],
            "execution_status": "blocked",
        }
        return self._record_syscall(receipt, state)

    def _require_booted_state(self, operation: str, name: str = "kernel") -> dict:
        self._ensure_layout()
        if not self.state_path.exists():
            return self._record_unbooted(operation, name)
        state = self._read_state()
        if not state.get("booted"):
            return self._record_unbooted(operation, name, state=state)
        return state

    def _record_unbooted(self, operation: str, name: str, state: dict | None = None) -> dict:
        state = state or {
            "format": KERNEL_STATE_FORMAT,
            "workspace": str(self.root),
            "booted": False,
            "process_sequence": 0,
            "processes": {},
            "receipt_sequence": 0,
            "receipts": [],
            "syscall_count": 0,
            "last_receipt": None,
        }
        self._write_state(state)
        receipt = {
            "format": "BOGK-blocked-receipt-7.0",
            "workspace": str(self.root),
            "operation": operation,
            "failures": [{"path": name, "reason": "kernel is not booted"}],
            "execution_status": "blocked",
        }
        return self._record_receipt(operation, name, receipt, state=state)

    def _record_syscall(self, receipt: dict, state: dict) -> dict:
        state["syscall_count"] += 1
        logged = {
            "sequence": state["syscall_count"],
            "syscall": receipt["syscall"],
            "execution_status": receipt["execution_status"],
            "path": receipt.get("path"),
            "app": receipt.get("app"),
            "mount": receipt.get("mount"),
        }
        self.syscall_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.syscall_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(logged, sort_keys=True, separators=(",", ":")) + "\n")
        return self._record_receipt(f"syscall-{receipt['syscall']}", receipt.get("app") or receipt.get("mount") or "unknown", receipt, state=state)

    def _record_receipt(self, operation: str, name: str, receipt: dict, state: dict) -> dict:
        state["receipt_sequence"] += 1
        receipt = {
            **receipt,
            "kernel_receipt_format": KERNEL_RECEIPT_FORMAT,
            "kernel_operation": operation,
            "kernel_receipt_sequence": state["receipt_sequence"],
        }
        try:
            validate_schema(receipt, "kernel-receipt.schema.json")
        except SchemaError as exc:
            raise BogKernelError(str(exc)) from exc
        path = self.receipts_dir / f"{state['receipt_sequence']:04d}_{_safe_name(operation)}_{_safe_name(name)}.json"
        _write_json(path, receipt)
        state["receipts"].append({
            "sequence": state["receipt_sequence"],
            "operation": operation,
            "name": name,
            "path": str(path),
            "execution_status": receipt["execution_status"],
        })
        state["last_receipt"] = str(path)
        self._write_state(state)
        return receipt

    def _next_process_id(self, state: dict) -> str:
        state["process_sequence"] += 1
        return f"p{state['process_sequence']:04d}"

    def _sync_mounts(self, state: dict) -> None:
        self.workspace.state = self.workspace._read_state()
        for name, mount in sorted(self.workspace.state.get("mounts", {}).items()):
            _write_json(self.mounts_dir / f"{_safe_name(name)}.json", {
                "format": "BOGK-mount-7.0",
                "name": name,
                "archive": mount["archive"],
                "path": mount["path"],
            })
        self._write_state(state)

    def _ensure_layout(self) -> None:
        for path in (self.kernel_dir, self.receipts_dir, self.processes_dir, self.mounts_dir):
            path.mkdir(parents=True, exist_ok=True)
        if not self.syscall_log_path.exists():
            self.syscall_log_path.write_text("")

    def _read_state(self) -> dict:
        try:
            state = json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise BogKernelError(f"invalid kernel state: {exc}") from exc
        if state.get("format") != KERNEL_STATE_FORMAT:
            raise BogKernelError(f"unsupported kernel state format: {state.get('format')}")
        return state

    def _write_state(self, state: dict) -> None:
        _write_json(self.state_path, state)


def _is_safe_relpath(path: object) -> bool:
    if not isinstance(path, str) or not path:
        return False
    candidate = Path(path)
    return not candidate.is_absolute() and ".." not in candidate.parts


def _safe_name(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)
    return safe.strip("._") or "item"


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
