import tempfile
from pathlib import Path
import unittest

from bogvm.assembler import assemble_file
from bogvm.vm import run_file


class BOGVMContradictionTests(unittest.TestCase):
    def test_contradiction_repairs_accept_attempt(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "contradiction.bogbin"
            assemble_file("examples/contradiction.bogasm", out)
            receipt = run_file(out)

        self.assertEqual(receipt["execution_status"], "completed")
        self.assertEqual(receipt["accepted_claim_names"], [])
        self.assertEqual(receipt["rejected_claim_names"], ["claim_A_C"])
        self.assertEqual(receipt["quarantined_claim_names"], ["claim_A_C"])

        repair_events = [event for event in receipt["events"] if event["opcode"] == "REPAIR_CONTRADICTION"]
        self.assertEqual(len(repair_events), 1)
        self.assertEqual(repair_events[0]["details"]["repair_actions"], ["reject_claim", "quarantine_claim"])


if __name__ == "__main__":
    unittest.main()
