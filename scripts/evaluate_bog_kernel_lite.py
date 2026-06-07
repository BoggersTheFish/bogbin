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


DEFAULT_ARTIFACT_DIR = ROOT / "artifacts" / "bog_kernel_lite"
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "bog_kernel_lite_report.json"
DEFAULT_RECEIPT_PATH = ROOT / "artifacts" / "bog_kernel_lite_receipt.json"


def evaluate(
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    report_path: Path = DEFAULT_REPORT_PATH,
    receipt_path: Path = DEFAULT_RECEIPT_PATH,
) -> tuple[dict, dict]:
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    artifact_dir.mkdir(parents=True)
    workspace_root = artifact_dir / "workspace"
    init_receipt = init_workspace(workspace_root)
    workspace = Workspace.open(workspace_root)
    project = _write_fixture(workspace_root / "kernel-demo-app")
    archive_receipt = workspace.archive_project(project, name="kernel-demo")
    mount_receipt = workspace.mount_archive("kernel-demo", name="kernel-demo")
    install_receipt = workspace.install_package(project, name="kernel-demo-app", version="1.0.0")

    kernel = BogKernel(workspace)
    boot_receipt = kernel.boot()
    run_receipt = kernel.run("kernel-demo-app")
    read_receipt = kernel.syscall_read("kernel-demo", "README.txt")
    write_receipt = kernel.syscall_write("kernel-demo-app", "kernel.log", "BogK syscall write\n")
    blocked_write_receipt = kernel.syscall_write("kernel-demo-app", "blocked.txt", "rejected\n")
    status_receipt = kernel.status()

    expected = [
        init_receipt,
        archive_receipt,
        mount_receipt,
        install_receipt,
        boot_receipt,
        run_receipt,
        read_receipt,
        write_receipt,
        status_receipt,
    ]
    report = {
        "format": "BOGK-lite-report-8.0",
        "workspace": str(workspace_root),
        "boot_receipt": boot_receipt,
        "run_receipt": run_receipt,
        "read_receipt": read_receipt,
        "write_receipt": write_receipt,
        "blocked_write_receipt": blocked_write_receipt,
        "status_receipt": status_receipt,
        "execution_status": "completed"
        if all(item["execution_status"] == "completed" for item in expected)
        and blocked_write_receipt["execution_status"] == "blocked"
        else "blocked",
    }
    receipt = {
        "format": "BOGK-lite-receipt-8.0",
        "report_path": str(report_path),
        "execution_status": report["execution_status"],
        "report_sha256": _stable_json_hash(report),
    }
    _write_json(report_path, report)
    receipt["report_file_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    _write_json(receipt_path, receipt)
    return report, receipt


def main() -> None:
    report, receipt = evaluate()
    print(json.dumps({
        "report": str(DEFAULT_REPORT_PATH),
        "receipt": str(DEFAULT_RECEIPT_PATH),
        "execution_status": receipt["execution_status"],
    }, indent=2, sort_keys=True))
    if receipt["execution_status"] != "completed":
        raise SystemExit(1)


def _write_fixture(root: Path) -> Path:
    root.mkdir()
    (root / "README.txt").write_text("BogK kernel contract fixture\n")
    (root / "app.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "print('BogK delegated verified run')\n"
        "(Path(os.environ['BOG_APP_RUNTIME_DIR']) / 'run.log').write_text('run\\n')\n"
    )
    manifest = {
        "format": "BOGOS-app-manifest-6.0",
        "apps": {
            "kernel-demo-app": {
                "name": "kernel-demo-app",
                "entrypoint": [sys.executable, "app.py"],
                "allowed_files": ["README.txt", "app.py"],
                "expected_hashes": {
                    "README.txt": _sha256(root / "README.txt"),
                    "app.py": _sha256(root / "app.py"),
                },
                "permissions": {"network": False, "subprocess": False},
                "environment": {"BOGK_DEMO": "1"},
                "read_policy": {"allow": ["README.txt", "app.py"]},
                "write_policy": {"mode": "allowed", "allow": ["run.log", "kernel.log"]},
                "receipt_path": ".bogos/receipts",
            },
        },
    }
    (root / "bog_app.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return root


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_json_hash(obj: dict) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
