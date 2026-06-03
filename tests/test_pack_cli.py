import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from bogvm.assembler import Assembler
from bogvm.packer import pack_bytes_to_bogasm
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
            self.assertEqual(receipt["accepted_without_verify"], 0)

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


if __name__ == "__main__":
    unittest.main()
