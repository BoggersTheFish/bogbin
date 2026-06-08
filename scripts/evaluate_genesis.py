from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bogvm.bogos import Workspace, init_workspace
from bogvm.genesis import Genesis


ARTIFACT_DIR = ROOT / "artifacts" / "genesis"
RECEIPT_PATH = ROOT / "artifacts" / "genesis_receipt.json"


def evaluate(artifact_dir: Path = ARTIFACT_DIR, receipt_path: Path = RECEIPT_PATH) -> dict:
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    artifact_dir.mkdir(parents=True)
    workspace = artifact_dir / "workspace"
    init_workspace(workspace)
    receipt = Genesis(Workspace.open(workspace)).demo()
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main() -> None:
    receipt = evaluate()
    print(json.dumps({
        "receipt": str(RECEIPT_PATH),
        "genesis_session_root": receipt["genesis_session_root"],
        "execution_status": receipt["execution_status"],
    }, indent=2, sort_keys=True))
    if receipt["execution_status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
