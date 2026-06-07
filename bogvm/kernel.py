from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import threading
from typing import Any

from .store import verify_installed_package
from .schema import SchemaError, validate_schema


class BogKernelError(Exception):
    pass


KERNEL_STATE_FORMAT = "BOGK-state-8.0"
LEGACY_KERNEL_STATE_FORMAT = "BOGK-state-7.0"
KERNEL_RECEIPT_FORMAT = "BOGK-receipt-8.0"


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
            "format": "BOGK-boot-receipt-8.0",
            "workspace": str(self.root),
            "kernel": str(self.kernel_dir),
            "capabilities": [
                "verified-app-run",
                "mounted-archive-read",
                "policy-controlled-appdata-write",
                "brokered-capability-runtime",
                "process-proof-replay",
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
            "format": "BOGK-status-receipt-8.0",
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

    def run(self, app: str, args: list[str] | None = None, brokered: bool = False) -> dict:
        if brokered:
            return self.run_brokered(app, args=args)
        state = self._require_booted_state("run", app)
        if isinstance(state, dict) and state.get("execution_status") == "blocked":
            return state
        self.workspace.state = self.workspace._read_state()
        process_id = self._next_process_id(state)
        app_receipt = self.workspace.run_app(app, extra_args=args or [])
        process = {
            "format": "BOGK-process-8.0",
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
            "format": "BOGK-process-receipt-8.0",
            "workspace": str(self.root),
            "process": process,
            "delegated_app_receipt": app_receipt,
            "failures": app_receipt.get("failures", []),
            "execution_status": app_receipt["execution_status"],
        }
        return self._record_receipt("run", app, receipt, state=state)

    def run_brokered(self, app: str, args: list[str] | None = None) -> dict:
        state = self._require_booted_state("run-brokered", app)
        if state.get("execution_status") == "blocked":
            return state
        self.workspace.state = self.workspace._read_state()
        app_info = self.workspace.state.get("apps", {}).get(app)
        failures = []
        verification = self.workspace._verify_installed_package(app_info["package"]) if app_info else None
        if app_info is None:
            failures.append({"path": app, "reason": f"app not installed: {app}"})
        elif verification["execution_status"] != "completed":
            failures.extend(verification["failures"])
        capabilities = app_info.get("capabilities") if app_info else None
        if app_info and capabilities is None:
            failures.append({"path": "bog_app.json", "reason": "brokered run requires a v8 capability manifest"})
        policy = self.workspace._verify_app_runtime_policy(app, app_info, verification) if app_info and verification else None
        if policy and policy["execution_status"] != "completed":
            failures.extend(policy["failures"])

        process_id = self._next_process_id(state)
        if failures:
            return self._finalize_brokered_process(
                state, process_id, app, app_info, verification, policy, [], None, failures
            )

        install_dir = Path(app_info["install_dir"])
        runtime_dir = self.workspace.bogos / "appdata" / app
        runtime_dir.mkdir(parents=True, exist_ok=True)
        command = _resolve_entrypoint(install_dir, app_info["entrypoint"]) + (args or [])
        token = secrets.token_hex(24)
        broker = _CapabilityBroker(self, state, app, app_info, verification, token)
        broker.start()
        environment = _brokered_environment(app_info, app, install_dir, runtime_dir, broker.socket_path, token)
        runtime_before = _snapshot(runtime_dir)
        package_before = _snapshot(install_dir)
        try:
            result = subprocess.run(command, cwd=runtime_dir, env=environment, check=False, text=True, capture_output=True)
        except OSError as exc:
            result = None
            failures.append({"path": app, "reason": str(exc)})
        finally:
            broker.stop()

        if result is not None and result.returncode != 0:
            failures.append({"path": app, "reason": f"brokered app exited with code {result.returncode}"})
        package_after = _snapshot(install_dir)
        if package_after != package_before:
            failures.append({"path": str(install_dir), "reason": "installed package changed during brokered run"})
        post_verification = self.workspace._verify_installed_package(app_info["package"])
        failures.extend(post_verification.get("failures", []))
        brokered_writes = {call["path"] for call in broker.calls if call["operation"] == "write" and call["execution_status"] == "completed"}
        raw_changes = set(_snapshot_changes(runtime_before, _snapshot(runtime_dir)))
        for path in sorted(raw_changes - brokered_writes):
            failures.append({"path": path, "reason": "raw runtime write outside BogK broker"})
        final_writes = {
            call["path"]: call
            for call in broker.calls
            if call["operation"] == "write" and call["execution_status"] == "completed"
        }
        for call in final_writes.values():
            target = runtime_dir / call["path"]
            if target.is_symlink() or not target.resolve().is_relative_to(runtime_dir.resolve()):
                failures.append({"path": call["path"], "reason": "brokered output replaced by unsafe path"})
                continue
            actual_sha256 = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
            if actual_sha256 != call["sha256"]:
                failures.append({"path": call["path"], "reason": "brokered output changed outside BogK broker"})

        return self._finalize_brokered_process(
            state,
            process_id,
            app,
            app_info,
            verification,
            policy,
            broker.calls,
            result,
            failures,
            post_verification=post_verification,
        )

    def replay(self, receipt_path: str | Path) -> dict:
        state = self._require_booted_state("replay", str(receipt_path))
        if state.get("execution_status") == "blocked":
            return state
        try:
            original = json.loads(Path(receipt_path).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            original = {}
            failures = [{"path": str(receipt_path), "reason": f"invalid replay receipt: {exc}"}]
        else:
            failures = []
        if original.get("format") != "BOGK-brokered-process-receipt-8.0":
            failures.append({"path": str(receipt_path), "reason": "replay requires a brokered v8 process receipt"})
        else:
            try:
                validate_schema(original, "brokered-process-receipt.schema.json")
            except SchemaError as exc:
                failures.append({"path": str(receipt_path), "reason": str(exc)})

        replayed_calls = []
        app = original.get("app")
        self.workspace.state = self.workspace._read_state()
        app_info = self.workspace.state.get("apps", {}).get(app)
        verification = self.workspace._verify_installed_package(app_info["package"]) if app_info else None
        if not app_info or verification["execution_status"] != "completed":
            failures.append({"path": str(app), "reason": "current app package verification failed"})
        else:
            policy = self.workspace._verify_app_runtime_policy(app, app_info, verification)
            if _stable_hash(policy.get("policy")) != original.get("policy_sha256"):
                failures.append({"path": "bog_app.json", "reason": "app policy changed since recorded process"})
            calls = original.get("syscall_receipts", [])
            if [call.get("sequence") for call in calls] != list(range(1, len(calls) + 1)):
                failures.append({"path": str(receipt_path), "reason": "syscall sequence is not contiguous"})
            final_write_sequences = {
                call["path"]: call["sequence"]
                for call in calls
                if call["operation"] == "write" and call["execution_status"] == "completed"
            }
            for call in calls:
                verify_write_output = (
                    call["operation"] != "write"
                    or call["execution_status"] != "completed"
                    or final_write_sequences.get(call.get("path")) == call["sequence"]
                )
                replayed = self._replay_call(app_info, call, verify_write_output=verify_write_output)
                replayed_calls.append(replayed)
                if replayed["evidence_sha256"] != call["evidence_sha256"]:
                    failures.append({"path": call.get("path") or call.get("name") or call.get("package", ""), "reason": "syscall replay evidence mismatch"})
            if verification.get("bundle_sha256") != original.get("package_bundle_sha256"):
                failures.append({"path": app_info["package"], "reason": "package bundle changed since recorded process"})

        proof_material = dict(original.get("proof_material", {}))
        stdout = original.get("stdout") if isinstance(original.get("stdout"), str) else ""
        stderr = original.get("stderr") if isinstance(original.get("stderr"), str) else ""
        if hashlib.sha256(stdout.encode()).hexdigest() != proof_material.get("stdout_sha256"):
            failures.append({"path": str(receipt_path), "reason": "recorded stdout hash mismatch"})
        if hashlib.sha256(stderr.encode()).hexdigest() != proof_material.get("stderr_sha256"):
            failures.append({"path": str(receipt_path), "reason": "recorded stderr hash mismatch"})
        if original.get("returncode") != proof_material.get("returncode"):
            failures.append({"path": str(receipt_path), "reason": "recorded returncode mismatch"})
        recorded_proof = _stable_hash(proof_material)
        if recorded_proof != original.get("proof_sha256"):
            failures.append({"path": str(receipt_path), "reason": "recorded final proof hash mismatch"})
        if app_info and verification:
            replay_material = {
                **proof_material,
                "package_bundle_sha256": verification.get("bundle_sha256"),
                "installed_tree_sha256": verification.get("installed_tree_sha256"),
                "policy_sha256": _stable_hash(policy.get("policy")),
                "syscall_evidence": [call["evidence_sha256"] for call in replayed_calls],
            }
            replay_proof = _stable_hash(replay_material)
            if replay_proof != original.get("proof_sha256"):
                failures.append({"path": str(receipt_path), "reason": "replayed final proof hash mismatch"})
        else:
            replay_proof = None
        receipt = {
            "format": "BOGK-replay-receipt-8.0",
            "workspace": str(self.root),
            "source_receipt": str(receipt_path),
            "source_proof_sha256": original.get("proof_sha256"),
            "replayed_proof_sha256": replay_proof,
            "replayed_syscall_receipts": replayed_calls,
            "replay_verified": not failures,
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }
        return self._record_receipt("replay", str(app or "unknown"), receipt, state=state)

    def _finalize_brokered_process(
        self, state: dict, process_id: str, app: str, app_info: dict | None, verification: dict | None,
        policy: dict | None, calls: list[dict], result: subprocess.CompletedProcess | None, failures: list[dict],
        post_verification: dict | None = None,
    ) -> dict:
        policy_sha256 = _stable_hash(policy.get("policy")) if policy else None
        proof_material = {
            "app": app,
            "package": app_info.get("package") if app_info else None,
            "package_bundle_sha256": verification.get("bundle_sha256") if verification else None,
            "installed_tree_sha256": verification.get("installed_tree_sha256") if verification else None,
            "policy_sha256": policy_sha256,
            "syscall_evidence": [call["evidence_sha256"] for call in calls],
            "returncode": result.returncode if result else None,
            "stdout_sha256": hashlib.sha256((result.stdout if result else "").encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256((result.stderr if result else "").encode()).hexdigest(),
        }
        process = {
            "format": "BOGK-process-8.0",
            "process_id": process_id,
            "app": app,
            "package": app_info.get("package") if app_info else None,
            "mode": "brokered",
            "status": "exited" if not failures else "blocked",
        }
        _write_json(self.processes_dir / f"{process_id}.json", process)
        state["processes"][process_id] = process
        receipt = {
            "format": "BOGK-brokered-process-receipt-8.0",
            "workspace": str(self.root),
            "app": app,
            "process": process,
            "package_verification": verification,
            "dependency_verification": verification.get("dependency_verifications", {}) if verification else {},
            "app_policy_verification": policy,
            "post_run_verification": post_verification,
            "policy_sha256": policy_sha256,
            "package_bundle_sha256": verification.get("bundle_sha256") if verification else None,
            "syscall_receipts": calls,
            "stdout": result.stdout if result else "",
            "stderr": result.stderr if result else "",
            "returncode": result.returncode if result else None,
            "proof_material": proof_material,
            "proof_sha256": _stable_hash(proof_material),
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }
        try:
            validate_schema(receipt, "brokered-process-receipt.schema.json")
        except SchemaError as exc:
            raise BogKernelError(str(exc)) from exc
        return self._record_receipt("run-brokered", app, receipt, state=state)

    def _replay_call(self, app_info: dict, call: dict, verify_write_output: bool = True) -> dict:
        operation = call["operation"]
        capabilities = app_info["capabilities"]
        evidence = {"operation": operation, "execution_status": call["execution_status"]}
        if operation in {"read", "write", "env", "dependency"}:
            current_verification = self.workspace._verify_installed_package(app_info["package"])
            evidence.update(
                package_verification_status=current_verification["execution_status"],
                package_tree_sha256=current_verification.get("installed_tree_sha256"),
            )
        if operation == "read":
            path = call["path"]
            evidence.update(path=path, allowed=path in capabilities["read"])
            if call["execution_status"] == "completed":
                target = Path(app_info["install_dir"]) / path
                install_dir = Path(app_info["install_dir"])
                safe_target = not target.is_symlink() and target.resolve().is_relative_to(install_dir.resolve())
                evidence["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest() if safe_target and target.is_file() else None
        elif operation == "write":
            path = call["path"]
            evidence.update(path=path, allowed=path in capabilities["write"])
            if call["execution_status"] == "completed" and verify_write_output:
                target = self.workspace.bogos / "appdata" / app_info["name"] / path
                runtime = self.workspace.bogos / "appdata" / app_info["name"]
                safe_target = not target.is_symlink() and target.resolve().is_relative_to(runtime.resolve())
                evidence["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest() if safe_target and target.is_file() else None
            else:
                evidence["sha256"] = call.get("sha256")
        elif operation == "env":
            name = call["name"]
            evidence.update(name=name, allowed=name in capabilities["env"], value=app_info["environment"].get(name))
        elif operation == "dependency":
            package = call["package"]
            allowed = package in capabilities["dependencies"]
            evidence.update(package=package, allowed=allowed)
            if allowed:
                verification = self.workspace._verify_installed_package(package)
                evidence.update(bundle_sha256=verification.get("bundle_sha256"), verification_status=verification["execution_status"])
        else:
            evidence["call_count"] = call.get("call_count")
        return {**evidence, "evidence_sha256": _stable_hash(evidence)}

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
            "format": "BOGK-syscall-receipt-8.0",
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
            "format": "BOGK-syscall-receipt-8.0",
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
            "format": "BOGK-syscall-receipt-8.0",
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
            "format": "BOGK-blocked-receipt-8.0",
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
                "format": "BOGK-mount-8.0",
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
        if state.get("format") == LEGACY_KERNEL_STATE_FORMAT:
            state["format"] = KERNEL_STATE_FORMAT
            self._write_state(state)
        elif state.get("format") != KERNEL_STATE_FORMAT:
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


class _CapabilityBroker:
    def __init__(self, kernel: BogKernel, state: dict, app: str, app_info: dict, verification: dict, token: str) -> None:
        self.kernel = kernel
        self.state = state
        self.app = app
        self.app_info = app_info
        self.verification = verification
        self.token = token
        self.calls: list[dict] = []
        self.socket_path = Path(tempfile.gettempdir()) / f"bogk_{secrets.token_hex(12)}.sock"
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.thread = threading.Thread(target=self._serve, name=f"bogk-broker-{app}", daemon=True)
        self.running = False

    def start(self) -> None:
        self.socket_path.unlink(missing_ok=True)
        self.server.bind(str(self.socket_path))
        self.socket_path.chmod(0o600)
        self.server.listen()
        self.server.settimeout(0.2)
        self.running = True
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        self.thread.join(timeout=2)
        self.server.close()
        self.socket_path.unlink(missing_ok=True)

    def _serve(self) -> None:
        while self.running:
            try:
                connection, _ = self.server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with connection:
                try:
                    request = json.loads(_socket_line(connection))
                    response = self._handle(request)
                except Exception as exc:
                    response = {
                        "execution_status": "blocked",
                        "failures": [{"path": "broker", "reason": str(exc)}],
                    }
                connection.sendall(json.dumps(response, sort_keys=True, separators=(",", ":")).encode() + b"\n")

    def _handle(self, request: dict) -> dict:
        operation = request.get("operation")
        failures = []
        evidence = {"operation": operation}
        response: dict[str, Any] = {}
        capabilities = self.app_info["capabilities"]
        if request.get("token") != self.token:
            failures.append({"path": "broker", "reason": "invalid broker capability token"})
        elif operation in {"read", "write", "env", "dependency"}:
            current_verification = self.kernel.workspace._verify_installed_package(self.app_info["package"])
            evidence.update(
                package_verification_status=current_verification["execution_status"],
                package_tree_sha256=current_verification.get("installed_tree_sha256"),
            )
            if current_verification["execution_status"] != "completed":
                failures.extend(current_verification["failures"])

        if request.get("token") != self.token:
            pass
        elif operation == "read":
            path = request.get("path")
            evidence.update(path=path, allowed=path in capabilities["read"])
            if not _is_safe_relpath(path) or path not in capabilities["read"]:
                failures.append({"path": str(path), "reason": "read blocked by capability manifest"})
            elif not failures:
                target = Path(self.app_info["install_dir"]) / path
                install_dir = Path(self.app_info["install_dir"])
                if target.is_symlink() or not target.resolve().is_relative_to(install_dir.resolve()):
                    failures.append({"path": path, "reason": "capability read target is unsafe"})
                elif not target.is_file():
                    failures.append({"path": path, "reason": "capability read target missing"})
                else:
                    data = target.read_bytes()
                    evidence["sha256"] = hashlib.sha256(data).hexdigest()
                    response["data_hex"] = data.hex()
        elif operation == "write":
            path = request.get("path")
            evidence.update(path=path, allowed=path in capabilities["write"])
            try:
                data = bytes.fromhex(request.get("data_hex", ""))
            except ValueError:
                data = b""
                failures.append({"path": str(path), "reason": "invalid broker write data"})
            evidence["sha256"] = hashlib.sha256(data).hexdigest()
            if not _is_safe_relpath(path) or path not in capabilities["write"]:
                failures.append({"path": str(path), "reason": "write blocked by capability manifest"})
            if not failures:
                target = (self.kernel.workspace.bogos / "appdata" / self.app / path).resolve()
                runtime = (self.kernel.workspace.bogos / "appdata" / self.app).resolve()
                if not target.is_relative_to(runtime):
                    failures.append({"path": path, "reason": "broker write escaped appdata"})
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    response.update(size=len(data), sha256=evidence["sha256"])
        elif operation == "env":
            name = request.get("name")
            evidence.update(name=name, allowed=name in capabilities["env"], value=self.app_info["environment"].get(name))
            if name not in capabilities["env"]:
                failures.append({"path": str(name), "reason": "environment access blocked by capability manifest"})
            elif not failures:
                response["value"] = self.app_info["environment"][name]
        elif operation == "dependency":
            package = request.get("package")
            allowed = package in capabilities["dependencies"]
            evidence.update(package=package, allowed=allowed)
            if not allowed:
                failures.append({"path": str(package), "reason": "dependency access blocked by capability manifest"})
            elif not failures:
                dependency_verification = self.kernel.workspace._verify_installed_package(package)
                evidence.update(
                    bundle_sha256=dependency_verification.get("bundle_sha256"),
                    verification_status=dependency_verification["execution_status"],
                )
                if dependency_verification["execution_status"] != "completed":
                    failures.extend(dependency_verification["failures"])
                else:
                    response["verification"] = dependency_verification
        elif operation == "receipt":
            evidence["call_count"] = len(self.calls)
            response["calls"] = list(self.calls)
        else:
            failures.append({"path": str(operation), "reason": "unknown broker capability operation"})

        evidence["execution_status"] = "completed" if not failures else "blocked"
        call = {
            "format": "BOGK-capability-syscall-receipt-8.0",
            "sequence": len(self.calls) + 1,
            "app": self.app,
            **evidence,
            "evidence_sha256": _stable_hash(evidence),
            "failures": failures,
            "execution_status": evidence["execution_status"],
        }
        self.calls.append(call)
        return {**response, "receipt": call, "failures": failures, "execution_status": call["execution_status"]}


def _socket_line(connection: socket.socket) -> str:
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = connection.recv(65536)
        if not chunk:
            break
        data.extend(chunk)
    return data.decode("utf-8")


def _resolve_entrypoint(install_dir: Path, entrypoint: list[str]) -> list[str]:
    command = [str(part) for part in entrypoint]
    if len(command) >= 2 and _is_safe_relpath(command[1]) and (install_dir / command[1]).is_file():
        command[1] = str((install_dir / command[1]).resolve())
    elif command and _is_safe_relpath(command[0]) and (install_dir / command[0]).is_file():
        command[0] = str((install_dir / command[0]).resolve())
    return command


def _brokered_environment(app_info: dict, app: str, install_dir: Path, runtime_dir: Path, socket_path: Path, token: str) -> dict[str, str]:
    repo = Path(__file__).resolve().parents[1]
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": str(repo),
        "BOG_APP_NAME": app,
        "BOG_APP_PACKAGE": app_info["package"],
        "BOG_PACKAGE_DIR": str(install_dir),
        "BOG_APP_RUNTIME_DIR": str(runtime_dir),
        "BOG_BROKER_SOCKET": str(socket_path),
        "BOG_BROKER_TOKEN": token,
    }
    return environment


def _snapshot(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _snapshot_changes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(set(before) ^ set(after) | {path for path in set(before) & set(after) if before[path] != after[path]})


def _stable_hash(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
