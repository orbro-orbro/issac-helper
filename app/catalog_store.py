"""Validate, load, and atomically publish achievement catalogs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Mapping

from .catalog import CATEGORY_DEFINITIONS, CHARACTERS


class CatalogValidationError(ValueError):
    """Raised when a catalog cannot safely be published."""


class CatalogLoadError(ValueError):
    """Raised when a catalog file does not contain the supported schema."""


@dataclass(frozen=True)
class CatalogValidation:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    completeness: Mapping[str, int]


_REQUIRED_FIELDS = (
    "steam.name",
    "display.name_en",
    "display.name_zh",
    "display.unlock_condition_en",
    "display.unlock_condition_zh",
    "reward.name_zh",
    "dlc",
    "icon.path",
)
_SECRET_STATUSES = {"verified", "unverified", "conflict", "not_applicable"}
_PROVENANCE_SOURCES = {"steam_schema", "wiki_gg", "huiji", "translated_wiki_gg"}
_CHARACTER_IDS = {str(item["id"]) for item in CHARACTERS}


def nested_value(record: Mapping[str, object], dotted: str) -> object | None:
    """Return a nested value, or ``None`` when any part is unavailable."""

    current: object = record
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _missing_fields(record: Mapping[str, object]) -> set[str]:
    missing = record.get("missing", [])
    if not isinstance(missing, list):
        return set()
    return {
        field
        for item in missing
        if isinstance(item, Mapping)
        and isinstance((field := item.get("field")), str)
    }


def _as_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def validate_catalog(
    payload: Mapping[str, object],
    *,
    expected_count: int = 641,
    assets_root: Path | None = None,
) -> CatalogValidation:
    """Aggregate structural catalog errors without changing any on-disk file."""

    errors: list[str] = []
    warnings: list[str] = []
    completeness = {field: 0 for field in _REQUIRED_FIELDS}
    if not isinstance(payload, Mapping):
        return CatalogValidation(False, ("catalog payload must be an object",), (), completeness)

    achievements = payload.get("achievements", [])
    if not isinstance(achievements, list):
        return CatalogValidation(False, ("achievements must be a list",), (), completeness)
    if len(achievements) != expected_count:
        errors.append(f"expected {expected_count} achievements, found {len(achievements)}")
    if payload.get("achievement_count") != len(achievements):
        errors.append("achievement_count does not match achievements")

    ids: set[int] = set()
    steam_keys: set[tuple[int, int]] = set()
    for index, candidate in enumerate(achievements):
        if not isinstance(candidate, Mapping):
            errors.append(f"achievement {index}: record must be an object")
            continue
        record = candidate
        achievement_id = _as_int(record.get("id"))
        label = str(record.get("id"))
        if achievement_id is None:
            errors.append(f"achievement {label}: id must be numeric")
        elif achievement_id in ids:
            errors.append(f"duplicate achievement id {achievement_id}")
        else:
            ids.add(achievement_id)

        steam = record.get("steam", {})
        if not isinstance(steam, Mapping):
            errors.append(f"achievement {label}: steam must be an object")
            steam = {}
        group = _as_int(steam.get("group"))
        bit = _as_int(steam.get("bit"))
        if group is None or bit is None:
            errors.append(f"achievement {label}: Steam coordinate must be numeric")
        else:
            steam_key = (group, bit)
            if steam_key in steam_keys:
                errors.append(f"duplicate Steam coordinate {steam_key}")
            else:
                steam_keys.add(steam_key)

        missing = _missing_fields(record)
        for field in _REQUIRED_FIELDS:
            if nested_value(record, field) not in (None, ""):
                completeness[field] += 1
            elif field not in missing:
                errors.append(f"achievement {label}: {field} lacks value or missing reason")

        relations = record.get("characters", [])
        if not isinstance(relations, list):
            errors.append(f"achievement {label}: characters must be a list")
        else:
            for relation in relations:
                relation_id = relation.get("id") if isinstance(relation, Mapping) else None
                if relation_id not in _CHARACTER_IDS:
                    errors.append(f"achievement {label}: unknown character {relation_id}")

        categories = record.get("categories", [])
        if not isinstance(categories, list):
            errors.append(f"achievement {label}: categories must be a list")
        else:
            for category in categories:
                if category not in CATEGORY_DEFINITIONS:
                    errors.append(f"achievement {label}: unknown category {category}")

        secret = record.get("secret", {})
        secret_status = secret.get("status") if isinstance(secret, Mapping) else None
        if secret_status not in _SECRET_STATUSES:
            errors.append(f"achievement {label}: invalid Secret mapping status")
        elif secret_status == "conflict":
            errors.append(f"achievement {label}: conflicting Secret identity")
        elif secret_status == "unverified":
            warnings.append(f"achievement {label}: unverified Secret mapping")

        icon = record.get("icon", {})
        icon_path_value = nested_value(record, "icon.path")
        if icon_path_value not in (None, ""):
            icon_path = Path(str(icon_path_value))
            if icon_path.is_absolute() or ".." in icon_path.parts:
                errors.append(f"achievement {label}: unsafe icon path")
            elif assets_root is not None and not (assets_root / icon_path).is_file():
                errors.append(f"achievement {label}: missing icon {icon_path}")
        if isinstance(icon, Mapping) and icon.get("fallback"):
            warnings.append(f"achievement {label}: fallback icon")

        sources = record.get("sources", {})
        if not isinstance(sources, Mapping):
            errors.append(f"achievement {label}: sources must be an object")
        else:
            for field, entries in sources.items():
                if not isinstance(entries, list):
                    errors.append(f"achievement {label}: sources for {field} must be a list")
                    continue
                for entry in entries:
                    if not isinstance(entry, Mapping):
                        errors.append(f"achievement {label}: source for {field} must be an object")
                        continue
                    if entry.get("source") not in _PROVENANCE_SOURCES:
                        errors.append(f"achievement {label}: unknown source for {field}")
                    if not (entry.get("url") or entry.get("source_url") or entry.get("origin")):
                        errors.append(f"achievement {label}: source for {field} lacks URL or local origin")

    return CatalogValidation(not errors, tuple(errors), tuple(warnings), completeness)


def load_catalog(path: Path) -> dict[str, object]:
    """Load a version-two catalog object from JSON."""

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogLoadError(f"unable to load catalog: {error}") from error
    if not isinstance(payload, dict):
        raise CatalogLoadError("catalog JSON must be an object")
    if payload.get("schema_version") != 2:
        raise CatalogLoadError("unsupported catalog schema version")
    return payload


def publish_catalog(
    payload: Mapping[str, object],
    path: Path,
    *,
    expected_count: int = 641,
    assets_root: Path | None = None,
) -> CatalogValidation:
    """Validate and atomically replace ``path`` with a UTF-8 catalog file."""

    result = validate_catalog(payload, expected_count=expected_count, assets_root=assets_root)
    if not result.valid:
        raise CatalogValidationError("; ".join(result.errors))

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        temporary.replace(path)
        temporary = None
        return result
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
