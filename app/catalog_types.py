"""Shared records that preserve achievement data from individual sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .readers.steam_stats import AchievementDefinition


@dataclass(frozen=True)
class SourceAchievement:
    id: int
    source: str
    source_url: str | None
    retrieved_at: str | None
    values: Mapping[str, object]
    field_provenance: Mapping[str, Mapping[str, object]] = field(
        default_factory=dict
    )


def steam_source_records(
    definitions: Iterable[AchievementDefinition],
) -> dict[int, SourceAchievement]:
    return {
        item.id: SourceAchievement(
            id=item.id,
            source="steam_schema",
            source_url=None,
            retrieved_at=None,
            values={
                "steam_group": item.group,
                "steam_bit": item.bit,
                "steam_name": str(item.id),
                "name_en": item.name,
                "steam_description_en": item.description,
                "icon_url": item.icon,
                "icon_locked_url": item.icon_locked,
            },
        )
        for item in definitions
    }
