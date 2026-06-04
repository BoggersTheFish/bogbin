import hashlib
import tempfile
from pathlib import Path
import unittest

from bogvm.assembler import assemble_file
from bogvm.vm import run_file, run_file_with_block_receipt


class BOGVMResidualPatchingTests(unittest.TestCase):
    def test_residual_patch_accepts_exact_reconstruction(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "residual_patch_storage.bogbin"
            assemble_file("examples/residual_patch_storage.bogasm", out)
            receipt = run_file(out)

        expected = hashlib.sha256(bytes([10, 20, 10, 40, 10, 60, 10, 80])).hexdigest()

        self.assertEqual(receipt["bogbin"], "BOGBIN-2.0")
        self.assertEqual(receipt["vm"], "BOGVM-2.0")
        self.assertEqual(receipt["execution_status"], "completed")
        self.assertEqual(receipt["accepted_data_block_names"], ["generated_residual_exact"])
        self.assertEqual(receipt["accepted_without_verify"], 0)
        self.assertEqual(receipt["candidate_graph_contamination"], 0)

        apply_events = [e for e in receipt["events"] if e["opcode"] == "APPLY_RESIDUAL"]
        self.assertEqual(apply_events[0]["details"]["residual_count"], 4)

        verify_events = [e for e in receipt["events"] if e["opcode"] == "VERIFY_HASH"]
        self.assertEqual(verify_events[0]["details"]["result"], "verified")
        self.assertEqual(verify_events[0]["details"]["actual_hash"], expected)

    def test_residual_patch_bad_hash_blocks_accept_data(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "residual_patch_bad_hash.bogbin"
            assemble_file("examples/residual_patch_bad_hash.bogasm", out)
            receipt, exit_code = run_file_with_block_receipt(out)

        self.assertEqual(exit_code, 1)
        self.assertEqual(receipt["bogbin"], "BOGBIN-2.0")
        self.assertEqual(receipt["vm"], "BOGVM-2.0")
        self.assertEqual(receipt["execution_status"], "blocked")
        self.assertIn("ACCEPT_DATA without VERIFY_HASH", receipt["block_reason"])
        self.assertEqual(receipt["accepted_data_block_names"], [])
        self.assertEqual(receipt["accepted_without_verify"], 0)
        self.assertEqual(receipt["candidate_graph_contamination"], 0)

        verify_events = [e for e in receipt["events"] if e["opcode"] == "VERIFY_HASH"]
        self.assertEqual(verify_events[0]["details"]["result"], "rejected")


if __name__ == "__main__":
    unittest.main()
