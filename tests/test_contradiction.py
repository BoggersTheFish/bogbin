import tempfile
from pathlib import Path
import unittest

from bogvm.assembler import assemble_file
from bogvm.vm import run_file, VMError


class BOGVMContradictionTests(unittest.TestCase):
    def test_contradiction_blocks_accept(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "contradiction.bogbin"
            assemble_file("examples/contradiction.bogasm", out)

            with self.assertRaises(VMError):
                run_file(out)


if __name__ == "__main__":
    unittest.main()
