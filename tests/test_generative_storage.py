import hashlib
import tempfile
from pathlib import Path
import unittest

from bogvm.assembler import assemble_file
from bogvm.vm import run_file


class BOGVMGenerativeStorageTests(unittest.TestCase):
    def test_repeat_byte_storage_accepts_after_hash_verify(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "repeat_byte_storage.bogbin"
            assemble_file("examples/repeat_byte_storage.bogasm", out)
            receipt = run_file(out)

        self.assertEqual(receipt["accepted_data_block_names"], ["generated_42x16"])
        self.assertEqual(receipt["accepted_without_verify"], 0)
        self.assertEqual(receipt["candidate_graph_contamination"], 0)

        events = receipt["events"]
        verify_events = [e for e in events if e["opcode"] == "VERIFY_HASH"]
        self.assertEqual(verify_events[0]["details"]["result"], "verified")
        self.assertEqual(
            verify_events[0]["details"]["actual_hash"],
            hashlib.sha256(bytes([42]) * 16).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
