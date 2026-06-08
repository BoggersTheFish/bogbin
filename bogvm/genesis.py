from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

from .bogos import BogOSError, Workspace
from .kernel import BogKernel
from .schema import SchemaError, validate_schema
from .signing import canonical_bytes, sign_object, verify_object_signature
from .store import _directory_hash, package_directory, read_store_index


GENESIS_FORMAT = "BOGOS-Genesis-9.0"
LEDGER_FORMAT = "BOGOS-Genesis-ledger-entry-9.0"
REGISTRY_FORMAT = "BOGOS-Genesis-registry-9.0"
LOCK_FORMAT = "BOGOS-Genesis-lock-9.0"
ZERO_HASH = "0" * 64


class GenesisError(BogOSError):
    pass


class Genesis:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.root = workspace.root
        self.dir = workspace.bogos / "genesis"
        self.ledger_dir = self.dir / "ledger"
        self.objects_dir = self.dir / "objects"
        self.states_dir = self.dir / "states"
        self.registry_dir = self.dir / "registry"
        self.registry_packages = self.registry_dir / "packages"
        self.session_path = self.dir / "session.json"
        self.lock_path = self.root / "bog.lock"
        self.private_key = workspace.bogos / "keys" / "workspace.key"
        self.trusted_keys = workspace._trusted_public_keys()
        self._ensure_layout()

    def boot(self) -> dict:
        registry = self.verify_registry(required=False)
        lock = self.verify_lock(required=False)
        kernel = BogKernel(self.workspace)
        kernel_boot = kernel.boot()
        state_root = self.current_root()
        material = {
            "workspace_sha256": self._workspace_hash(),
            "trust_store_sha256": self._directory_hash(self.workspace.bogos / "trust"),
            "installed_package_index_sha256": self._file_hash(self.workspace.bogos / "store" / "index.json"),
            "kernel_state_sha256": self._file_hash(kernel.state_path),
            "registry_sha256": registry.get("registry_sha256"),
            "lockfile_sha256": lock.get("lockfile_sha256"),
            "previous_receipt_root_hash": self.last_hash(),
            "state_root_sha256": state_root,
        }
        receipt = {
            "format": "BOGOS-Genesis-boot-receipt-9.0",
            "trusted_boot_completed": kernel_boot["execution_status"] == "completed",
            **material,
            "execution_status": "completed",
        }
        entry = self.record("trusted-boot", receipt)
        self._write_json(self.session_path, {
            "format": "BOGOS-Genesis-session-9.0",
            "boot_entry": entry["sequence"],
            "boot_receipt_hash": entry["receipt_hash"],
            "initial_state_root": state_root,
        })
        return entry

    def create_registry(self, package_sources: list[dict]) -> dict:
        if self.registry_dir.exists():
            shutil.rmtree(self.registry_dir)
        self.registry_packages.mkdir(parents=True)
        packages = {}
        for spec in package_sources:
            key = f"{spec['name']}-{spec['version']}"
            bundle = self.registry_packages / key
            package_receipt = package_directory(
                spec["source"],
                bundle,
                name=spec["name"],
                version=spec["version"],
                dependencies=spec.get("dependencies", []),
                signing_key=self.private_key,
            )
            packages[key] = {
                "name": spec["name"],
                "version": spec["version"],
                "dependencies": package_receipt["dependencies"],
                "bundle_sha256": package_receipt["bundle_sha256"],
                "archive_tree_sha256": package_receipt["archive_tree_sha256"],
                "public_key_id": package_receipt["signature"]["key_id"],
                "capability_requirements": spec.get("capabilities", {}),
                "receipt_hash": self._stable_hash(package_receipt),
                "bundle": f"packages/{key}",
            }
        index = {"format": REGISTRY_FORMAT, "packages": packages}
        signed = {**index, "signature": sign_object(index, self.private_key)}
        self._write_json(self.registry_dir / "index.json", signed)
        return self.sync_registry()

    def sync_registry(self) -> dict:
        verification = self.verify_registry(required=True)
        return self.record("registry-sync", {
            "format": "BOGOS-Genesis-registry-sync-receipt-9.0",
            **verification,
            "execution_status": verification["execution_status"],
        })

    def sync_registry_from(self, source: str | Path) -> dict:
        source_path = Path(source).resolve()
        if not (source_path / "index.json").is_file():
            return self.record("registry-sync", {
                "format": "BOGOS-Genesis-registry-sync-receipt-9.0",
                "source": str(source_path),
                "failures": [{"path": str(source_path), "reason": "registry source is missing index.json"}],
                "execution_status": "blocked",
            })
        if self.registry_dir.exists():
            shutil.rmtree(self.registry_dir)
        shutil.copytree(source_path, self.registry_dir)
        receipt = self.sync_registry()
        receipt["source"] = str(source_path)
        return receipt

    def verify_registry(self, required: bool = True) -> dict:
        path = self.registry_dir / "index.json"
        if not path.exists():
            return self._missing("registry", required)
        try:
            signed = json.loads(path.read_text())
            signature = signed.pop("signature")
            result = verify_object_signature(signed, signature, self.trusted_keys)
            failures = [] if result["verified"] else [{"path": str(path), "reason": result["reason"]}]
            if signed.get("format") != REGISTRY_FORMAT:
                failures.append({"path": str(path), "reason": "unsupported Genesis registry format"})
            for key, item in signed.get("packages", {}).items():
                bundle = (self.registry_dir / item["bundle"]).resolve()
                if not bundle.is_relative_to(self.registry_dir.resolve()):
                    failures.append({"path": key, "reason": "registry package path escapes registry"})
                    continue
                receipt = json.loads((bundle / "receipt.json").read_text())
                if receipt["bundle_sha256"] != item["bundle_sha256"]:
                    failures.append({"path": key, "reason": "registry package bundle hash mismatch"})
                if _directory_hash(bundle) != item["bundle_sha256"]:
                    failures.append({"path": key, "reason": "registry package content hash mismatch"})
                if self._stable_hash(receipt) != item["receipt_hash"]:
                    failures.append({"path": key, "reason": "registry package receipt hash mismatch"})
                unsigned_receipt = dict(receipt)
                package_signature = unsigned_receipt.pop("signature", {})
                if not verify_object_signature(unsigned_receipt, package_signature, self.trusted_keys)["verified"]:
                    failures.append({"path": key, "reason": "registry package signature is not trusted"})
                expected = {
                    "name": receipt["name"],
                    "version": receipt["version"],
                    "dependencies": receipt["dependencies"],
                    "bundle_sha256": receipt["bundle_sha256"],
                    "archive_tree_sha256": receipt["archive_tree_sha256"],
                    "public_key_id": receipt["signature"]["key_id"],
                }
                if any(item.get(field) != value for field, value in expected.items()):
                    failures.append({"path": key, "reason": "registry package metadata does not match signed receipt"})
            return {
                "registry_signature_verified": result["verified"],
                "registry_sha256": self._stable_hash(signed),
                "package_count": len(signed.get("packages", {})),
                "failures": failures,
                "execution_status": "completed" if not failures else "blocked",
            }
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            return self._blocked(str(path), str(exc))

    def create_lock(self) -> dict:
        registry = self._registry_index()
        lock = {
            "format": LOCK_FORMAT,
            "registry_sha256": self._stable_hash({k: v for k, v in registry.items() if k != "signature"}),
            "registry_signature": registry["signature"],
            "trust_key_ids": sorted(self._trusted_key_ids()),
            "packages": registry["packages"],
        }
        signed = {**lock, "signature": sign_object(lock, self.private_key)}
        self._write_json(self.lock_path, signed)
        return self.record("lock", {
            "format": "BOGOS-Genesis-lock-receipt-9.0",
            **self.verify_lock(required=True),
        })

    def verify_lock(self, required: bool = True) -> dict:
        if not self.lock_path.exists():
            return self._missing("lockfile", required)
        try:
            signed = json.loads(self.lock_path.read_text())
            signature = signed.pop("signature")
            result = verify_object_signature(signed, signature, self.trusted_keys)
            registry = self.verify_registry(required=True)
            failures = [] if result["verified"] else [{"path": str(self.lock_path), "reason": result["reason"]}]
            if signed["registry_sha256"] != registry.get("registry_sha256"):
                failures.append({"path": str(self.lock_path), "reason": "lockfile registry hash mismatch"})
            if signed["trust_key_ids"] != sorted(self._trusted_key_ids()):
                failures.append({"path": str(self.lock_path), "reason": "lockfile trust keys mismatch"})
            if signed["packages"] != self._registry_index().get("packages"):
                failures.append({"path": str(self.lock_path), "reason": "lockfile package pins do not match registry"})
            return {
                "lockfile_verified": not failures,
                "lockfile_sha256": self._stable_hash(signed),
                "packages": sorted(signed["packages"]),
                "failures": failures,
                "execution_status": "completed" if not failures else "blocked",
            }
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            return self._blocked(str(self.lock_path), str(exc))

    def install(self, package: str) -> dict:
        registry_check = self.verify_registry(required=True)
        lock_check = self.verify_lock(required=True)
        failures = registry_check["failures"] + lock_check["failures"]
        lock = json.loads(self.lock_path.read_text()) if self.lock_path.exists() else {}
        entry = lock.get("packages", {}).get(package)
        if entry is None:
            failures.append({"path": package, "reason": "package is not pinned by bog.lock"})
        install_receipt = None
        if not failures:
            install_receipt = self.workspace.install_package(self.registry_dir / entry["bundle"])
            failures.extend(install_receipt.get("failures", []))
        return self.record("install", {
            "format": "BOGOS-Genesis-install-receipt-9.0",
            "package": package,
            "registry_signature_verified": registry_check["registry_signature_verified"],
            "lockfile_verified": lock_check["lockfile_verified"],
            "package_install": install_receipt,
            "dependencies_verified": bool(install_receipt and install_receipt["execution_status"] == "completed"),
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        })

    def fs_write(self, path: str, data: str | bytes, capability: str = "shell") -> dict:
        rel = self._safe_path(path)
        encoded = data.encode() if isinstance(data, str) else bytes(data)
        before = self.current_manifest()
        object_hash = hashlib.sha256(encoded).hexdigest()
        object_path = self.objects_dir / object_hash
        if not object_path.exists():
            object_path.write_bytes(encoded)
        after = dict(before)
        after[rel] = {"object_sha256": object_hash, "size": len(encoded)}
        before_root = self._manifest_root(before)
        after_root = self._save_manifest(after)
        return self.record("fs-write", {
            "format": "BOGOS-Genesis-fs-write-receipt-9.0",
            "path": rel,
            "capability": capability,
            "object_sha256": object_hash,
            "before_root_sha256": before_root,
            "after_root_sha256": after_root,
            "execution_status": "completed",
        })

    def fs_read(self, path: str, capability: str = "shell") -> tuple[bytes, dict]:
        rel = self._safe_path(path)
        entry = self.current_manifest().get(rel)
        failures = [] if entry else [{"path": rel, "reason": "file does not exist in Genesis state"}]
        data = (self.objects_dir / entry["object_sha256"]).read_bytes() if entry else b""
        receipt = self.record("fs-read", {
            "format": "BOGOS-Genesis-fs-read-receipt-9.0",
            "path": rel,
            "capability": capability,
            "object_sha256": hashlib.sha256(data).hexdigest() if entry else None,
            "state_root_sha256": self.current_root(),
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        })
        return data, receipt

    def rollback(self, selector: str | int) -> dict:
        entry = self.read_entry(selector)
        target_root = (
            entry.get("after_root_sha256")
            or entry.get("state_root_sha256")
            or entry.get("initial_state_root")
        )
        failures = []
        if not target_root or not (self.states_dir / f"{target_root}.json").exists():
            failures.append({"path": str(selector), "reason": "receipt does not identify a recoverable state root"})
        before = self.current_root()
        if not failures:
            self._set_current_root(target_root)
        return self.record("rollback", {
            "format": "BOGOS-Genesis-rollback-receipt-9.0",
            "source_receipt": entry["receipt_hash"],
            "before_root_sha256": before,
            "after_root_sha256": target_root,
            "rollback_verified": not failures and self.current_root() == target_root,
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        })

    def replay_session(self, receipt_path: str | Path | None = None) -> dict:
        chain = self.verify_ledger()
        entries = self.entries()
        failures = list(chain["failures"])
        if any(entry.get("event") in {"registry-sync", "lock", "install", "app-run"} for entry in entries):
            registry = self.verify_registry(required=True)
            lock = self.verify_lock(required=True)
            failures.extend(registry["failures"])
            failures.extend(lock["failures"])
        source = None
        if receipt_path is not None:
            try:
                source = json.loads(Path(receipt_path).read_text())
                unsigned = dict(source)
                signature = unsigned.pop("signature")
                if not verify_object_signature(unsigned, signature, self.trusted_keys)["verified"]:
                    failures.append({"path": str(receipt_path), "reason": "source Genesis receipt signature is invalid"})
                if source.get("format") != "BOGOS-Genesis-final-receipt-9.0":
                    failures.append({"path": str(receipt_path), "reason": "source is not a Genesis final receipt"})
                known_hashes = {entry.get("receipt_hash") for entry in entries}
                if source.get("genesis_session_root") not in known_hashes:
                    failures.append({"path": str(receipt_path), "reason": "source Genesis session root is not in the ledger"})
            except (OSError, KeyError, json.JSONDecodeError) as exc:
                failures.append({"path": str(receipt_path), "reason": f"invalid source Genesis receipt: {exc}"})
        virtual_root = ZERO_HASH
        for entry in entries:
            if entry["event"] == "trusted-boot":
                virtual_root = entry.get("state_root_sha256", virtual_root)
            elif entry["event"] == "fs-write":
                if entry["before_root_sha256"] != virtual_root:
                    failures.append({"path": str(entry["sequence"]), "reason": "write replay root mismatch"})
                virtual_root = entry["after_root_sha256"]
                if not (self.objects_dir / entry["object_sha256"]).is_file():
                    failures.append({"path": entry["object_sha256"], "reason": "replay object missing"})
            elif entry["event"] == "rollback":
                virtual_root = entry["after_root_sha256"]
            elif entry["event"] == "install" and entry.get("execution_status") == "completed":
                verification = self.workspace._verify_installed_package(entry["package"])
                if verification["execution_status"] != "completed":
                    failures.append({"path": entry["package"], "reason": "installed package failed session replay verification"})
            elif entry["event"] == "app-run":
                process = entry.get("process_receipt", {})
                if self._stable_hash(process.get("proof_material", {})) != process.get("proof_sha256"):
                    failures.append({"path": entry.get("app", "app"), "reason": "brokered process proof hash mismatch"})
                for call in process.get("syscall_receipts", []):
                    evidence = {key: value for key, value in call.items() if key not in {"format", "sequence", "app", "evidence_sha256", "failures"}}
                    if self._stable_hash(evidence) != call.get("evidence_sha256"):
                        failures.append({"path": entry.get("app", "app"), "reason": "capability syscall evidence hash mismatch"})
        if virtual_root != self.current_root():
            failures.append({"path": "state", "reason": "replayed final workspace root mismatch"})
        result = {
            "format": "BOGOS-Genesis-session-replay-receipt-9.0",
            "source_receipt": str(receipt_path) if receipt_path else None,
            "source_genesis_session_root": source.get("genesis_session_root") if source else None,
            "ledger_root_sha256": chain["ledger_root_sha256"],
            "replayed_event_count": len(entries),
            "replayed_final_state_root_sha256": virtual_root,
            "full_session_replay_verified": not failures,
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }
        return self.record("replay-session", result)

    def demo(self) -> dict:
        self._reset_demo()
        sources = self._create_demo_packages()
        boot = self.boot()
        registry = self.create_registry(sources)
        lock = self.create_lock()
        installs = [self.install("genesis-lib-1.0.0"), self.install("note-app-1.0.0"), self.install("calc-app-1.0.0")]
        kernel = BogKernel(self.workspace)
        note = kernel.run("note-app", brokered=True)
        calc = kernel.run("calc-app", brokered=True)
        note_event = self._record_process(note)
        calc_event = self._record_process(calc)
        initial_entry = self.record("state-checkpoint", {
            "format": "BOGOS-Genesis-state-checkpoint-receipt-9.0",
            "state_root_sha256": self.current_root(),
            "execution_status": "completed",
        })
        write = self.fs_write("notes/today.txt", "hello from BogOS Genesis\n", capability="note-app")
        data, read = self.fs_read("notes/today.txt", capability="note-app")
        forbidden = kernel.syscall_write("note-app", "forbidden.txt", "blocked")
        forbidden_event = self.record("forbidden-access", {
            "format": "BOGOS-Genesis-forbidden-access-receipt-9.0",
            "kernel_receipt": forbidden,
            "forbidden_access_blocked": forbidden["execution_status"] == "blocked",
            "execution_status": "completed" if forbidden["execution_status"] == "blocked" else "blocked",
        })
        installed = Path(read_store_index(self.workspace.bogos / "store")["packages"]["note-app-1.0.0"]["install_dir"])
        tamper_target = installed / "app.py"
        original = tamper_target.read_bytes()
        tamper_target.write_bytes(original + b"\n# tampered\n")
        tampered = kernel.run("note-app", brokered=True)
        tamper_event = self.record("tamper-rejection", {
            "format": "BOGOS-Genesis-tamper-rejection-receipt-9.0",
            "kernel_receipt": tampered,
            "tampered_package_blocked": tampered["execution_status"] == "blocked",
            "execution_status": "completed" if tampered["execution_status"] == "blocked" else "blocked",
        })
        tamper_target.write_bytes(original)
        rollback = self.rollback(initial_entry["sequence"])
        pre_replay_chain = self.verify_ledger()
        replay = self.replay_session()
        calls = note.get("syscall_receipts", [])
        checks = {
            "trusted_boot_completed": boot["trusted_boot_completed"],
            "registry_signature_verified": registry["registry_signature_verified"],
            "lockfile_verified": lock["lockfile_verified"],
            "all_packages_signed": all(self._install_signature_ok(item) for item in installs),
            "all_dependencies_verified": all(item["dependencies_verified"] for item in installs),
            "all_apps_capability_brokered": note["execution_status"] == calc["execution_status"] == "completed",
            "all_state_changes_receipted": write["execution_status"] == "completed" and read["execution_status"] == "completed" and data.startswith(b"hello"),
            "forbidden_access_blocked": forbidden["execution_status"] == "blocked" and any(call["execution_status"] == "blocked" for call in calls),
            "tampered_package_blocked": tampered["execution_status"] == "blocked",
            "rollback_verified": rollback["rollback_verified"],
            "full_session_replay_verified": replay["full_session_replay_verified"],
        }
        final = {
            "format": "BOGOS-Genesis-final-receipt-9.0",
            **checks,
            "genesis_session_root": pre_replay_chain["ledger_root_sha256"],
            "final_state_root_sha256": self.current_root(),
            "proof": {
                "boot": boot["receipt_hash"],
                "registry": registry["receipt_hash"],
                "lock": lock["receipt_hash"],
                "installs": [item["receipt_hash"] for item in installs],
                "note_process": note_event["receipt_hash"],
                "calc_process": calc_event["receipt_hash"],
                "forbidden_access": forbidden_event["receipt_hash"],
                "tamper_rejection": tamper_event["receipt_hash"],
                "rollback": rollback["receipt_hash"],
                "replay": replay["receipt_hash"],
            },
            "execution_status": "completed" if all(checks.values()) else "blocked",
        }
        final_entry = self.record("genesis-final", final)
        final_path = self.dir / "genesis_receipt.json"
        self._write_json(final_path, final_entry)
        return final_entry

    def shell_command(self, command: str) -> dict | str:
        parts = command.strip().split(maxsplit=3)
        if not parts:
            return ""
        if parts[0] == "status":
            return {"format": GENESIS_FORMAT, "state_root_sha256": self.current_root(), **self.verify_ledger()}
        if parts[0] == "install" and len(parts) == 2:
            return self.install(parts[1])
        if parts[0] == "run" and len(parts) == 2:
            return BogKernel(self.workspace).run(parts[1], brokered=True)
        if parts[:2] == ["fs", "read"] and len(parts) == 3:
            return self.fs_read(parts[2])[0].decode(errors="replace")
        if parts[:2] == ["fs", "write"] and len(parts) == 4:
            return self.fs_write(parts[2], parts[3].strip('"'))
        if parts[0] == "ledger":
            return self.verify_ledger()
        if parts[0] == "rollback" and len(parts) == 2:
            return self.rollback(parts[1])
        if parts[:2] == ["replay", "session"]:
            return self.replay_session()
        raise GenesisError(f"unknown Genesis shell command: {command}")

    def record(self, event: str, receipt: dict) -> dict:
        sequence = len(self.entries()) + 1
        payload = {
            **receipt,
            "ledger_format": LEDGER_FORMAT,
            "sequence": sequence,
            "event": event,
            "previous_hash": self.last_hash(),
        }
        receipt_hash = self._stable_hash(payload)
        signed = {**payload, "receipt_hash": receipt_hash}
        signed["signature"] = sign_object(signed, self.private_key)
        try:
            validate_schema(signed, "genesis-receipt.schema.json")
        except SchemaError as exc:
            raise GenesisError(str(exc)) from exc
        self._write_json(self.ledger_dir / f"{sequence:06d}_{event}.json", signed)
        return signed

    def verify_ledger(self) -> dict:
        failures = []
        previous = ZERO_HASH
        for expected, entry in enumerate(self.entries(), 1):
            signature = entry.get("signature", {})
            unsigned = dict(entry)
            unsigned.pop("signature", None)
            payload = dict(unsigned)
            receipt_hash = payload.pop("receipt_hash", None)
            if entry.get("sequence") != expected:
                failures.append({"path": str(expected), "reason": "ledger sequence mismatch"})
            if entry.get("previous_hash") != previous:
                failures.append({"path": str(expected), "reason": "ledger previous hash mismatch"})
            if self._stable_hash(payload) != receipt_hash:
                failures.append({"path": str(expected), "reason": "ledger receipt hash mismatch"})
            if not verify_object_signature(unsigned, signature, self.trusted_keys)["verified"]:
                failures.append({"path": str(expected), "reason": "ledger signature verification failed"})
            previous = receipt_hash or previous
        return {
            "ledger_verified": not failures,
            "entry_count": len(self.entries()),
            "ledger_root_sha256": previous,
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }

    def entries(self) -> list[dict]:
        result = []
        for path in sorted(self.ledger_dir.glob("*.json")):
            try:
                result.append(json.loads(path.read_text()))
            except json.JSONDecodeError:
                result.append({"sequence": -1, "receipt_hash": "", "previous_hash": "", "signature": {}})
        return result

    def read_entry(self, selector: str | int) -> dict:
        if str(selector).isdigit():
            index = int(selector) - 1
            try:
                return self.entries()[index]
            except IndexError as exc:
                raise GenesisError(f"unknown ledger receipt: {selector}") from exc
        for entry in self.entries():
            if entry.get("receipt_hash") == selector:
                return entry
        raise GenesisError(f"unknown ledger receipt: {selector}")

    def last_hash(self) -> str:
        entries = self.entries()
        return entries[-1].get("receipt_hash", ZERO_HASH) if entries else ZERO_HASH

    def current_manifest(self) -> dict:
        pointer = self.dir / "current_root"
        if not pointer.exists():
            self._save_manifest({})
        root = pointer.read_text().strip()
        return json.loads((self.states_dir / f"{root}.json").read_text())["files"]

    def current_root(self) -> str:
        self.current_manifest()
        return (self.dir / "current_root").read_text().strip()

    def _save_manifest(self, files: dict) -> str:
        root = self._manifest_root(files)
        self._write_json(self.states_dir / f"{root}.json", {"format": "BOGFS-COW-state-9.0", "root_sha256": root, "files": files})
        self._set_current_root(root)
        return root

    def _set_current_root(self, root: str) -> None:
        (self.dir / "current_root").write_text(root + "\n")

    def _manifest_root(self, files: dict) -> str:
        return self._stable_hash({"files": files})

    def _registry_index(self) -> dict:
        try:
            return json.loads((self.registry_dir / "index.json").read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise GenesisError(f"invalid Genesis registry: {exc}") from exc

    def _reset_demo(self) -> None:
        for path in (self.ledger_dir, self.objects_dir, self.states_dir, self.registry_dir):
            if path.exists():
                shutil.rmtree(path)
        self.lock_path.unlink(missing_ok=True)
        self.session_path.unlink(missing_ok=True)
        self._ensure_layout()
        self._save_manifest({})

    def _create_demo_packages(self) -> list[dict]:
        demo = self.dir / "demo-sources"
        if demo.exists():
            shutil.rmtree(demo)
        lib = demo / "genesis-lib"
        lib.mkdir(parents=True)
        (lib / "proof.txt").write_text("verified Genesis dependency\n")
        note = self._write_demo_app(
            demo / "note-app", "note-app", "genesis-lib-1.0.0",
            "from bog_runtime import BogCapabilityError, bog_dependency, bog_read, bog_write\n"
            "print(bog_read('README.txt').decode().strip())\n"
            "print(bog_dependency('genesis-lib-1.0.0')['execution_status'])\n"
            "bog_write('note.log', 'note written through BogK\\n')\n"
            "try:\n    bog_read('secret.txt')\nexcept BogCapabilityError as exc:\n    print(f'blocked: {exc}')\n",
            "note.log",
        )
        calc = self._write_demo_app(
            demo / "calc-app", "calc-app", "genesis-lib-1.0.0",
            "from bog_runtime import bog_dependency, bog_read, bog_write\n"
            "bog_dependency('genesis-lib-1.0.0')\n"
            "value = sum(map(int, bog_read('numbers.txt').decode().split()))\n"
            "bog_write('result.txt', str(value))\nprint(value)\n",
            "result.txt",
            extra={"numbers.txt": "20 22\n"},
        )
        return [
            {"source": lib, "name": "genesis-lib", "version": "1.0.0"},
            {"source": note, "name": "note-app", "version": "1.0.0", "dependencies": ["genesis-lib-1.0.0"]},
            {"source": calc, "name": "calc-app", "version": "1.0.0", "dependencies": ["genesis-lib-1.0.0"]},
        ]

    def _write_demo_app(self, root: Path, name: str, dependency: str, source: str, output: str, extra: dict | None = None) -> Path:
        root.mkdir(parents=True)
        files = {"README.txt": f"BogOS Genesis signed {name}\n", "secret.txt": "not granted\n", "app.py": source, **(extra or {})}
        for path, data in files.items():
            (root / path).write_text(data)
        readable = sorted(path for path in files if path != "secret.txt")
        manifest = {
            "format": "BOGOS-app-manifest-8.0",
            "apps": {name: {
                "name": name,
                "entrypoint": [sys.executable, "app.py"],
                "allowed_files": readable,
                "expected_hashes": {path: self._file_hash(root / path) for path in readable},
                "permissions": {"network": False, "subprocess": False},
                "environment": {},
                "read_policy": {"allow": readable},
                "write_policy": {"mode": "allowed", "allow": [output]},
                "capabilities": {"read": [p for p in readable if p != "app.py"], "write": [output], "env": [], "dependencies": [dependency]},
                "receipt_path": ".bogos/receipts",
            }},
        }
        self._write_json(root / "bog_app.json", manifest)
        return root

    def _install_signature_ok(self, receipt: dict) -> bool:
        try:
            return receipt["package_install"]["store_receipt"]["signature_verification"]["trusted"]
        except (KeyError, TypeError):
            return False

    def _record_process(self, receipt: dict) -> dict:
        return self.record("app-run", {
            "format": "BOGOS-Genesis-app-run-receipt-9.0",
            "app": receipt.get("app"),
            "process_receipt": receipt,
            "all_apps_capability_brokered": receipt.get("execution_status") == "completed",
            "execution_status": receipt.get("execution_status", "blocked"),
        })

    def _workspace_hash(self) -> str:
        return self._directory_hash(self.root, exclude={self.dir, self.workspace.bogos / "kernel"})

    def _directory_hash(self, root: Path, exclude: set[Path] | None = None) -> str:
        exclude = {path.resolve() for path in (exclude or set())}
        h = hashlib.sha256()
        if not root.exists():
            return h.hexdigest()
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            if any(path.resolve().is_relative_to(blocked) for blocked in exclude):
                continue
            h.update(path.relative_to(root).as_posix().encode())
            h.update(b"\0")
            h.update(path.read_bytes())
        return h.hexdigest()

    def _trusted_key_ids(self) -> list[str]:
        from .signing import public_key_info
        return [public_key_info(path)["key_id"] for path in self.trusted_keys]

    def _safe_path(self, path: str) -> str:
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts or not path:
            raise GenesisError(f"unsafe Genesis path: {path}")
        return candidate.as_posix()

    def _file_hash(self, path: Path) -> str | None:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

    def _stable_hash(self, obj: Any) -> str:
        return hashlib.sha256(canonical_bytes(obj)).hexdigest()

    def _missing(self, name: str, required: bool) -> dict:
        failures = [{"path": name, "reason": f"{name} is missing"}] if required else []
        return {"failures": failures, "execution_status": "blocked" if required else "completed"}

    def _blocked(self, path: str, reason: str) -> dict:
        return {"failures": [{"path": path, "reason": reason}], "execution_status": "blocked"}

    def _ensure_layout(self) -> None:
        for path in (self.dir, self.ledger_dir, self.objects_dir, self.states_dir, self.registry_packages):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _write_json(path: Path, obj: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
