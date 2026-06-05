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


DEFAULT_ARTIFACT_DIR = ROOT / "artifacts" / "bogos_lite_demo"
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "bogos_lite_demo_report.json"
DEFAULT_RECEIPT_PATH = ROOT / "artifacts" / "bogos_lite_demo_receipt.json"


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
    demo_receipt = workspace.demo(None, public=True)
    status = workspace.status(verbose=True)
    latest = workspace.read_receipt("latest")

    report = {
        "format": "BOGOS-lite-public-demo-report-5.0",
        "workspace": str(workspace_root),
        "init_receipt": init_receipt,
        "demo_receipt": demo_receipt,
        "status": status,
        "latest_receipt": latest,
        "execution_status": demo_receipt["execution_status"],
    }
    receipt = {
        "format": "BOGOS-lite-public-demo-receipt-5.0",
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


def _stable_json_hash(obj: dict) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
