import tempfile
from pathlib import Path
import unittest

from scripts.evaluate_signed_dependency_demo import evaluate


class SignedDependencyDemoTests(unittest.TestCase):
    def test_signed_dependency_demo_emits_final_proof_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            receipt = evaluate(root / "demo", root / "proof.json")
            self.assertEqual(receipt["format"], "BOGK-signed-dependency-proof-receipt-7.0")
            self.assertEqual(receipt["execution_status"], "completed")
            self.assertTrue(all(receipt["checks"].values()))
            self.assertTrue((root / "proof.json").is_file())


if __name__ == "__main__":
    unittest.main()
