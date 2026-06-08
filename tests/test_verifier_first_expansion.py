import json
from pathlib import Path
import tempfile
import unittest

from bogvm.bogboot import BogBoot
from bogvm.bogos import Workspace, init_workspace
from bogvm.mesh import BogMesh
from bogvm.swarm import BogPilotSwarm
from bogvm.vertical import vertical_demo


class VerifierFirstExpansionTests(unittest.TestCase):
    def _workspace(self, root: Path) -> Workspace:
        init_workspace(root)
        return Workspace.open(root)

    def test_bogboot_and_irq_gate_admit_or_quarantine(self):
        with tempfile.TemporaryDirectory() as td:
            boot = BogBoot(self._workspace(Path(td) / "node"))
            self.assertEqual(boot.boot()["execution_status"], "completed")
            accepted = boot.irq_claim("timer", b"tick", {"tick": 1}, ["hardware.timer.tick"])
            blocked = boot.irq_claim("keyboard", b"x", {"key": "x"}, [])
            self.assertTrue(accepted["accepted"])
            self.assertFalse(blocked["accepted"])
            self.assertEqual(boot.verify()["execution_status"], "completed")

    def test_mesh_converges_splits_and_rejects_untrusted_claims(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            node_a = self._workspace(root / "a")
            node_b = self._workspace(root / "b")
            mesh_a, mesh_b = BogMesh(node_a), BogMesh(node_b)
            mesh_a.trust_peer(node_b.bogos / "trust" / "workspace.pub")
            mesh_b.trust_peer(node_a.bogos / "trust" / "workspace.pub")
            first = mesh_a.propose("pkg/latest", "H1", context={"channel": "stable"}, capability_scope=["registry.publish"])
            self.assertEqual(first["outcomes"][0]["policy"], "converge")
            mesh_b.propose("pkg/latest", "H2", context={"channel": "stable"}, capability_scope=["registry.publish"])
            claim = next(mesh_b.claims_dir.glob("*.json"))
            self.assertEqual(mesh_a.import_claim(claim)["execution_status"], "completed")
            split = mesh_a.resolve("pkg/latest")
            self.assertTrue(split["context_split"])
            self.assertEqual(split["outcomes"][0]["policy"], "split")

    def test_swarm_selects_verified_best_path_and_replays(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = self._workspace(Path(td) / "node")
            swarm = BogPilotSwarm(workspace)
            receipt = swarm.tournament("repair", [
                {"action": "write", "path": "repair/a", "data": "a", "score": 4, "cost": 1},
                {"action": "write", "path": "repair/b", "data": "b", "score": 8, "cost": 2},
                {"action": "write", "path": "../bad", "data": "bad", "score": 99, "cost": 1},
            ])
            self.assertEqual(receipt["execution_status"], "completed")
            self.assertEqual(BogPilotSwarm.replay(receipt)["execution_status"], "completed")
            data, _ = swarm.genesis.fs_read("repair/b")
            self.assertEqual(data, b"b")

    def test_full_vertical_demo(self):
        with tempfile.TemporaryDirectory() as td:
            receipt = vertical_demo(self._workspace(Path(td) / "node"))
            self.assertEqual(receipt["execution_status"], "completed", json.dumps(receipt, indent=2))
            self.assertTrue(all(value for value in receipt.values() if isinstance(value, bool)))


if __name__ == "__main__":
    unittest.main()
