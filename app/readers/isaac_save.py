"""Read the verified Repentance+ Secret-flag section."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct


HEADER = b"ISAACNGSAVE09R"
COUNT_OFFSET = 24
FLAGS_OFFSET = 32


class IsaacSaveError(ValueError):
    """Raised when an Isaac save cannot be read safely."""


@dataclass(frozen=True)
class SaveSecrets:
    format_name: str
    secret_count: int
    unlocked_ids: frozenset[int]


def parse_secrets(data: bytes) -> SaveSecrets:
    """Parse Secret flags from the observed ISAACNGSAVE09R format."""

    if len(data) < FLAGS_OFFSET:
        raise IsaacSaveError(
            f"truncated save header: expected at least {FLAGS_OFFSET} bytes"
        )
    if not data.startswith(HEADER):
        shown = data[: len(HEADER)].decode("ascii", errors="replace")
        raise IsaacSaveError(f"unsupported save format: {shown!r}")
    secret_count = struct.unpack_from("<I", data, COUNT_OFFSET)[0]
    end = FLAGS_OFFSET + secret_count
    if end > len(data):
        raise IsaacSaveError(
            f"truncated secret table: declared {secret_count} flags, "
            f"only {len(data) - FLAGS_OFFSET} available"
        )
    flags = data[FLAGS_OFFSET:end]
    unlocked = frozenset(index for index, flag in enumerate(flags, start=1) if flag)
    return SaveSecrets(HEADER.decode("ascii"), secret_count, unlocked)


def read_secrets(path: Path) -> SaveSecrets:
    """Read Secret flags from a save file without changing it."""

    return parse_secrets(Path(path).read_bytes())
