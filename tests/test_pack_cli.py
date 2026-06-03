import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from bogvm.assembler import Assembler
from bogvm.packer import pack_bytes_to_bogasm, pack_chunked_bytes_to_bogasm
from bogvm.vm import run_file_with_block_receipt


class PackCliTests(unittest.TestCase):
    def test_cli_pack_emits_bogasm_bogbin_and_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "input.bin"
            bogasm_path = root / "output.bogasm"
            bogbin_path = root / "output.bogbin"
            receipt_path = root / "receipt.json"
            input_path.write_bytes(bytes((20 + i) % 256 for i in range(12)))

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "bogvm",
                    "pack",
                    str(input_path),
                    str(bogbin_path),
                    "--bogasm",
                    str(bogasm_path),
                    "--receipt",
                    str(receipt_path),
                ],
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue(bogasm_path.exists())
            self.assertTrue(bogbin_path.exists())
            self.assertTrue(receipt_path.exists())

            bogasm = bogasm_path.read_text()
            self.assertIn("VERIFY_HASH payload", bogasm)
            self.assertIn("ACCEPT_DATA payload", bogasm)

            receipt = json.loads(receipt_path.read_text())
            self.assertEqual(receipt["execution_status"], "completed")
            self.assertEqual(receipt["accepted_data_block_names"], ["payload"])
            self.assertEqual(receipt["pack_mode"], "single_block")
            self.assertEqual(receipt["accepted_without_verify"], 0)

    def test_cli_chunk_size_works_and_receipt_includes_chunk_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "input.bin"
            bogasm_path = root / "chunked.bogasm"
            bogbin_path = root / "chunked.bogbin"
            receipt_path = root / "chunked_receipt.json"
            data = bytes([7]) * 4 + bytes((20 + i) % 256 for i in range(4)) + bytes([1, 2, 99, 4])
            input_path.write_bytes(data)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "bogvm",
                    "pack",
                    str(input_path),
                    str(bogbin_path),
                    "--chunk-size",
                    "4",
                    "--bogasm",
                    str(bogasm_path),
                    "--receipt",
                    str(receipt_path),
                ],
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            bogasm = bogasm_path.read_text()
            self.assertIn("DATA_BLOCK payload_chunk_0000", bogasm)
            self.assertIn("DATA_BLOCK payload_chunk_0001", bogasm)
            self.assertIn("DATA_BLOCK payload_chunk_0002", bogasm)

            receipt = json.loads(receipt_path.read_text())
            self.assertEqual(receipt["execution_status"], "completed")
            self.assertEqual(receipt["pack_mode"], "chunked")
            self.assertEqual(receipt["chunk_size"], 4)
            self.assertEqual(receipt["chunk_count"], 3)
            self.assertEqual(receipt["whole_sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(receipt["total_residual_count"], 1)
            self.assertEqual(
                receipt["accepted_data_block_names"],
                ["payload_chunk_0000", "payload_chunk_0001", "payload_chunk_0002"],
            )

    def test_single_block_preserves_v07_payload_block_behavior(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "input.bin"
            bogasm_path = root / "single.bogasm"
            bogbin_path = root / "single.bogbin"
            receipt_path = root / "single_receipt.json"
            input_path.write_bytes(bytes((20 + i) % 256 for i in range(12)))

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "bogvm",
                    "pack",
                    str(input_path),
                    str(bogbin_path),
                    "--chunk-size",
                    "4",
                    "--single-block",
                    "--bogasm",
                    str(bogasm_path),
                    "--receipt",
                    str(receipt_path),
                ],
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            bogasm = bogasm_path.read_text()
            self.assertIn("DATA_BLOCK payload\n", bogasm)
            self.assertNotIn("payload_chunk_0000", bogasm)

            receipt = json.loads(receipt_path.read_text())
            self.assertEqual(receipt["pack_mode"], "single_block")
            self.assertEqual(receipt["chunk_count"], 1)
            self.assertEqual(receipt["accepted_data_block_names"], ["payload"])

    def test_bad_tampered_generated_hash_path_remains_blocked(self):
        data = bytes((10 + i) % 256 for i in range(8))
        good_hash = hashlib.sha256(data).hexdigest()
        bad_hash = "0" * 64 if good_hash != "0" * 64 else "1" * 64
        bogasm = pack_bytes_to_bogasm(data).replace(good_hash, bad_hash)

        with tempfile.TemporaryDirectory() as td:
            bogbin_path = Path(td) / "tampered.bogbin"
            bogbin_path.write_bytes(Assembler().assemble_text(bogasm))
            receipt, exit_code = run_file_with_block_receipt(bogbin_path)

        self.assertEqual(exit_code, 1)
        self.assertEqual(receipt["execution_status"], "blocked")
        self.assertIn("ACCEPT_DATA without VERIFY_HASH", receipt["block_reason"])
        self.assertEqual(receipt["accepted_data_block_names"], [])
        verify_events = [e for e in receipt["events"] if e["opcode"] == "VERIFY_HASH"]
        self.assertEqual(verify_events[0]["details"]["result"], "rejected")

    def test_tampered_chunk_hash_blocks_acceptance(self):
        data = bytes([7]) * 4 + bytes((20 + i) % 256 for i in range(4))
        good_hash = hashlib.sha256(data[:4]).hexdigest()
        bad_hash = "0" * 64 if good_hash != "0" * 64 else "1" * 64
        bogasm = pack_chunked_bytes_to_bogasm(data, chunk_size=4).replace(good_hash, bad_hash, 1)

        with tempfile.TemporaryDirectory() as td:
            bogbin_path = Path(td) / "tampered_chunk.bogbin"
            bogbin_path.write_bytes(Assembler().assemble_text(bogasm))
            receipt, exit_code = run_file_with_block_receipt(bogbin_path)

        self.assertEqual(exit_code, 1)
        self.assertEqual(receipt["execution_status"], "blocked")
        self.assertIn("ACCEPT_DATA without VERIFY_HASH", receipt["block_reason"])
        self.assertEqual(receipt["accepted_data_block_names"], [])
        verify_events = [e for e in receipt["events"] if e["opcode"] == "VERIFY_HASH"]
        self.assertEqual(verify_events[0]["details"]["result"], "rejected")


if __name__ == "__main__":
    unittest.main()
