import hashlib
import tempfile
from pathlib import Path
import unittest

from bogvm.assembler import assemble_file
from bogvm.vm import run_file


class BOGVMIntegerWaveBasisTests(unittest.TestCase):
    def test_ramp_u8_basis_accepts_after_hash_verify(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "ramp_u8_storage.bogbin"
            assemble_file("examples/ramp_u8_storage.bogasm", out)
            receipt = run_file(out)

        expected = hashlib.sha256(bytes((10 + i) % 256 for i in range(16))).hexdigest()

        self.assertEqual(receipt["accepted_data_block_names"], ["generated_ramp_10x16"])
        self.assertEqual(receipt["accepted_without_verify"], 0)
        self.assertEqual(receipt["candidate_graph_contamination"], 0)

        verify_events = [e for e in receipt["events"] if e["opcode"] == "VERIFY_HASH"]
        self.assertEqual(verify_events[0]["details"]["result"], "verified")
        self.assertEqual(verify_events[0]["details"]["actual_hash"], expected)


if __name__ == "__main__":
    unittest.main()
