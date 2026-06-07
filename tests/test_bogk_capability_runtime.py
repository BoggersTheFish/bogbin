import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from bogvm.bogos import Workspace, init_workspace
from bogvm.kernel import BogKernel
from scripts.evaluate_bogk_capability_runtime import _write_app, _write_dependency, evaluate


class BogKCapabilityRuntimeTests(unittest.TestCase):
    def test_killer_demo_emits_completed_capability_proof(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            receipt = evaluate(root / "demo", root / "proof.json")
            self.assertEqual(receipt["format"], "BOGK-brokered-capability-proof-receipt-8.0")
            self.assertEqual(receipt["execution_status"], "completed")
            self.assertTrue(all(receipt["checks"].values()))

    def test_brokered_run_blocks_raw_runtime_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace_root = root / "workspace"
            init_workspace(workspace_root)
            workspace = Workspace.open(workspace_root)
            dependency = _write_dependency(workspace_root / "proof-lib")
            workspace.install_package(dependency, name="proof-lib", version="1.0.0")
            app = _write_app(workspace_root / "app")
            app_py = app / "app.py"
            app_py.write_text(app_py.read_text() + "\nfrom pathlib import Path\nPath('raw.txt').write_text('raw')\n")
            manifest = json.loads((app / "bog_app.json").read_text())
            import hashlib
            manifest["apps"]["capability-app"]["expected_hashes"]["app.py"] = hashlib.sha256(app_py.read_bytes()).hexdigest()
            (app / "bog_app.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            workspace.install_package(app, name="app", version="1.0.0", dependencies=["proof-lib-1.0.0"])
            kernel = BogKernel(workspace)
            kernel.boot()
            receipt = kernel.run("capability-app", brokered=True)
            self.assertEqual(receipt["execution_status"], "blocked")
            self.assertTrue(any("raw runtime write" in failure["reason"] for failure in receipt["failures"]))

    def test_replay_blocks_changed_brokered_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace_root = root / "workspace"
            init_workspace(workspace_root)
            workspace = Workspace.open(workspace_root)
            workspace.install_package(_write_dependency(workspace_root / "proof-lib"), name="proof-lib", version="1.0.0")
            workspace.install_package(
                _write_app(workspace_root / "app"),
                name="app",
                version="1.0.0",
                dependencies=["proof-lib-1.0.0"],
            )
            kernel = BogKernel(workspace)
            kernel.boot()
            run = kernel.run("capability-app", brokered=True)
            receipt_path = Path(json.loads(kernel.state_path.read_text())["last_receipt"])
            self.assertEqual(run["execution_status"], "completed")
            tampered_receipt_path = root / "tampered-receipt.json"
            tampered_receipt = json.loads(receipt_path.read_text())
            tampered_receipt["stdout"] += "tampered\n"
            tampered_receipt_path.write_text(json.dumps(tampered_receipt, indent=2, sort_keys=True) + "\n")
            tampered_replay = kernel.replay(tampered_receipt_path)
            self.assertEqual(tampered_replay["execution_status"], "blocked")
            self.assertTrue(any("stdout hash mismatch" in failure["reason"] for failure in tampered_replay["failures"]))

            (workspace_root / ".bogos" / "appdata" / "capability-app" / "run.log").write_text("changed\n")
            replay = kernel.replay(receipt_path)
            self.assertEqual(replay["execution_status"], "blocked")
            self.assertTrue(any("syscall replay evidence mismatch" in failure["reason"] for failure in replay["failures"]))

    def test_brokered_run_blocks_direct_overwrite_of_broker_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace_root = root / "workspace"
            init_workspace(workspace_root)
            workspace = Workspace.open(workspace_root)
            workspace.install_package(_write_dependency(workspace_root / "proof-lib"), name="proof-lib", version="1.0.0")
            app = _write_app(workspace_root / "app")
            app_py = app / "app.py"
            app_py.write_text(app_py.read_text() + "\nfrom pathlib import Path\nPath('run.log').write_text('overwritten')\n")
            manifest = json.loads((app / "bog_app.json").read_text())
            import hashlib
            manifest["apps"]["capability-app"]["expected_hashes"]["app.py"] = hashlib.sha256(app_py.read_bytes()).hexdigest()
            (app / "bog_app.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            workspace.install_package(app, name="app", version="1.0.0", dependencies=["proof-lib-1.0.0"])
            kernel = BogKernel(workspace)
            kernel.boot()
            receipt = kernel.run("capability-app", brokered=True)
            self.assertEqual(receipt["execution_status"], "blocked")
            self.assertTrue(any("brokered output changed" in failure["reason"] for failure in receipt["failures"]))

    def test_brokered_run_and_replay_cli(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace_root = root / "workspace"
            init_workspace(workspace_root)
            workspace = Workspace.open(workspace_root)
            workspace.install_package(_write_dependency(workspace_root / "proof-lib"), name="proof-lib", version="1.0.0")
            workspace.install_package(_write_app(workspace_root / "app"), name="app", version="1.0.0", dependencies=["proof-lib-1.0.0"])
            BogKernel(workspace).boot()

            run = _run_bog(workspace_root, "kernel", "run", "--brokered", "capability-app")
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
            self.assertEqual(json.loads(run.stdout)["format"], "BOGK-brokered-process-receipt-8.0")
            receipt_path = json.loads((workspace_root / ".bogos" / "kernel" / "state.json").read_text())["last_receipt"]
            replay = _run_bog(workspace_root, "kernel", "replay", receipt_path)
            self.assertEqual(replay.returncode, 0, replay.stderr + replay.stdout)
            self.assertTrue(json.loads(replay.stdout)["replay_verified"])


def _run_bog(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    return subprocess.run(
        [sys.executable, "-m", "bog", "--workspace", str(workspace), *args],
        cwd=workspace,
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )


if __name__ == "__main__":
    unittest.main()
