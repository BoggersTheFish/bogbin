import hashlib
import unittest

from bogvm.bases import synthesize_basis
from bogvm.optimizer import optimize_residual_plan


class AutoResidualOptimizerTests(unittest.TestCase):
    def test_exact_repeat_byte_input_chooses_repeat_byte_with_zero_residuals(self):
        data = bytes([42]) * 16
        plan = optimize_residual_plan(data)

        self.assertEqual(plan["basis"], "repeat_byte")
        self.assertEqual(plan["start_byte"], 42)
        self.assertEqual(plan["residual_count"], 0)
        self.assertEqual(plan["residuals"], [])
        self.assertEqual(plan["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(plan["reconstructed_hash"], plan["sha256"])

    def test_ramp_like_input_chooses_ramp_u8_with_zero_residuals(self):
        data = bytes((10 + i) % 256 for i in range(32))
        plan = optimize_residual_plan(data)

        self.assertEqual(plan["basis"], "ramp_u8")
        self.assertEqual(plan["start_byte"], 10)
        self.assertEqual(plan["residual_count"], 0)
        self.assertEqual(plan["residuals"], [])
        self.assertEqual(plan["reconstructed_hash"], hashlib.sha256(data).hexdigest())

    def test_mixed_input_produces_residuals_and_reconstructs_exact_sha256(self):
        data = bytes([10, 11, 99, 13, 14, 77, 16, 17])
        plan = optimize_residual_plan(data)

        self.assertEqual(plan["basis"], "ramp_u8")
        self.assertEqual(plan["start_byte"], 10)
        self.assertEqual(plan["residual_count"], 2)
        self.assertEqual(
            plan["residuals"],
            [{"offset": 2, "byte": 99}, {"offset": 5, "byte": 77}],
        )
        self.assertEqual(plan["reconstructed_hash"], hashlib.sha256(data).hexdigest())

    def test_tie_breaking_is_deterministic(self):
        data = b""
        plan = optimize_residual_plan(data)

        self.assertEqual(plan["basis"], "repeat_byte")
        self.assertEqual(plan["start_byte"], 0)
        self.assertEqual(plan["residual_count"], 0)
        self.assertEqual(plan["reconstructed_hash"], hashlib.sha256(data).hexdigest())

    def test_shared_basis_generation_is_deterministic(self):
        self.assertEqual(synthesize_basis("repeat_byte", 7, 4), bytes([7, 7, 7, 7]))
        self.assertEqual(synthesize_basis("ramp_u8", 254, 4), bytes([254, 255, 0, 1]))
        self.assertEqual(synthesize_basis("triangle_u8", 0, 4), bytes([0, 32, 64, 96]))
        self.assertEqual(synthesize_basis("sine8_u8", 0, 4), bytes([0, 90, 127, 90]))


if __name__ == "__main__":
    unittest.main()
