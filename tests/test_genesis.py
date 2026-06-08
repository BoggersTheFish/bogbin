import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from bogvm.bogos import Workspace, init_workspace
from bogvm.genesis import Genesis


class GenesisTests(unittest.TestCase):
    def test_copy_on_write_ledger_rollback_and_replay(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            init_workspace(root)
            genesis = Genesis(Workspace.open(root))
            boot = genesis.boot()
            initial_root = genesis.current_root()
            write = genesis.fs_write("notes/today.txt", "hello")
            data, read = genesis.fs_read("notes/today.txt")
            rollback = genesis.rollback(boot["sequence"])
            replay = genesis.replay_session()

            self.assertEqual(data, b"hello")
            self.assertEqual(write["before_root_sha256"], initial_root)
            self.assertEqual(read["execution_status"], "completed")
            self.assertTrue(rollback["rollback_verified"])
            self.assertEqual(genesis.current_root(), initial_root)
            self.assertTrue(replay["full_session_replay_verified"])
            self.assertTrue(genesis.verify_ledger()["ledger_verified"])

    def test_ledger_rejects_edited_old_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            init_workspace(root)
            genesis = Genesis(Workspace.open(root))
            genesis.boot()
            genesis.fs_write("proof.txt", "proof")
            first = sorted(genesis.ledger_dir.glob("*.json"))[0]
            entry = json.loads(first.read_text())
            entry["workspace_sha256"] = "0" * 64
            first.write_text(json.dumps(entry, indent=2, sort_keys=True) + "\n")
            verification = genesis.verify_ledger()
            self.assertEqual(verification["execution_status"], "blocked")
            self.assertTrue(any("hash mismatch" in failure["reason"] for failure in verification["failures"]))

    def test_genesis_shell_commands(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            init_workspace(root)
            genesis = Genesis(Workspace.open(root))
            genesis.boot()
            genesis.shell_command('fs write notes/today.txt "hello"')
            self.assertEqual(genesis.shell_command("fs read notes/today.txt"), "hello")
            self.assertTrue(genesis.shell_command("ledger")["ledger_verified"])

    def test_genesis_demo_cli_emits_final_receipt(self):
        if os.environ.get("BOG_RUN_SLOW_GENESIS") != "1":
            self.skipTest("set BOG_RUN_SLOW_GENESIS=1 to run the full signed-package Genesis demo")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            init_workspace(root)
            result = subprocess.run(
                [sys.executable, "-m", "bog", "--workspace", str(root), "genesis", "demo"],
                cwd=root,
                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["format"], "BOGOS-Genesis-final-receipt-9.0")
            self.assertEqual(receipt["execution_status"], "completed")
            for key, value in receipt.items():
                if key.endswith("_verified") or key.endswith("_completed") or key.startswith("all_") or key.endswith("_blocked"):
                    self.assertTrue(value, key)


if __name__ == "__main__":
    unittest.main()
