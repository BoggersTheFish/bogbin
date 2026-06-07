from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bogvm.bogos import Workspace, init_workspace
from bogvm.kernel import BogKernel
from bogvm.schema import validate_schema


DEFAULT_ARTIFACT_DIR = ROOT / "artifacts" / "bogk_capability_runtime"
DEFAULT_RECEIPT_PATH = ROOT / "artifacts" / "bogk_capability_proof_receipt.json"


def evaluate(artifact_dir: Path = DEFAULT_ARTIFACT_DIR, receipt_path: Path = DEFAULT_RECEIPT_PATH) -> dict:
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    artifact_dir.mkdir(parents=True)
    workspace_root = artifact_dir / "workspace"
    init_workspace(workspace_root)
    workspace = Workspace.open(workspace_root)

    dependency = _write_dependency(workspace_root / "proof-lib")
    dependency_install = workspace.install_package(dependency, name="proof-lib", version="1.0.0")
    app = _write_app(workspace_root / "capability-app")
    app_install = workspace.install_package(
        app, name="capability-app", version="1.0.0", dependencies=["proof-lib-1.0.0"]
    )

    kernel = BogKernel(workspace)
    boot = kernel.boot()
    run = kernel.run("capability-app", brokered=True)
    process_receipt_path = Path(json.loads(kernel.state_path.read_text())["last_receipt"])
    replay = kernel.replay(process_receipt_path)

    installed_app = workspace_root / ".bogos" / "store" / "installed" / "capability-app-1.0.0" / "app.py"
    installed_app.write_text("print('tampered before broker start')\n")
    tampered = kernel.run("capability-app", brokered=True)

    calls = run["syscall_receipts"]
    checks = {
        "signed_dependency_verified": _signature_ok(dependency_install),
        "signed_app_verified": _signature_ok(app_install),
        "capability_manifest_valid": run["app_policy_verification"]["execution_status"] == "completed",
        "brokered_read_allowed": _call_status(calls, "read", "README.txt") == "completed",
        "brokered_write_allowed": _call_status(calls, "write", "run.log") == "completed",
        "forbidden_read_blocked": (
            _call_status(calls, "read", "secret.txt") == "blocked"
            and (workspace_root / ".bogos" / "store" / "installed" / "capability-app-1.0.0" / "secret.txt").is_file()
        ),
        "forbidden_write_blocked": (
            _call_status(calls, "write", "forbidden.log") == "blocked"
            and not (workspace_root / ".bogos" / "appdata" / "capability-app" / "forbidden.log").exists()
        ),
        "tampered_package_blocked": tampered["execution_status"] == "blocked" and not tampered["syscall_receipts"],
        "replay_verified": replay["execution_status"] == "completed" and replay["replay_verified"],
    }
    receipt = {
        "format": "BOGK-brokered-capability-proof-receipt-8.0",
        "workspace": str(workspace_root),
        "trusted_public_keys": {
            path.name: path.read_text().strip()
            for path in workspace._trusted_public_keys()
        },
        "checks": checks,
        "proof_chain": {
            "dependency_install": dependency_install,
            "app_install": app_install,
            "bogk_boot": boot,
            "brokered_process": run,
            "replay": replay,
            "tampered_process": tampered,
        },
        "execution_status": "completed" if all(checks.values()) else "blocked",
    }
    receipt["proof_sha256"] = _stable_hash(receipt)
    validate_schema(receipt, "receipt.schema.json")
    _write_json(receipt_path, receipt)
    return receipt


def main() -> None:
    receipt = evaluate()
    print(json.dumps({
        "receipt": str(DEFAULT_RECEIPT_PATH),
        "proof_sha256": receipt["proof_sha256"],
        "execution_status": receipt["execution_status"],
    }, indent=2, sort_keys=True))
    if receipt["execution_status"] != "completed":
        raise SystemExit(1)


def _write_dependency(root: Path) -> Path:
    root.mkdir()
    (root / "proof.txt").write_text("signed capability dependency\n")
    return root


def _write_app(root: Path) -> Path:
    root.mkdir()
    (root / "README.txt").write_text("BogK brokered capability proof\n")
    (root / "secret.txt").write_text("exists but is not granted\n")
    (root / "app.py").write_text(
        "from bog_runtime import BogCapabilityError, bog_dependency, bog_env, bog_read, bog_receipt, bog_write\n"
        "print(bog_read('README.txt').decode().strip())\n"
        "print(bog_env('BOG_PROOF_DEMO'))\n"
        "print(bog_dependency('proof-lib-1.0.0')['execution_status'])\n"
        "bog_write('run.log', 'brokered output\\n')\n"
        "for operation in (lambda: bog_read('secret.txt'), lambda: bog_write('forbidden.log', 'blocked')):\n"
        "    try:\n"
        "        operation()\n"
        "    except BogCapabilityError as exc:\n"
        "        print(f'blocked before broker access: {exc}')\n"
        "print(f'broker receipts before final receipt call: {len(bog_receipt())}')\n"
    )
    manifest = {
        "format": "BOGOS-app-manifest-8.0",
        "apps": {
            "capability-app": {
                "name": "capability-app",
                "entrypoint": [sys.executable, "app.py"],
                "allowed_files": ["README.txt", "app.py"],
                "expected_hashes": {"README.txt": _file_hash(root / "README.txt"), "app.py": _file_hash(root / "app.py")},
                "permissions": {"network": False, "subprocess": False},
                "environment": {"BOG_PROOF_DEMO": "brokered-v8"},
                "read_policy": {"allow": ["README.txt", "app.py"]},
                "write_policy": {"mode": "allowed", "allow": ["run.log"]},
                "capabilities": {
                    "read": ["README.txt"],
                    "write": ["run.log"],
                    "env": ["BOG_PROOF_DEMO"],
                    "dependencies": ["proof-lib-1.0.0"],
                },
                "receipt_path": ".bogos/receipts",
            }
        },
    }
    _write_json(root / "bog_app.json", manifest)
    return root


def _call_status(calls: list[dict], operation: str, path: str) -> str | None:
    return next((call["execution_status"] for call in calls if call["operation"] == operation and call.get("path") == path), None)


def _signature_ok(receipt: dict) -> bool:
    return receipt["store_receipt"]["signature_verification"]["trusted"]


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_hash(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
