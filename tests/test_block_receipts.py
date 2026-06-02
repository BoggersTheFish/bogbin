import tempfile
from pathlib import Path
import unittest

from bogvm.assembler import assemble_file
from bogvm.vm import run_file_with_block_receipt


class BOGVMBlockReceiptTests(unittest.TestCase):
    def test_blocked_execution_emits_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "contradiction.bogbin"
            assemble_file("examples/contradiction.bogasm", out)
            receipt, exit_code = run_file_with_block_receipt(out)

        self.assertEqual(exit_code, 1)
        self.assertEqual(receipt["execution_status"], "blocked")
        self.assertIn("ACCEPT without VERIFY", receipt["block_reason"])
        self.assertEqual(receipt["accepted_without_verify"], 0)
        self.assertEqual(receipt["candidate_graph_contamination"], 0)

        opcodes = [event["opcode"] for event in receipt["events"]]
        self.assertIn("BLOCKED_EXECUTION", opcodes)


if __name__ == "__main__":
    unittest.main()
