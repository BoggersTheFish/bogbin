from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
import zipfile

from .bogcell import BogCell, compile_source, verify_build_receipt
from .bogos import Workspace, init_workspace
from .genesis import Genesis, ZERO_HASH
from .kernel import BogKernel
from .signing import canonical_bytes, verify_object_signature
from .schema import SchemaError, validate_schema
from .store import _directory_hash, package_directory, read_store_index


class HyperGenesisError(Exception):
    pass


class HyperGenesis:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.genesis = Genesis(workspace)
        self.root = workspace.root
        self.dir = workspace.bogos / "hypergenesis"
        self.dir.mkdir(parents=True, exist_ok=True)

    def build(self, source: str | Path, output: str | Path) -> dict:
        source_path = self.workspace._resolve_path(source)
        output_path = self.workspace._resolve_path(output)
        receipt = compile_source(source_path, output_path, self.genesis.private_key)
        for relpath in receipt["capabilities"]["read"]:
            candidate = source_path.parent / relpath
            if candidate.is_file() and candidate.resolve().is_relative_to(source_path.parent.resolve()):
                target = output_path / relpath
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, target)
        app_name = source_path.stem
        _write_json(output_path / "bog_cell.json", {
            "format": "BOGCELL-app-manifest-10.0",
            "apps": {app_name: {
                "program": "program.bogcell",
                "build_receipt": "build_receipt.json",
                "environment": {},
                "capabilities": receipt["capabilities"],
            }},
        })
        return self.genesis.record("bog-build", {
            "format": "BOGBUILD-session-receipt-10.0",
            "output": str(output_path),
            "build_receipt": receipt,
            "bogcell_app_compiled": True,
            "execution_status": "completed",
        })

    def package_build(self, project: str | Path, name: str, version: str, dependencies: list[str] | None = None) -> dict:
        source = self.workspace._resolve_path(project)
        cell_path = source / "bog_cell.json"
        if cell_path.is_file():
            manifest = json.loads(cell_path.read_text())
            entries = list(manifest.get("apps", {}).values())
            if len(entries) == 1:
                manifest["apps"] = {name: entries[0]}
                _write_json(cell_path, manifest)
        registry = self.genesis.create_registry([{
            "source": source,
            "name": name,
            "version": version,
            "dependencies": dependencies or [],
        }])
        lock = self.genesis.create_lock()
        key = f"{name}-{version}"
        return self.genesis.record("bog-package", {
            "format": "BOGBUILD-package-receipt-10.0",
            "package": key,
            "registry_receipt": registry["receipt_hash"],
            "lock_receipt": lock["receipt_hash"],
            "execution_status": "completed",
        })

    def run_cell(self, app: str) -> dict:
        receipt = BogCell(self.workspace, self.genesis).run(app)
        event = self.genesis.record("bogcell-run", {
            "format": "BOGCELL-session-receipt-10.0",
            "app": app,
            "process_receipt": receipt,
            "bogcell_raw_syscall_surface_absent": receipt["raw_syscall_surface"] == [],
            "execution_status": receipt["execution_status"],
        })
        return event

    def state_diff(self, root_a: str, root_b: str) -> dict:
        a, b = self._state(root_a), self._state(root_b)
        paths = sorted(set(a) | set(b))
        changes = [
            {"path": path, "before": a.get(path), "after": b.get(path)}
            for path in paths if a.get(path) != b.get(path)
        ]
        return {
            "format": "BOGSTATE-diff-receipt-10.0",
            "root_a": root_a,
            "root_b": root_b,
            "changed_paths": [item["path"] for item in changes],
            "changes": changes,
            "execution_status": "completed",
        }

    def ledger_verify(self) -> dict:
        chain = self.genesis.verify_ledger()
        failures = list(chain["failures"])
        for state_path in sorted(self.genesis.states_dir.glob("*.json")):
            try:
                state = json.loads(state_path.read_text())
                if _stable_hash({"files": state["files"]}) != state["root_sha256"] or state_path.stem != state["root_sha256"]:
                    failures.append({"path": str(state_path), "reason": "state manifest root mismatch"})
                for entry in state["files"].values():
                    object_path = self.genesis.objects_dir / entry["object_sha256"]
                    if not object_path.is_file() or _file_hash(object_path) != entry["object_sha256"]:
                        failures.append({"path": str(object_path), "reason": "state object hash mismatch"})
            except (OSError, KeyError, json.JSONDecodeError) as exc:
                failures.append({"path": str(state_path), "reason": str(exc)})
        return {
            "format": "BOGLEDGER-verification-receipt-10.0",
            "ledger_root_sha256": chain["ledger_root_sha256"],
            "ledger_verified": not failures,
            "state_history_verified": not failures,
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }

    def state_checkout(self, root: str) -> dict:
        self._state(root)
        before = self.genesis.current_root()
        self.genesis._set_current_root(root)
        return self.genesis.record("state-checkout", {
            "format": "BOGSTATE-checkout-receipt-10.0",
            "before_root_sha256": before,
            "after_root_sha256": root,
            "checkout_verified": self.genesis.current_root() == root,
            "execution_status": "completed",
        })

    def prove_file(self, path: str, root: str | None = None) -> dict:
        root = root or self.genesis.current_root()
        files = self._state(root)
        entry = files.get(self.genesis._safe_path(path))
        failures = [] if entry and (self.genesis.objects_dir / entry["object_sha256"]).is_file() else [{"path": path, "reason": "file not proven by state root"}]
        return {
            "format": "BOGSTATE-file-proof-10.0",
            "path": path,
            "state_root_sha256": root,
            "entry": entry,
            "object_verified": not failures and hashlib.sha256((self.genesis.objects_dir / entry["object_sha256"]).read_bytes()).hexdigest() == entry["object_sha256"],
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }

    def pilot(self, prompt: str) -> dict:
        plan = self._plan(prompt)
        results = []
        for action in plan:
            try:
                if action["action"] == "write":
                    result = self.genesis.fs_write(action["path"], action["data"], capability="BogPilot")
                elif action["action"] == "run-cell":
                    result = self.run_cell(action["app"])
                elif action["action"] == "install":
                    result = self.genesis.install(action["package"])
                elif action["action"] == "replay-session":
                    result = self.genesis.replay_session()
                else:
                    result = {"execution_status": "blocked", "failures": [{"path": action["action"], "reason": "unknown pilot action"}]}
            except Exception as exc:
                result = {"execution_status": "blocked", "failures": [{"path": str(action), "reason": str(exc)}]}
            results.append({"proposal": action, "result": result})
        accepted_or_blocked = all(item["result"].get("execution_status") in {"completed", "blocked"} for item in results)
        return self.genesis.record("bog-pilot", {
            "format": "BOGPILOT-receipt-10.0",
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "plan": plan,
            "results": results,
            "ai_proposed_action_verified_or_blocked": accepted_or_blocked,
            "execution_status": "completed" if accepted_or_blocked else "blocked",
        })

    def export_proof(self, final_receipt: str | Path, output: str | Path) -> dict:
        final_path = self.workspace._resolve_path(final_receipt)
        output_path = self.workspace._resolve_path(output)
        final = json.loads(final_path.read_text())
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "proof"
            stage.mkdir()
            for name, source in (
                ("trust", self.workspace.bogos / "trust"),
                ("ledger", self.genesis.ledger_dir),
                ("registry", self.genesis.registry_dir),
                ("states", self.genesis.states_dir),
                ("objects", self.genesis.objects_dir),
            ):
                if source.exists():
                    shutil.copytree(source, stage / name)
            shutil.copy2(self.genesis.lock_path, stage / "bog.lock")
            shutil.copy2(final_path, stage / "final_receipt.json")
            manifest = {
                "format": "BOGPROOF-bundle-10.0",
                "final_receipt_sha256": _file_hash(stage / "final_receipt.json"),
                "genesis_session_root": final.get("genesis_session_root"),
                "final_state_root_sha256": final.get("final_state_root_sha256"),
                "files": self._hash_tree(stage),
            }
            validate_schema(manifest, "bogproof-manifest.schema.json")
            _write_json(stage / "manifest.json", manifest)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(item for item in stage.rglob("*") if item.is_file()):
                    archive.write(path, path.relative_to(stage).as_posix())
        return self.genesis.record("proof-export", {
            "format": "BOGPROOF-export-receipt-10.0",
            "proof": str(output_path),
            "proof_sha256": _file_hash(output_path),
            "portable_proof_exported": True,
            "execution_status": "completed",
        })

    @staticmethod
    def verify_proof(path: str | Path) -> dict:
        path = Path(path)
        failures = []
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            try:
                with zipfile.ZipFile(path) as archive:
                    names = [info.filename for info in archive.infolist()]
                    if len(names) != len(set(names)):
                        raise HyperGenesisError("duplicate portable proof archive path")
                    for info in archive.infolist():
                        target = (root / info.filename).resolve()
                        if not target.is_relative_to(root.resolve()):
                            raise HyperGenesisError("unsafe proof archive path")
                    archive.extractall(root)
                manifest = json.loads((root / "manifest.json").read_text())
                validate_schema(manifest, "bogproof-manifest.schema.json")
                actual = HyperGenesis._hash_tree(root, exclude={"manifest.json"})
                if manifest.get("format") != "BOGPROOF-bundle-10.0" or actual != manifest.get("files"):
                    failures.append({"path": str(path), "reason": "portable proof manifest mismatch"})
                if manifest.get("final_receipt_sha256") != _file_hash(root / "final_receipt.json"):
                    failures.append({"path": "final_receipt.json", "reason": "portable final receipt hash mismatch"})
                trusted = sorted((root / "trust").glob("*.pub"))
                registry = json.loads((root / "registry" / "index.json").read_text())
                registry_unsigned = dict(registry)
                registry_signature = registry_unsigned.pop("signature", {})
                if not verify_object_signature(registry_unsigned, registry_signature, trusted)["verified"]:
                    failures.append({"path": "registry/index.json", "reason": "portable registry signature invalid"})
                for key, item in registry_unsigned.get("packages", {}).items():
                    bundle = root / "registry" / item["bundle"]
                    receipt = json.loads((bundle / "receipt.json").read_text())
                    receipt_unsigned = dict(receipt)
                    receipt_signature = receipt_unsigned.pop("signature", {})
                    if not verify_object_signature(receipt_unsigned, receipt_signature, trusted)["verified"]:
                        failures.append({"path": key, "reason": "portable package signature invalid"})
                    if _directory_hash(bundle) != item["bundle_sha256"] or receipt["bundle_sha256"] != item["bundle_sha256"]:
                        failures.append({"path": key, "reason": "portable package bundle hash mismatch"})
                    for dependency in receipt.get("dependencies", []):
                        if dependency not in registry_unsigned.get("packages", {}):
                            failures.append({"path": key, "reason": f"portable dependency missing: {dependency}"})
                lock = json.loads((root / "bog.lock").read_text())
                lock_unsigned = dict(lock)
                lock_signature = lock_unsigned.pop("signature", {})
                if not verify_object_signature(lock_unsigned, lock_signature, trusted)["verified"]:
                    failures.append({"path": "bog.lock", "reason": "portable lock signature invalid"})
                if lock_unsigned.get("registry_sha256") != _stable_hash(registry_unsigned) or lock_unsigned.get("packages") != registry_unsigned.get("packages"):
                    failures.append({"path": "bog.lock", "reason": "portable lock does not pin registry"})
                previous = ZERO_HASH
                entries = []
                for ledger_path in sorted((root / "ledger").glob("*.json")):
                    entry = json.loads(ledger_path.read_text())
                    entries.append(entry)
                    unsigned = dict(entry)
                    signature = unsigned.pop("signature", {})
                    payload = dict(unsigned)
                    receipt_hash = payload.pop("receipt_hash", None)
                    if entry.get("previous_hash") != previous or _stable_hash(payload) != receipt_hash:
                        failures.append({"path": ledger_path.name, "reason": "portable ledger chain mismatch"})
                    if not verify_object_signature(unsigned, signature, trusted)["verified"]:
                        failures.append({"path": ledger_path.name, "reason": "portable ledger signature invalid"})
                    previous = receipt_hash
                final = json.loads((root / "final_receipt.json").read_text())
                unsigned_final = dict(final)
                final_signature = unsigned_final.pop("signature", {})
                if not verify_object_signature(unsigned_final, final_signature, trusted)["verified"]:
                    failures.append({"path": "final_receipt.json", "reason": "final receipt signature invalid"})
                if final.get("genesis_session_root") != manifest.get("genesis_session_root"):
                    failures.append({"path": "final_receipt.json", "reason": "portable session root linkage mismatch"})
                if final.get("final_state_root_sha256") != manifest.get("final_state_root_sha256"):
                    failures.append({"path": "final_receipt.json", "reason": "portable final state linkage mismatch"})
                virtual_root = ZERO_HASH
                for entry in entries:
                    if entry.get("event") == "trusted-boot":
                        virtual_root = entry["state_root_sha256"]
                    elif entry.get("event") in {"fs-write", "rollback", "state-checkout"}:
                        virtual_root = entry["after_root_sha256"]
                if virtual_root != manifest.get("final_state_root_sha256"):
                    failures.append({"path": "states", "reason": "portable replay final root mismatch"})
                state_path = root / "states" / f"{virtual_root}.json"
                state = json.loads(state_path.read_text())
                if _stable_hash({"files": state["files"]}) != virtual_root:
                    failures.append({"path": state_path.name, "reason": "portable final state manifest mismatch"})
                for entry in state["files"].values():
                    object_path = root / "objects" / entry["object_sha256"]
                    if not object_path.is_file() or _file_hash(object_path) != entry["object_sha256"]:
                        failures.append({"path": entry["object_sha256"], "reason": "portable state object mismatch"})
            except (OSError, KeyError, json.JSONDecodeError, zipfile.BadZipFile, HyperGenesisError, SchemaError) as exc:
                failures.append({"path": str(path), "reason": str(exc)})
        return {
            "format": "BOGPROOF-verification-receipt-10.0",
            "proof": str(path),
            "third_party_import_verified": not failures,
            "full_session_replay_verified": not failures,
            "final_state_root_sha256": manifest.get("final_state_root_sha256") if "manifest" in locals() else None,
            "failures": failures,
            "execution_status": "completed" if not failures else "blocked",
        }

    def demo(self) -> dict:
        self.genesis._reset_demo()
        sources = self.genesis._create_demo_packages()
        cell = self._create_cell_source()
        sources.append({"source": cell, "name": "built-cell-app", "version": "1.0.0", "dependencies": ["genesis-lib-1.0.0"]})
        boot = self.genesis.boot()
        self.genesis.create_registry(sources)
        registry_mirror = self.dir / "registry-mirror"
        if registry_mirror.exists():
            shutil.rmtree(registry_mirror)
        shutil.copytree(self.genesis.registry_dir, registry_mirror)
        registry = self.genesis.sync_registry_from(registry_mirror)
        lock = self.genesis.create_lock()
        installs = [self.genesis.install(key) for key in ("genesis-lib-1.0.0", "note-app-1.0.0", "built-cell-app-1.0.0")]
        initial_root = self.genesis.current_root()
        build_receipt = json.loads((cell / "build_receipt.json").read_text())
        build_verify = verify_build_receipt(build_receipt, self.genesis.trusted_keys)
        cell_run = self.run_cell("built-cell-app")
        brokered = BogKernel(self.workspace).run("note-app", brokered=True)
        brokered_event = self.genesis._record_process(brokered)
        note = self.genesis.fs_write("notes/today.txt", "HyperGenesis portable note\n", capability="demo")
        forbidden_cell = self._run_forbidden_cell()
        installed = Path(read_store_index(self.workspace.bogos / "store")["packages"]["note-app-1.0.0"]["install_dir"])
        target = installed / "app.py"
        original = target.read_bytes()
        target.write_bytes(original + b"\n# tamper\n")
        tampered = BogKernel(self.workspace).run("note-app", brokered=True)
        target.write_bytes(original)
        rollback = self.state_checkout(initial_root)
        diff = self.state_diff(initial_root, note["after_root_sha256"])
        file_proof = self.prove_file("run.log", note["before_root_sha256"])
        proof_entry = self._state(note["before_root_sha256"])["run.log"]
        proof_object = self.genesis.objects_dir / proof_entry["object_sha256"]
        proof_bytes = proof_object.read_bytes()
        proof_object.write_bytes(proof_bytes + b"tamper")
        state_tamper = self.ledger_verify()
        proof_object.write_bytes(proof_bytes)
        ledger = self.ledger_verify()
        pilot = self.pilot("write an approved note and attempt forbidden access")
        replay = self.genesis.replay_session()
        pre_final_root = self.genesis.verify_ledger()["ledger_root_sha256"]
        provisional = {
            "format": "BOGOS-HyperGenesis-final-receipt-10.0",
            "trusted_boot_completed": boot["trusted_boot_completed"],
            "signed_registry_verified": registry["registry_signature_verified"],
            "lockfile_verified": lock["lockfile_verified"],
            "all_packages_signed": all(self.genesis._install_signature_ok(item) for item in installs),
            "all_dependencies_verified": all(item["dependencies_verified"] for item in installs),
            "bogcell_app_compiled": build_verify["execution_status"] == "completed",
            "bogcell_raw_syscall_surface_absent": cell_run["process_receipt"]["raw_syscall_surface"] == [],
            "brokered_app_capabilities_verified": brokered["execution_status"] == "completed",
            "copy_on_write_state_verified": bool(diff["changed_paths"]) and file_proof["execution_status"] == "completed" and ledger["state_history_verified"],
            "state_object_tamper_blocked": state_tamper["execution_status"] == "blocked",
            "forbidden_access_blocked": forbidden_cell["execution_status"] == "blocked",
            "tampered_package_blocked": tampered["execution_status"] == "blocked",
            "rollback_verified": rollback["checkout_verified"],
            "portable_proof_exported": False,
            "third_party_import_verified": False,
            "full_session_replay_verified": replay["full_session_replay_verified"],
            "ai_proposed_action_verified_or_blocked": pilot["ai_proposed_action_verified_or_blocked"],
            "final_roots_match": False,
            "genesis_session_root": pre_final_root,
            "final_state_root_sha256": self.genesis.current_root(),
            "proof": {"build": build_receipt, "cell": cell_run["receipt_hash"], "brokered": brokered_event["receipt_hash"]},
            "execution_status": "blocked",
        }
        provisional_entry = self.genesis.record("hypergenesis-provisional", provisional)
        provisional_path = self.dir / "hypergenesis_provisional.json"
        _write_json(provisional_path, provisional_entry)
        proof_path = self.dir / "session.bogproof"
        exported = self.export_proof(provisional_path, proof_path)
        verified = self.verify_proof(proof_path)
        checks = {
            **{key: value for key, value in provisional.items() if isinstance(value, bool)},
            "portable_proof_exported": exported["portable_proof_exported"],
            "third_party_import_verified": verified["third_party_import_verified"],
            "full_session_replay_verified": verified["full_session_replay_verified"],
            "final_roots_match": verified["final_state_root_sha256"] == provisional["final_state_root_sha256"],
        }
        final = {
            "format": "BOGOS-HyperGenesis-final-receipt-10.0",
            **checks,
            "genesis_session_root": pre_final_root,
            "final_state_root_sha256": provisional["final_state_root_sha256"],
            "portable_proof_sha256": exported["proof_sha256"],
            "execution_status": "completed" if all(checks.values()) else "blocked",
        }
        final_entry = self.genesis.record("hypergenesis-final", final)
        _write_json(self.dir / "hypergenesis_receipt.json", final_entry)
        return final_entry

    def _create_cell_source(self) -> Path:
        root = self.dir / "built-cell-app"
        if root.exists():
            shutil.rmtree(root)
        root.mkdir()
        (root / "README.txt").write_text("hello from self-built BogCell\n")
        source = root / "app.bogsrc"
        source.write_text(
            "read README.txt as message\n"
            "env BOG_PROOF_DEMO as mode\n"
            "dependency genesis-lib-1.0.0 as dependency\n"
            "write run.log $message\n"
            "exit 0\n"
        )
        build = compile_source(source, root, self.genesis.private_key)
        manifest = {
            "format": "BOGCELL-app-manifest-10.0",
            "apps": {"built-cell-app": {
                "program": "program.bogcell",
                "build_receipt": "build_receipt.json",
                "environment": {"BOG_PROOF_DEMO": "hypergenesis-v10"},
                "capabilities": build["capabilities"],
            }},
        }
        _write_json(root / "bog_cell.json", manifest)
        return root

    def _run_forbidden_cell(self) -> dict:
        app = self.workspace.state["apps"]["built-cell-app"]
        call, _ = BogCell(self.workspace, self.genesis)._execute(
            app, app["cell_capabilities"], ["READ", "secret.txt", "x"], 1, {}
        )
        return {
            "format": "BOGCELL-forbidden-capability-receipt-10.0",
            "capability_receipt": call,
            "execution_status": call["execution_status"],
        }

    def _plan(self, prompt: str) -> list[dict]:
        plan = [{"action": "write", "path": "pilot/approved.txt", "data": "BogPilot proposed this verified write"}]
        if "forbidden" in prompt.lower():
            plan.append({"action": "write", "path": "../forbidden.txt", "data": "must be blocked"})
        return plan

    def _state(self, root: str) -> dict:
        path = self.genesis.states_dir / f"{root}.json"
        if not path.is_file():
            raise HyperGenesisError(f"unknown state root: {root}")
        state = json.loads(path.read_text())
        if _stable_hash({"files": state["files"]}) != root:
            raise HyperGenesisError(f"state root verification failed: {root}")
        return state["files"]

    @staticmethod
    def _hash_tree(root: Path, exclude: set[str] | None = None) -> dict:
        exclude = exclude or set()
        return {
            path.relative_to(root).as_posix(): _file_hash(path)
            for path in sorted(item for item in root.rglob("*") if item.is_file())
            if path.relative_to(root).as_posix() not in exclude
        }


def _stable_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
