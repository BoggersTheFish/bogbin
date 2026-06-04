import tempfile
from pathlib import Path
import unittest

from bogvm.assembler import assemble_file
from bogvm.vm import run_file_with_block_receipt


class BOGVMBlockReceiptTests(unittest.TestCase):
    def test_contradiction_is_repaired_without_blocking_execution(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "contradiction.bogbin"
            assemble_file("examples/contradiction.bogasm", out)
            receipt, exit_code = run_file_with_block_receipt(out)

        self.assertEqual(exit_code, 0)
        self.assertEqual(receipt["execution_status"], "completed")
        self.assertEqual(receipt["accepted_claim_names"], [])
        self.assertEqual(receipt["rejected_claim_names"], ["claim_A_C"])
        self.assertEqual(receipt["quarantined_claim_names"], ["claim_A_C"])
        self.assertEqual(receipt["accepted_without_verify"], 0)
        self.assertEqual(receipt["candidate_graph_contamination"], 0)

        opcodes = [event["opcode"] for event in receipt["events"]]
        self.assertIn("REPAIR_CONTRADICTION", opcodes)

    def test_unverified_accept_still_emits_block_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "bad.bogbin"
            assemble_file("examples/accept_without_verify.bogasm", out)
            receipt, exit_code = run_file_with_block_receipt(out)

        self.assertEqual(exit_code, 1)
        self.assertEqual(receipt["execution_status"], "blocked")
        self.assertIn("ACCEPT without VERIFY", receipt["block_reason"])

        opcodes = [event["opcode"] for event in receipt["events"]]
        self.assertIn("BLOCKED_EXECUTION", opcodes)


if __name__ == "__main__":
    unittest.main()
