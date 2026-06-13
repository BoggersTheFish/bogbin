import hashlib
import unittest

from scripts.pack_v32_bogapp import HEADER_SIZE, MAGIC, pack_app


class V32BogAppContractTests(unittest.TestCase):
    def test_packer_emits_canonical_header_and_hashes(self):
        code = b"\x90\xcd\x80"
        container = pack_app(code, "audit_app", "1.2.3")

        self.assertEqual(len(container), HEADER_SIZE + len(code))
        self.assertEqual(container[:8], MAGIC)
        self.assertEqual(int.from_bytes(container[8:12], "big"), 1)
        self.assertEqual(int.from_bytes(container[12:16], "big"), HEADER_SIZE)
        self.assertEqual(int.from_bytes(container[16:20], "big"), 0)
        self.assertEqual(int.from_bytes(container[20:24], "big"), HEADER_SIZE)
        self.assertEqual(int.from_bytes(container[24:28], "big"), len(code))
        self.assertEqual(int.from_bytes(container[28:32], "big"), 0)
        self.assertEqual(container[72:104], hashlib.sha256(code).digest())
        self.assertEqual(container[104:136], hashlib.sha256(container[:104]).digest())
        self.assertEqual(container[136:], code)

    def test_text_fields_require_room_for_canonical_nul_padding(self):
        with self.assertRaises(ValueError):
            pack_app(b"\x90", "x" * 24, "1.0.0")
        with self.assertRaises(ValueError):
            pack_app(b"\x90", "app", "x" * 16)

    def test_text_fields_are_ascii_only(self):
        with self.assertRaises(UnicodeEncodeError):
            pack_app(b"\x90", "app-\N{SNOWMAN}", "1.0.0")


if __name__ == "__main__":
    unittest.main()
