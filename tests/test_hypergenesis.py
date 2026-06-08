import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from bogvm.bogcell import BogCell, compile_source, verify_build_receipt
from bogvm.bogos import Workspace, init_workspace
from bogvm.genesis import Genesis
from bogvm.hypergenesis import HyperGenesis


class HyperGenesisTests(unittest.TestCase):
    def test_bogbuild_and_bogcell_have_capability_only_io(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            init_workspace(root)
            workspace = Workspace.open(root)
            genesis = Genesis(workspace)
            source = root / "app.bogsrc"
            source.write_text("read README.txt as message\nwrite output.txt $message\nexit 0\n")
            app = root / "cell-app"
            app.mkdir()
            (app / "README.txt").write_text("cell data\n")
            receipt = compile_source(source, app, genesis.private_key)
            (app / "bog_cell.json").write_text(json.dumps({
                "format": "BOGCELL-app-manifest-10.0",
                "apps": {"cell-app": {
                    "program": "program.bogcell",
                    "capabilities": receipt["capabilities"],
                    "environment": {},
                }},
            }, indent=2, sort_keys=True) + "\n")
            workspace.install_package(app, name="cell-app", version="1.0.0")
            run = BogCell(workspace, genesis).run("cell-app")

            self.assertEqual(run["execution_status"], "completed")
            self.assertEqual(run["raw_syscall_surface"], [])
            self.assertEqual(genesis.fs_read("output.txt")[0], b"cell data\n")
            self.assertEqual(verify_build_receipt(receipt, genesis.trusted_keys)["execution_status"], "completed")

    def test_state_history_diff_checkout_file_proof_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            init_workspace(root)
            hyper = HyperGenesis(Workspace.open(root))
            before = hyper.genesis.current_root()
            write = hyper.genesis.fs_write("notes/today.txt", "verified")
            after = write["after_root_sha256"]
            self.assertEqual(hyper.state_diff(before, after)["changed_paths"], ["notes/today.txt"])
            self.assertTrue(hyper.prove_file("notes/today.txt", after)["object_verified"])
            self.assertTrue(hyper.state_checkout(before)["checkout_verified"])
            object_path = hyper.genesis.objects_dir / write["object_sha256"]
            object_path.write_text("tampered")
            self.assertEqual(hyper.ledger_verify()["execution_status"], "blocked")

    def test_portable_proof_verifies_without_source_private_key(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            init_workspace(root)
            hyper = HyperGenesis(Workspace.open(root))
            hyper.genesis.boot()
            hyper.genesis.create_registry([])
            hyper.genesis.create_lock()
            hyper.genesis.fs_write("portable.txt", "proof")
            final = hyper.genesis.record("hypergenesis-final", {
                "format": "BOGOS-HyperGenesis-final-receipt-10.0",
                "genesis_session_root": hyper.genesis.last_hash(),
                "final_state_root_sha256": hyper.genesis.current_root(),
                "execution_status": "completed",
            })
            final_path = root / "final.json"
            final_path.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
            proof = root / "session.bogproof"
            hyper.export_proof(final_path, proof)
            verify = HyperGenesis.verify_proof(proof)
            self.assertEqual(verify["execution_status"], "completed")
            self.assertTrue(verify["third_party_import_verified"])
            self.assertNotIn("workspace.key", {item.filename for item in __import__("zipfile").ZipFile(proof).infolist()})

    def test_pilot_blocks_unsafe_proposal_without_granting_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            init_workspace(root)
            receipt = HyperGenesis(Workspace.open(root)).pilot("write a note and attempt forbidden access")
            self.assertTrue(receipt["ai_proposed_action_verified_or_blocked"])
            self.assertEqual(receipt["results"][0]["result"]["execution_status"], "completed")
            self.assertEqual(receipt["results"][1]["result"]["execution_status"], "blocked")

    def test_hypergenesis_demo_cli(self):
        if os.environ.get("BOG_RUN_SLOW_HYPERGENESIS") != "1":
            self.skipTest("set BOG_RUN_SLOW_HYPERGENESIS=1 to run the full flagship demo")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "workspace"
            init_workspace(root)
            result = subprocess.run(
                [sys.executable, "-m", "bog", "--workspace", str(root), "hypergenesis", "demo"],
                cwd=root,
                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["format"], "BOGOS-HyperGenesis-final-receipt-10.0")
            self.assertEqual(receipt["execution_status"], "completed")
            self.assertTrue(all(value for value in receipt.values() if isinstance(value, bool)))


if __name__ == "__main__":
    unittest.main()
