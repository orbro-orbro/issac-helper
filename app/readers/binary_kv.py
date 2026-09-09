"""Reader for Valve's binary KeyValues representation used by Steam stats."""

from __future__ import annotations

from pathlib import Path
import struct
from typing import Any


class BinaryKVError(ValueError):
    """Raised when a binary KeyValues document is malformed or unsupported."""


class _Reader:
    def __init__(self, data: bytes):
        self.data = memoryview(data)
        self.offset = 0

    def take(self, size: int, label: str) -> bytes:
        end = self.offset + size
        if end > len(self.data):
            raise BinaryKVError(
                f"truncated {label} at byte {self.offset}: need {size} bytes"
            )
        value = self.data[self.offset:end].tobytes()
        self.offset = end
        return value

    def unpack(self, fmt: str, label: str) -> Any:
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.take(size, label))[0]

    def cstring(self, label: str) -> str:
        start = self.offset
        while self.offset < len(self.data) and self.data[self.offset] != 0:
            self.offset += 1
        if self.offset >= len(self.data):
            raise BinaryKVError(f"unterminated {label} at byte {start}")
        raw = self.data[start:self.offset].tobytes()
        self.offset += 1
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BinaryKVError(f"invalid UTF-8 {label} at byte {start}") from exc

    def object(self, *, nested: bool) -> dict[str, object]:
        result: dict[str, object] = {}
        while self.offset < len(self.data):
            value_type = self.take(1, "value type")[0]
            if value_type == 8:
                return result
            name = self.cstring("key name")
            result[name] = self.value(value_type)
        if nested:
            raise BinaryKVError("truncated object: missing end marker")
        return result

    def value(self, value_type: int) -> object:
        if value_type == 0:
            return self.object(nested=True)
        if value_type == 1:
            return self.cstring("string value")
        if value_type == 2:
            return self.unpack("<i", "int32 value")
        if value_type == 3:
            return self.unpack("<f", "float value")
        if value_type == 5:
            count = self.unpack("<H", "UTF-16 character count")
            raw = self.take(count * 2, "UTF-16 value")
            try:
                return raw.decode("utf-16-le").rstrip("\0")
            except UnicodeDecodeError as exc:
                raise BinaryKVError("invalid UTF-16 value") from exc
        if value_type == 6:
            return tuple(self.take(4, "color value"))
        if value_type == 7:
            return self.unpack("<Q", "uint64 value")
        if value_type == 10:
            return self.unpack("<q", "int64 value")
        raise BinaryKVError(f"unsupported type {value_type} at byte {self.offset - 1}")


def parse_binary_keyvalues(data: bytes) -> dict[str, object]:
    """Parse a complete binary KeyValues document into nested dictionaries."""

    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    return _Reader(data).object(nested=False)


def read_binary_keyvalues(path: Path) -> dict[str, object]:
    """Read and parse a binary KeyValues file without modifying it."""

    return parse_binary_keyvalues(Path(path).read_bytes())
