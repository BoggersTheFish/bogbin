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


DEFAULT_ARTIFACT_DIR = ROOT / "artifacts" / "signed_dependency_demo"
DEFAULT_RECEIPT_PATH = ROOT / "artifacts" / "signed_dependency_proof_receipt.json"


def evaluate(
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    receipt_path: Path = DEFAULT_RECEIPT_PATH,
) -> dict:
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    artifact_dir.mkdir(parents=True)
    workspace_root = artifact_dir / "workspace"
    init_workspace(workspace_root)
    workspace = Workspace.open(workspace_root)

    dependency = _write_dependency(workspace_root / "proof-lib")
    dependency_install = workspace.install_package(dependency, name="proof-lib", version="1.0.0")

    app = _write_app(workspace_root / "signed-proof-app", write_path="run.log")
    archive = workspace.archive_project(app, name="signed-proof-app")
    app_install = workspace.install_package(
        app,
        name="signed-proof-app",
        version="1.0.0",
        dependencies=["proof-lib-1.0.0"],
    )
    package_verify = workspace.verify_package("signed-proof-app-1.0.0")

    kernel = BogKernel(workspace)
    boot = kernel.boot()
    run = kernel.run("signed-proof-app")

    installed_app = workspace_root / ".bogos" / "store" / "installed" / "signed-proof-app-1.0.0" / "app.py"
    installed_app.write_text("print('tampered')\n")
    tamper_block = kernel.run("signed-proof-app")

    bad_app = _write_app(workspace_root / "undeclared-writer", write_path="undeclared.txt")
    bad_install = workspace.install_package(
        bad_app,
        name="undeclared-writer",
        version="1.0.0",
        dependencies=["proof-lib-1.0.0"],
    )
    undeclared_write_block = kernel.run("signed-proof-app-bad-writer")

    checks = {
        "dependency_signed_and_verified": _signature_ok(dependency_install),
        "app_signed_and_verified": _signature_ok(app_install) and package_verify["execution_status"] == "completed",
        "dependency_verified_transitively": (
            package_verify["verification"]["dependency_verifications"]["proof-lib-1.0.0"]["execution_status"] == "completed"
        ),
        "archive_tree_verified": archive["execution_status"] == "completed",
        "app_policy_verified": run["delegated_app_receipt"]["runtime_policy"]["execution_status"] == "completed",
        "bogk_run_completed": run["execution_status"] == "completed",
        "tampering_blocked": tamper_block["execution_status"] == "blocked",
        "undeclared_write_blocked": undeclared_write_block["execution_status"] == "blocked",
        "bad_writer_package_signed": _signature_ok(bad_install),
    }
    receipt = {
        "format": "BOGK-signed-dependency-proof-receipt-7.0",
        "workspace": str(workspace_root),
        "trusted_public_keys": {
            path.name: path.read_text().strip()
            for path in workspace._trusted_public_keys()
        },
        "checks": checks,
        "proof_chain": {
            "dependency_install": dependency_install,
            "app_archive": archive,
            "app_install": app_install,
            "package_verification": package_verify,
            "bogk_boot": boot,
            "bogk_run": run,
            "tamper_rejection": tamper_block,
            "bad_writer_install": bad_install,
            "undeclared_write_rejection": undeclared_write_block,
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
    (root / "README.txt").write_text("signed proof dependency\n")
    return root


def _write_app(root: Path, write_path: str) -> Path:
    root.mkdir()
    app_name = "signed-proof-app" if write_path == "run.log" else "signed-proof-app-bad-writer"
    (root / "README.txt").write_text("signed dependency proof app\n")
    (root / "app.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        f"(Path(os.environ['BOG_APP_RUNTIME_DIR']) / {write_path!r}).write_text('proof\\n')\n"
        "print('signed dependency proof run')\n"
    )
    manifest = {
        "format": "BOGOS-app-manifest-6.0",
        "apps": {
            app_name: {
                "name": app_name,
                "entrypoint": [sys.executable, "app.py"],
                "allowed_files": ["README.txt", "app.py"],
                "expected_hashes": {
                    "README.txt": _file_hash(root / "README.txt"),
                    "app.py": _file_hash(root / "app.py"),
                },
                "permissions": {"network": False, "subprocess": False},
                "environment": {"BOG_PROOF_DEMO": "1"},
                "read_policy": {"allow": ["README.txt", "app.py"]},
                "write_policy": {"mode": "allowed", "allow": ["run.log"]},
                "receipt_path": ".bogos/receipts",
            }
        },
    }
    _write_json(root / "bog_app.json", manifest)
    return root


def _signature_ok(install_receipt: dict) -> bool:
    verification = install_receipt["store_receipt"]["signature_verification"]
    return verification["signed"] and verification["trusted"] and verification["execution_status"] == "completed"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_hash(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
