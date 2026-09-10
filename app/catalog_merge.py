"""Merge independently sourced achievement metadata into runtime records."""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from .catalog import classify_achievement, extract_character_relations
from .catalog_types import SourceAchievement


def _has_value(value: object) -> bool:
    return value is not None and value != ""


FieldCandidate = (
    tuple[SourceAchievement, object]
    | tuple[SourceAchievement, object, str]
)


def _source_entry(
    item: SourceAchievement,
    value: object,
    source_field: str | None = None,
) -> dict[str, object]:
    field_provenance = (
        item.field_provenance.get(source_field, {})
        if source_field is not None
        else {}
    )
    source_url = field_provenance.get("source_url", item.source_url)
    retrieved_at = field_provenance.get("retrieved_at", item.retrieved_at)
    entry: dict[str, object] = {
        "source": item.source,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "value": value,
    }
    origin = field_provenance.get("origin")
    if origin:
        entry["origin"] = origin
    elif item.source == "steam_schema" and not source_url:
        entry["origin"] = "local_steam_schema"
    return entry


def choose_field(
    field: str,
    candidates: Sequence[FieldCandidate],
) -> tuple[object | None, list[dict[str, object]], list[dict[str, object]]]:
    """Return selected value, provenance entries, and conflicting alternatives."""

    normalized = [
        (candidate[0], candidate[1], candidate[2] if len(candidate) == 3 else None)
        for candidate in candidates
    ]
    present = [
        (item, value, source_field)
        for item, value, source_field in normalized
        if _has_value(value)
    ]
    if not present:
        return None, [], []
    selected = present[0][1]
    provenance = [
        _source_entry(item, value, source_field)
        for item, value, source_field in present
        if value == selected
    ]
    conflicts = [
        {"field": field, **_source_entry(item, value, source_field)}
        for item, value, source_field in present
        if value != selected
    ]
    return selected, provenance, conflicts


def _candidate(
    item: SourceAchievement | None,
    key: str,
) -> list[FieldCandidate]:
    if item is None:
        return []
    return [(item, item.values.get(key), key)]


def _secret_mapping(
    achievement_id: int,
    steam: SourceAchievement | None,
    wiki: SourceAchievement | None,
    huiji: SourceAchievement | None,
    secret_count: int,
) -> dict[str, object]:
    records = [item for item in (steam, wiki, huiji) if item is not None]
    evidence = [item.source for item in records]
    steam_id: int | None = None
    if steam is not None:
        raw_name = steam.values.get("steam_name")
        if isinstance(raw_name, str) and raw_name.isdigit():
            steam_id = int(raw_name)
        elif isinstance(raw_name, int) and not isinstance(raw_name, bool):
            steam_id = raw_name

    numeric_ids = ([steam_id] if steam_id is not None else []) + [
        item.id for item in (wiki, huiji) if item is not None
    ]
    all_sources = steam is not None and wiki is not None and huiji is not None
    agree = all_sources and numeric_ids == [achievement_id, achievement_id, achievement_id]
    if agree and 1 <= achievement_id <= secret_count:
        status = "verified"
    elif len(set(numeric_ids)) > 1 or any(item.id != achievement_id for item in records):
        status = "conflict"
    else:
        status = "unverified"
    return {"id": achievement_id, "status": status, "evidence": evidence}


def merge_catalog(
    steam: Mapping[int, SourceAchievement],
    wiki: Mapping[int, SourceAchievement],
    huiji: Mapping[int, SourceAchievement],
    *,
    generated_at: str,
    secret_count: int = 641,
) -> dict[str, object]:
    """Merge source records by numeric ID using explicit field precedence."""

    achievements: list[dict[str, object]] = []
    canonical_ids = set(steam)
    external_only_ids = {
        "wiki_gg": sorted(set(wiki) - canonical_ids),
        "huiji": sorted(set(huiji) - canonical_ids),
    }
    for achievement_id in sorted(steam):
        steam_item = steam.get(achievement_id)
        wiki_item = wiki.get(achievement_id)
        huiji_item = huiji.get(achievement_id)
        sources: dict[str, list[dict[str, object]]] = {}
        conflicts: list[dict[str, object]] = []
        missing: list[dict[str, str]] = []

        def select(
            field: str,
            candidates: Sequence[FieldCandidate],
        ) -> object | None:
            value, provenance, alternatives = choose_field(field, candidates)
            if provenance:
                sources[field] = provenance
            else:
                missing.append({"field": field, "reason": "source_missing"})
            conflicts.extend(alternatives)
            return value

        name_en = select(
            "display.name_en",
            _candidate(steam_item, "name_en")
            + _candidate(wiki_item, "name_en")
            + _candidate(huiji_item, "name_en"),
        )
        name_zh = select("display.name_zh", _candidate(huiji_item, "name_zh"))
        description_en = select(
            "display.description_en",
            _candidate(steam_item, "steam_description_en")
            + _candidate(wiki_item, "steam_description_en"),
        )
        condition_en = select(
            "display.unlock_condition_en",
            _candidate(wiki_item, "unlock_condition_en"),
        )
        condition_zh = select(
            "display.unlock_condition_zh",
            _candidate(huiji_item, "unlock_condition_zh"),
        )
        reward_en = select("reward.name_en", _candidate(wiki_item, "reward_name_en"))
        reward_zh_candidates = _candidate(huiji_item, "reward_name_zh")
        if not reward_zh_candidates or not _has_value(reward_zh_candidates[0][1]):
            reward_zh_candidates = _candidate(huiji_item, "reward_zh")
        reward_zh = select("reward.name_zh", reward_zh_candidates)
        dlc = select("dlc", _candidate(huiji_item, "dlc"))
        icon_unlocked = select("icon.unlocked", _candidate(steam_item, "icon_url"))
        icon_locked = select("icon.locked", _candidate(steam_item, "icon_locked_url"))

        steam_name = select("steam.name", _candidate(steam_item, "steam_name"))
        steam_group = select("steam.group", _candidate(steam_item, "steam_group"))
        steam_bit = select("steam.bit", _candidate(steam_item, "steam_bit"))

        relations = extract_character_relations(
            str(condition_zh or ""),
            str(condition_en or ""),
            str(name_en or ""),
            str(description_en or ""),
        )
        category_values = {
            "name_en": name_en,
            "name_zh": name_zh,
            "description_en": description_en,
            "unlock_condition_en": condition_en,
            "unlock_condition_zh": condition_zh,
        }
        achievements.append({
            "id": achievement_id,
            "steam": {
                "name": steam_name,
                "group": steam_group,
                "bit": steam_bit,
                "description_en": description_en,
            },
            "secret": _secret_mapping(
                achievement_id, steam_item, wiki_item, huiji_item, secret_count
            ),
            "display": {
                "name_en": name_en,
                "name_zh": name_zh,
                "description_en": description_en,
                "unlock_condition_en": condition_en,
                "unlock_condition_zh": condition_zh,
            },
            "reward": {"name_en": reward_en, "name_zh": reward_zh},
            "characters": relations,
            "categories": classify_achievement(category_values, relations),
            "dlc": dlc,
            "icon": {"unlocked": icon_unlocked, "locked": icon_locked},
            "sources": sources,
            "conflicts": conflicts,
            "missing": missing,
        })

    status_counts = Counter(item["secret"]["status"] for item in achievements)
    return {
        "schema_version": 2,
        "generated_at": generated_at,
        "achievement_count": len(achievements),
        "achievements": achievements,
        "diagnostics": {
            "conflict_count": sum(len(item["conflicts"]) for item in achievements),
            "missing_count": sum(len(item["missing"]) for item in achievements),
            "secret_status_counts": dict(sorted(status_counts.items())),
            "external_only_ids": external_only_ids,
        },
    }
