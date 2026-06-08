from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bogvm.bogos import Workspace, init_workspace
from bogvm.hypergenesis import HyperGenesis


ARTIFACT_DIR = ROOT / "artifacts" / "hypergenesis"
RECEIPT_PATH = ROOT / "artifacts" / "hypergenesis_receipt.json"
PROOF_PATH = ROOT / "artifacts" / "hypergenesis_session.bogproof"


def evaluate(artifact_dir: Path = ARTIFACT_DIR, receipt_path: Path = RECEIPT_PATH, proof_path: Path = PROOF_PATH) -> dict:
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    artifact_dir.mkdir(parents=True)
    workspace = artifact_dir / "workspace"
    init_workspace(workspace)
    receipt = HyperGenesis(Workspace.open(workspace)).demo()
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    shutil.copy2(workspace / ".bogos" / "hypergenesis" / "session.bogproof", proof_path)
    return receipt


def main() -> None:
    receipt = evaluate()
    print(json.dumps({
        "receipt": str(RECEIPT_PATH),
        "portable_proof": str(PROOF_PATH),
        "final_state_root_sha256": receipt["final_state_root_sha256"],
        "execution_status": receipt["execution_status"],
    }, indent=2, sort_keys=True))
    if receipt["execution_status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
