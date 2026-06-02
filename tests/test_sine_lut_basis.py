import hashlib
import tempfile
from pathlib import Path
import unittest

from bogvm.assembler import assemble_file
from bogvm.vm import run_file, run_file_with_block_receipt


def sine8_bytes(start: int, length: int) -> bytes:
    offsets = (0, 90, 127, 90, 0, -90, -127, -90)
    return bytes((start + offsets[i % len(offsets)]) % 256 for i in range(length))


class BOGVMSineLUTBasisTests(unittest.TestCase):
    def test_sine8_u8_accepts_after_hash_verify(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "sine8_u8_storage.bogbin"
            assemble_file("examples/sine8_u8_storage.bogasm", out)
            receipt = run_file(out)

        expected = hashlib.sha256(sine8_bytes(128, 16)).hexdigest()

        self.assertEqual(receipt["bogbin"], "BOGBIN-0.5")
        self.assertEqual(receipt["vm"], "BOGVM-0.5")
        self.assertEqual(receipt["execution_status"], "completed")
        self.assertEqual(receipt["accepted_data_block_names"], ["generated_sine8_128x16"])
        self.assertEqual(receipt["accepted_without_verify"], 0)
        self.assertEqual(receipt["candidate_graph_contamination"], 0)

        verify_events = [e for e in receipt["events"] if e["opcode"] == "VERIFY_HASH"]
        self.assertEqual(verify_events[0]["details"]["result"], "verified")
        self.assertEqual(verify_events[0]["details"]["actual_hash"], expected)

    def test_sine8_u8_bad_hash_blocks_accept_data(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "sine8_u8_bad_hash.bogbin"
            assemble_file("examples/sine8_u8_bad_hash.bogasm", out)
            receipt, exit_code = run_file_with_block_receipt(out)

        self.assertEqual(exit_code, 1)
        self.assertEqual(receipt["bogbin"], "BOGBIN-0.5")
        self.assertEqual(receipt["vm"], "BOGVM-0.5")
        self.assertEqual(receipt["execution_status"], "blocked")
        self.assertIn("ACCEPT_DATA without VERIFY_HASH", receipt["block_reason"])
        self.assertEqual(receipt["accepted_data_block_names"], [])
        self.assertEqual(receipt["accepted_without_verify"], 0)
        self.assertEqual(receipt["candidate_graph_contamination"], 0)

        verify_events = [e for e in receipt["events"] if e["opcode"] == "VERIFY_HASH"]
        self.assertEqual(verify_events[0]["details"]["result"], "rejected")


if __name__ == "__main__":
    unittest.main()
