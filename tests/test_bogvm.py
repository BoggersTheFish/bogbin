import tempfile
from pathlib import Path
import unittest

from bogvm.assembler import assemble_file
from bogvm.vm import run_file, VMError


class BOGVMTests(unittest.TestCase):
    def test_proof_chain_accepts(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "proof_chain.bogbin"
            assemble_file("examples/proof_chain.bogasm", out)
            receipt = run_file(out)

        self.assertIn("claim_A_C", receipt["accepted_claim_names"])
        self.assertEqual(receipt["accepted_without_verify"], 0)
        self.assertEqual(receipt["candidate_graph_contamination"], 0)

    def test_same_program_same_receipt_hash(self):
        with tempfile.TemporaryDirectory() as td:
            out1 = Path(td) / "a.bogbin"
            out2 = Path(td) / "b.bogbin"
            assemble_file("examples/proof_chain.bogasm", out1)
            assemble_file("examples/proof_chain.bogasm", out2)

            r1 = run_file(out1)
            r2 = run_file(out2)

        self.assertEqual(r1["receipt_hash"], r2["receipt_hash"])

    def test_accept_without_verify_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "bad.bogbin"
            assemble_file("examples/accept_without_verify.bogasm", out)

            with self.assertRaises(VMError):
                run_file(out)


if __name__ == "__main__":
    unittest.main()
