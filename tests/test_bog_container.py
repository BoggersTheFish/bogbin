import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from bogvm.assembler import Assembler
from bogvm.container import (
    ContainerError,
    build_bog_container,
    compile_bog_container_to_bogasm,
    read_bog_container,
    write_bog_container,
)
from bogvm.vm import run_file_with_block_receipt


class BOGContainerTests(unittest.TestCase):
    def test_container_creation_is_deterministic_and_hash_matches_input(self):
        data = bytes([7]) * 4 + bytes((20 + i) % 256 for i in range(4))

        first = build_bog_container(data, chunk_size=4)
        second = build_bog_container(data, chunk_size=4)

        self.assertEqual(first, second)
        self.assertEqual(first["format"], "BOG-0.9")
        self.assertEqual(first["vm_format"], "BOGBIN-0.9")
        self.assertEqual(first["pack_mode"], "chunked")
        self.assertEqual(first["chunk_count"], 2)
        self.assertEqual(first["whole_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(first["chunks"][0]["basis"], "repeat_byte")
        self.assertEqual(first["chunks"][1]["basis"], "ramp_u8")

    def test_bog_write_read_roundtrips_exactly(self):
        data = bytes([1, 2, 99, 4, 8, 8, 8, 8])
        container = build_bog_container(data, chunk_size=4)

        with tempfile.TemporaryDirectory() as td:
            first_path = Path(td) / "first.bog"
            second_path = Path(td) / "second.bog"
            write_bog_container(container, str(first_path))
            read_back = read_bog_container(str(first_path))
            write_bog_container(read_back, str(second_path))

            self.assertEqual(read_back, container)
            self.assertEqual(first_path.read_text(), second_path.read_text())

    def test_compiling_bog_to_bogasm_is_deterministic(self):
        data = bytes([1, 2, 99, 4, 8, 8, 8, 8])
        container = build_bog_container(data, chunk_size=4)

        first = compile_bog_container_to_bogasm(container)
        second = compile_bog_container_to_bogasm(container)

        self.assertEqual(first, second)
        self.assertIn("DATA_BLOCK payload_chunk_0000", first)
        self.assertIn("VERIFY_HASH payload_chunk_0001", first)

    def test_compiled_bogbin_runs_and_verifies_chunks(self):
        data = bytes([7]) * 4 + bytes((20 + i) % 256 for i in range(4))
        container = build_bog_container(data, chunk_size=4)
        bogasm = compile_bog_container_to_bogasm(container)

        with tempfile.TemporaryDirectory() as td:
            bogbin_path = Path(td) / "compiled.bogbin"
            bogbin_path.write_bytes(Assembler().assemble_text(bogasm))
            receipt, exit_code = run_file_with_block_receipt(bogbin_path)

        self.assertEqual(exit_code, 0)
        self.assertEqual(receipt["execution_status"], "completed")
        self.assertEqual(receipt["bogbin"], "BOGBIN-0.9")
        self.assertEqual(receipt["vm"], "BOGVM-0.9")
        self.assertEqual(receipt["accepted_data_block_names"], ["payload_chunk_0000", "payload_chunk_0001"])

    def test_tampered_residual_causes_hash_verification_failure(self):
        data = bytes([1, 2, 99, 4])
        container = build_bog_container(data, chunk_size=4)
        container["chunks"][0]["residuals"][0]["byte"] = 98
        bogasm = compile_bog_container_to_bogasm(container)

        with tempfile.TemporaryDirectory() as td:
            bogbin_path = Path(td) / "tampered.bogbin"
            bogbin_path.write_bytes(Assembler().assemble_text(bogasm))
            receipt, exit_code = run_file_with_block_receipt(bogbin_path)

        self.assertEqual(exit_code, 1)
        self.assertEqual(receipt["execution_status"], "blocked")
        self.assertIn("ACCEPT_DATA without VERIFY_HASH", receipt["block_reason"])
        verify_events = [event for event in receipt["events"] if event["opcode"] == "VERIFY_HASH"]
        self.assertEqual(verify_events[0]["details"]["result"], "rejected")

    def test_missing_required_container_field_is_rejected(self):
        container = build_bog_container(bytes([1, 2, 3, 4]), chunk_size=4)
        del container["whole_sha256"]

        with self.assertRaises(ContainerError):
            compile_bog_container_to_bogasm(container)

    def test_cli_pack_to_bog_and_compile_flow(self):
        data = bytes([7]) * 4 + bytes((20 + i) % 256 for i in range(4))

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "input.bin"
            container_path = root / "payload.bog"
            bogasm_path = root / "payload.bogasm"
            bogbin_path = root / "payload.bogbin"
            pack_receipt_path = root / "pack_receipt.json"
            run_receipt_path = root / "run_receipt.json"
            input_path.write_bytes(data)

            pack_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "bogvm",
                    "pack",
                    str(input_path),
                    str(container_path),
                    "--chunk-size",
                    "4",
                    "--receipt",
                    str(pack_receipt_path),
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(pack_result.returncode, 0, pack_result.stderr + pack_result.stdout)

            compile_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "bogvm",
                    "compile",
                    str(container_path),
                    str(bogbin_path),
                    "--bogasm",
                    str(bogasm_path),
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr + compile_result.stdout)

            run_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "bogvm",
                    "run",
                    str(bogbin_path),
                    "--receipt",
                    str(run_receipt_path),
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stderr + run_result.stdout)

            pack_receipt = json.loads(pack_receipt_path.read_text())
            run_receipt = json.loads(run_receipt_path.read_text())
            self.assertEqual(pack_receipt["format"], "BOG-0.9")
            self.assertEqual(pack_receipt["whole_sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(run_receipt["accepted_data_block_names"], ["payload_chunk_0000", "payload_chunk_0001"])


if __name__ == "__main__":
    unittest.main()
