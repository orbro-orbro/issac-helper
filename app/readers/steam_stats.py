"""Extract Isaac achievement definitions and unlock bits from Steam KeyValues."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .binary_kv import read_binary_keyvalues


class SteamStatsError(ValueError):
    """Raised when the expected Steam stats structure is unavailable."""


@dataclass(frozen=True)
class AchievementDefinition:
    group: int
    bit: int
    id: int
    name: str
    description: str
    icon: str
    icon_locked: str


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _english(value: object) -> str:
    if isinstance(value, str):
        return value
    mapping = _mapping(value)
    result = mapping.get("english", "")
    return result if isinstance(result, str) else ""


def extract_schema(
    root: Mapping[str, object], app_id: str = "250900"
) -> list[AchievementDefinition]:
    """Return numeric achievement definitions from a parsed Steam schema."""

    stats = _mapping(_mapping(root.get(app_id)).get("stats"))
    definitions: list[AchievementDefinition] = []
    for group_name, group_value in stats.items():
        if not str(group_name).isdigit():
            continue
        bits = _mapping(_mapping(group_value).get("bits"))
        for bit_name, bit_value in bits.items():
            if not str(bit_name).isdigit():
                continue
            item = _mapping(bit_value)
            raw_id = item.get("name")
            if not str(raw_id).isdigit():
                continue
            display = _mapping(item.get("display"))
            definitions.append(
                AchievementDefinition(
                    group=int(group_name),
                    bit=int(bit_name),
                    id=int(str(raw_id)),
                    name=_english(display.get("name")) or f"Achievement {raw_id}",
                    description=_english(display.get("desc")),
                    icon=str(display.get("icon", "")),
                    icon_locked=str(display.get("icon_gray", "")),
                )
            )
    if not definitions:
        raise SteamStatsError(f"no achievement definitions found for AppID {app_id}")
    definitions.sort(key=lambda item: (item.group, item.bit, item.id))
    ids = [item.id for item in definitions]
    if len(ids) != len(set(ids)):
        raise SteamStatsError("schema contains duplicate numeric achievement IDs")
    return definitions


def extract_unlocked(
    root: Mapping[str, object],
    definitions: Sequence[AchievementDefinition],
) -> dict[int, datetime | None]:
    """Map set cache bits to numeric achievement IDs and optional UTC times."""

    cache = _mapping(root.get("cache"))
    by_position = {(item.group, item.bit): item.id for item in definitions}
    unlocked: dict[int, datetime | None] = {}
    for group_name, group_value in cache.items():
        if not str(group_name).isdigit():
            continue
        group = int(str(group_name))
        values = _mapping(group_value)
        raw_mask = values.get("data", 0)
        if not isinstance(raw_mask, int):
            continue
        mask = raw_mask & 0xFFFFFFFF
        times = _mapping(values.get("AchievementTimes"))
        for bit in range(32):
            if not mask & (1 << bit):
                continue
            achievement_id = by_position.get((group, bit))
            if achievement_id is None:
                continue
            raw_time = times.get(str(bit))
            timestamp = None
            if isinstance(raw_time, int) and raw_time > 0:
                timestamp = datetime.fromtimestamp(raw_time, tz=timezone.utc)
            unlocked[achievement_id] = timestamp
    return unlocked


def read_schema(path: Path) -> list[AchievementDefinition]:
    return extract_schema(read_binary_keyvalues(Path(path)))


def read_unlocked(
    path: Path, definitions: Sequence[AchievementDefinition]
) -> dict[int, datetime | None]:
    return extract_unlocked(read_binary_keyvalues(Path(path)), definitions)
