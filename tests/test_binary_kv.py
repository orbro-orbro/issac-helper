import struct
import unittest

from app.readers.binary_kv import BinaryKVError, parse_binary_keyvalues


def cstring(value: str) -> bytes:
    return value.encode("utf-8") + b"\0"


def entry(kind: int, name: str, value: bytes) -> bytes:
    return bytes([kind]) + cstring(name) + value


def obj(name: str, body: bytes) -> bytes:
    return entry(0, name, body + b"\x08")


class BinaryKeyValuesTests(unittest.TestCase):
    def test_parses_supported_scalar_types_and_nested_objects(self):
        wide = "魂".encode("utf-16-le") + b"\0\0"
        payload = obj(
            "root",
            entry(1, "name", cstring("Isaac"))
            + entry(2, "data", struct.pack("<i", -1))
            + entry(3, "ratio", struct.pack("<f", 1.5))
            + entry(5, "wide", struct.pack("<H", 2) + wide)
            + entry(6, "color", bytes([1, 2, 3, 4]))
            + entry(7, "time", struct.pack("<Q", 7))
            + entry(10, "signed", struct.pack("<q", -9))
            + obj("child", entry(1, "value", cstring("ok"))),
        )

        result = parse_binary_keyvalues(payload)

        self.assertEqual(result["root"]["name"], "Isaac")
        self.assertEqual(result["root"]["data"], -1)
        self.assertAlmostEqual(result["root"]["ratio"], 1.5)
        self.assertEqual(result["root"]["wide"], "魂")
        self.assertEqual(result["root"]["color"], (1, 2, 3, 4))
        self.assertEqual(result["root"]["time"], 7)
        self.assertEqual(result["root"]["signed"], -9)
        self.assertEqual(result["root"]["child"], {"value": "ok"})

    def test_rejects_unterminated_key_name(self):
        with self.assertRaisesRegex(BinaryKVError, "unterminated"):
            parse_binary_keyvalues(b"\x01root")

    def test_rejects_unknown_type(self):
        with self.assertRaisesRegex(BinaryKVError, "unsupported type 9"):
            parse_binary_keyvalues(b"\x09bad\0")

    def test_rejects_truncated_scalar(self):
        with self.assertRaisesRegex(BinaryKVError, "truncated"):
            parse_binary_keyvalues(entry(7, "time", b"\x01"))


if __name__ == "__main__":
    unittest.main()
