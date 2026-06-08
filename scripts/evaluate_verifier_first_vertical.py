from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bogvm.bogos import Workspace, init_workspace
from bogvm.vertical import vertical_demo


def evaluate(root: Path, output: Path) -> dict:
    if root.exists():
        shutil.rmtree(root)
    init_workspace(root)
    receipt = vertical_demo(Workspace.open(root))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


if __name__ == "__main__":
    result = evaluate(ROOT / "artifacts" / "verifier_first_vertical", ROOT / "artifacts" / "verifier_first_vertical_receipt.json")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["execution_status"] == "completed" else 1)
