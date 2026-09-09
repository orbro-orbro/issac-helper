import unittest

from app.readers.isaac_save import IsaacSaveError, parse_secrets


def save_bytes(flags: bytes, count: int | None = None) -> bytes:
    data = bytearray(32 + len(flags))
    data[:14] = b"ISAACNGSAVE09R"
    data[24:28] = (len(flags) if count is None else count).to_bytes(4, "little")
    data[32:] = flags
    return bytes(data)


class IsaacSaveTests(unittest.TestCase):
    def test_reads_only_nonzero_secret_flags(self):
        result = parse_secrets(save_bytes(bytes([1, 0, 2, 0])))

        self.assertEqual(result.format_name, "ISAACNGSAVE09R")
        self.assertEqual(result.secret_count, 4)
        self.assertEqual(result.unlocked_ids, frozenset({1, 3}))

    def test_rejects_unknown_header(self):
        with self.assertRaisesRegex(IsaacSaveError, "unsupported save format"):
            parse_secrets(bytes(40))

    def test_rejects_truncated_header(self):
        with self.assertRaisesRegex(IsaacSaveError, "truncated"):
            parse_secrets(b"ISAACNGSAVE09R")

    def test_rejects_truncated_secret_table(self):
        with self.assertRaisesRegex(IsaacSaveError, "truncated secret table"):
            parse_secrets(save_bytes(b"\x01\x00", count=4))


if __name__ == "__main__":
    unittest.main()
