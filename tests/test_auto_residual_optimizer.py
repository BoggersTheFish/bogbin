import hashlib
import unittest

from bogvm.bases import synthesize_basis
from bogvm.optimizer import optimize_chunked_residual_plan, optimize_residual_plan


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

    def test_ramp_like_input_chooses_delta_u8_with_zero_residuals(self):
        data = bytes((10 + i) % 256 for i in range(32))
        plan = optimize_residual_plan(data)

        self.assertEqual(plan["basis"], "delta_u8")
        self.assertEqual(plan["start_byte"], 10)
        self.assertEqual(plan["delta"], 1)
        self.assertEqual(plan["residual_count"], 0)
        self.assertEqual(plan["residuals"], [])
        self.assertEqual(plan["reconstructed_hash"], hashlib.sha256(data).hexdigest())

    def test_mixed_input_produces_residuals_and_reconstructs_exact_sha256(self):
        data = bytes([10, 11, 99, 13, 14, 77, 16, 17])
        plan = optimize_residual_plan(data)

        self.assertEqual(plan["basis"], "delta_u8")
        self.assertEqual(plan["start_byte"], 10)
        self.assertEqual(plan["delta"], 1)
        self.assertEqual(plan["residual_count"], 2)
        self.assertEqual(
            plan["residuals"],
            [{"offset": 2, "byte": 99}, {"offset": 5, "byte": 77}],
        )
        self.assertEqual(plan["reconstructed_hash"], hashlib.sha256(data).hexdigest())

    def test_tie_breaking_is_deterministic(self):
        data = b""
        plan = optimize_residual_plan(data)

        self.assertEqual(plan["basis"], "zero_block")
        self.assertEqual(plan["start_byte"], 0)
        self.assertEqual(plan["residual_count"], 0)
        self.assertEqual(plan["reconstructed_hash"], hashlib.sha256(data).hexdigest())

    def test_shared_basis_generation_is_deterministic(self):
        self.assertEqual(synthesize_basis("zero_block", 99, 4), bytes([0, 0, 0, 0]))
        self.assertEqual(synthesize_basis("delta_u8", 10, 4, delta=3), bytes([10, 13, 16, 19]))
        self.assertEqual(synthesize_basis("repeat_byte", 7, 4), bytes([7, 7, 7, 7]))
        self.assertEqual(synthesize_basis("ramp_u8", 254, 4), bytes([254, 255, 0, 1]))
        self.assertEqual(synthesize_basis("triangle_u8", 0, 4), bytes([0, 32, 64, 96]))
        self.assertEqual(synthesize_basis("sine8_u8", 0, 4), bytes([0, 90, 127, 90]))

    def test_zero_block_input_chooses_zero_block(self):
        data = bytes([0]) * 16
        plan = optimize_residual_plan(data)

        self.assertEqual(plan["basis"], "zero_block")
        self.assertEqual(plan["start_byte"], 0)
        self.assertEqual(plan["delta"], 0)
        self.assertEqual(plan["residual_count"], 0)

    def test_optimizer_selects_delta_u8_for_arithmetic_byte_patterns(self):
        data = bytes((12 + (i * 7)) % 256 for i in range(32))
        plan = optimize_residual_plan(data)

        self.assertEqual(plan["basis"], "delta_u8")
        self.assertEqual(plan["start_byte"], 12)
        self.assertEqual(plan["delta"], 7)
        self.assertEqual(plan["residual_count"], 0)

    def test_chunk_splitting_is_deterministic_and_hash_is_stable(self):
        data = bytes([7]) * 4 + bytes((20 + i) % 256 for i in range(4)) + bytes([1, 2, 99, 4])
        plan = optimize_chunked_residual_plan(data, chunk_size=4)

        self.assertEqual(plan["chunk_size"], 4)
        self.assertEqual(plan["chunk_count"], 3)
        self.assertEqual([chunk["offset"] for chunk in plan["chunks"]], [0, 4, 8])
        self.assertEqual([chunk["length"] for chunk in plan["chunks"]], [4, 4, 4])
        self.assertEqual(plan["whole_sha256"], hashlib.sha256(data).hexdigest())

    def test_each_chunk_chooses_its_own_best_basis(self):
        data = bytes([7]) * 4 + bytes((20 + i) % 256 for i in range(4))
        plan = optimize_chunked_residual_plan(data, chunk_size=4)

        self.assertEqual(plan["chunks"][0]["basis"], "repeat_byte")
        self.assertEqual(plan["chunks"][0]["start_byte"], 7)
        self.assertEqual(plan["chunks"][0]["residual_count"], 0)
        self.assertEqual(plan["chunks"][1]["basis"], "delta_u8")
        self.assertEqual(plan["chunks"][1]["start_byte"], 20)
        self.assertEqual(plan["chunks"][1]["delta"], 1)
        self.assertEqual(plan["chunks"][1]["residual_count"], 0)


if __name__ == "__main__":
    unittest.main()
