"""Safely refresh the merged achievement catalog and its local icon cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Callable, Mapping
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .catalog_merge import merge_catalog
from .catalog_store import load_catalog, nested_value, publish_catalog
from .catalog_types import SourceAchievement, steam_source_records
from .huiji_catalog import fetch_huiji_achievements
from .readers.steam_stats import AchievementDefinition, read_schema
from .wiki_catalog import fetch_wiki_achievements


USER_AGENT = "IsaacHelper/0.1 catalog maintenance"
MAX_ICON_BYTES = 2 * 1024 * 1024
FALLBACK_ICON_PATH = "assets/achievements/fallback.svg"
STEAM_ICON_BASE_URL = (
    "https://shared.fastly.steamstatic.com/community_assets/images/apps/250900"
)
_ICON_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
_STEAM_ICON_FILENAME = re.compile(r"[0-9a-f]{40}\.(?:jpeg|jpg|png)", re.IGNORECASE)
# The live catalog currently has wiki identity and English mechanics for all 641
# Steam IDs. Requiring 95% still permits a small wiki lag after a game release,
# while refusing layout/parser failures that would erase a material data slice.
MIN_WIKI_COVERAGE_PERCENT = 95
_HUIJI_FIELDS = {
    "display.name_en": "name_en",
    "display.name_zh": "name_zh",
    "display.unlock_condition_zh": "unlock_condition_zh",
    "reward.name_zh": "reward_name_zh",
    "dlc": "dlc",
}


class _HttpsOnlyRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        if urlsplit(new_url).scheme != "https":
            raise HTTPError(
                request.full_url,
                code,
                f"refusing redirect to non-HTTPS URL: {new_url}",
                headers,
                fp,
            )
        return super().redirect_request(
            request, fp, code, message, headers, new_url
        )


@dataclass(frozen=True)
class CatalogUpdateResult:
    ok: bool
    updated_at: str | None
    achievement_count: int
    completeness: Mapping[str, int]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


def _validate_wiki_source_integrity(
    steam: Mapping[int, SourceAchievement],
    wiki: object,
) -> None:
    """Reject wiki output that cannot safely supply identity and mechanics."""

    if not isinstance(wiki, Mapping):
        raise ValueError("wiki.gg source integrity: result must be an ID mapping")

    for key, record in wiki.items():
        if (
            not isinstance(key, int)
            or isinstance(key, bool)
            or not isinstance(record, SourceAchievement)
            or record.id != key
            or record.source != "wiki_gg"
        ):
            raise ValueError(
                "wiki.gg source integrity: row identity/source disagrees with its ID key"
            )

    expected_ids = set(steam)
    if not expected_ids:
        return
    minimum = (
        len(expected_ids) * MIN_WIKI_COVERAGE_PERCENT + 99
    ) // 100
    covered_ids = expected_ids.intersection(wiki)
    if len(covered_ids) < minimum:
        raise ValueError(
            "wiki.gg source integrity: canonical ID coverage "
            f"{len(covered_ids)}/{len(expected_ids)} is below "
            f"the {MIN_WIKI_COVERAGE_PERCENT}% safety floor"
        )

    mechanics_count = sum(
        isinstance(wiki[achievement_id].values.get("unlock_condition_en"), str)
        and bool(wiki[achievement_id].values["unlock_condition_en"].strip())
        for achievement_id in covered_ids
    )
    if mechanics_count < minimum:
        raise ValueError(
            "wiki.gg source integrity: usable English unlock mechanics "
            f"{mechanics_count}/{len(expected_ids)} is below "
            f"the {MIN_WIKI_COVERAGE_PERCENT}% safety floor"
        )


def atomic_write_bytes(path: Path, body: bytes) -> None:
    """Atomically replace *path* with *body* using a neighboring temporary file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        temporary.replace(path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def cache_icon(url: str, destination: Path, *, timeout: float = 15.0) -> bool:
    """Cache one HTTPS image, rejecting empty, oversized, or non-image responses."""

    if destination.is_file() and destination.stat().st_size:
        return True
    if urlsplit(url).scheme != "https":
        return False
    request = Request(url, headers={"User-Agent": USER_AGENT})
    opener = build_opener(_HttpsOnlyRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        if not response.headers.get_content_type().startswith("image/"):
            return False
        body = response.read(MAX_ICON_BYTES + 1)
    if not body or len(body) > MAX_ICON_BYTES:
        return False
    atomic_write_bytes(destination, body)
    return True


def huiji_records_from_previous_catalog(
    catalog_path: Path,
) -> dict[int, SourceAchievement]:
    """Rebuild Huiji records selected by the currently published catalog."""

    if not catalog_path.is_file():
        return {}
    payload = load_catalog(catalog_path)
    achievements = payload.get("achievements", [])
    if not isinstance(achievements, list):
        raise ValueError("previous catalog achievements must be a list")

    records: dict[int, SourceAchievement] = {}
    for achievement in achievements:
        if not isinstance(achievement, Mapping):
            continue
        achievement_id = achievement.get("id")
        sources = achievement.get("sources")
        if (
            not isinstance(achievement_id, int)
            or isinstance(achievement_id, bool)
            or not isinstance(sources, Mapping)
        ):
            continue

        values: dict[str, object] = {}
        field_provenance: dict[str, dict[str, object]] = {}
        source_url: str | None = None
        retrieved_at: str | None = None
        for catalog_field, source_field in _HUIJI_FIELDS.items():
            entries = sources.get(catalog_field)
            if not isinstance(entries, list):
                continue
            provenance = next(
                (
                    entry
                    for entry in entries
                    if isinstance(entry, Mapping) and entry.get("source") == "huiji"
                ),
                None,
            )
            if provenance is None:
                continue
            value = provenance.get("value", nested_value(achievement, catalog_field))
            if value in (None, ""):
                continue
            values[source_field] = value
            candidate_url = provenance.get("source_url") or provenance.get("url")
            field_provenance[source_field] = {
                "source_url": candidate_url,
                "retrieved_at": provenance.get("retrieved_at"),
            }
            if source_url is None:
                if isinstance(candidate_url, str):
                    source_url = candidate_url
            if retrieved_at is None and isinstance(provenance.get("retrieved_at"), str):
                retrieved_at = provenance["retrieved_at"]

        if values:
            records[achievement_id] = SourceAchievement(
                id=achievement_id,
                source="huiji",
                source_url=source_url,
                retrieved_at=retrieved_at,
                values=values,
                field_provenance=field_provenance,
            )
    return records


def _icon_filename(achievement_id: int, url: str) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix not in _ICON_SUFFIXES:
        suffix = ".jpg"
    return f"{achievement_id}{suffix}"


def _resolve_icon_url(reference: str) -> str | None:
    parsed = urlsplit(reference)
    if parsed.scheme == "https" and parsed.netloc:
        return reference
    if _STEAM_ICON_FILENAME.fullmatch(reference):
        return f"{STEAM_ICON_BASE_URL}/{reference}"
    return None


def apply_icon_cache(
    payload: dict[str, object],
    icons_dir: Path,
    icon_cacher: Callable[[str, Path], bool],
) -> None:
    """Replace merged remote icon metadata with browser-relative local paths."""

    achievements = payload.get("achievements", [])
    if not isinstance(achievements, list):
        raise ValueError("catalog achievements must be a list")
    for record in achievements:
        if not isinstance(record, dict):
            raise ValueError("catalog achievement must be an object")
        achievement_id = record.get("id")
        icon = record.get("icon")
        icon_reference = icon.get("unlocked") if isinstance(icon, Mapping) else None
        cached = False
        filename = ""
        remote_url = (
            _resolve_icon_url(icon_reference)
            if isinstance(icon_reference, str)
            else None
        )
        if isinstance(achievement_id, int) and remote_url:
            filename = _icon_filename(achievement_id, remote_url)
            try:
                cached = icon_cacher(remote_url, icons_dir / filename)
            except Exception:
                cached = False
        record["icon"] = (
            {"path": f"assets/achievements/{filename}", "fallback": False}
            if cached
            else {"path": FALLBACK_ICON_PATH, "fallback": True}
        )


def update_achievement_catalog(
    schema_path: Path,
    catalog_path: Path,
    icons_dir: Path,
    *,
    wiki_fetcher=fetch_wiki_achievements,
    huiji_fetcher=fetch_huiji_achievements,
    schema_reader: Callable[[Path], list[AchievementDefinition]] = read_schema,
    icon_cacher: Callable[[str, Path], bool] = cache_icon,
    now: Callable[[], datetime] | None = None,
    expected_count: int = 641,
) -> CatalogUpdateResult:
    """Build, validate, and atomically publish a refreshed catalog."""

    warnings: list[str] = []
    try:
        generated_at = (now or (lambda: datetime.now(tz=timezone.utc)))().isoformat()
        steam = steam_source_records(schema_reader(schema_path))
        wiki = wiki_fetcher()
        _validate_wiki_source_integrity(steam, wiki)
        try:
            huiji = huiji_fetcher()
        except Exception as error:
            huiji = huiji_records_from_previous_catalog(catalog_path)
            warnings.append(f"Huiji update failed: {error}")
        payload = merge_catalog(
            steam,
            wiki,
            huiji,
            generated_at=generated_at,
            secret_count=expected_count,
        )
        apply_icon_cache(payload, icons_dir, icon_cacher)
        validation = publish_catalog(
            payload,
            catalog_path,
            expected_count=expected_count,
            assets_root=icons_dir.parent.parent,
        )
    except Exception as error:
        return CatalogUpdateResult(
            ok=False,
            updated_at=None,
            achievement_count=0,
            completeness={},
            warnings=tuple(warnings),
            errors=(f"{type(error).__name__}: {error}",),
        )

    return CatalogUpdateResult(
        ok=True,
        updated_at=generated_at,
        achievement_count=len(payload["achievements"]),
        completeness=validation.completeness,
        warnings=tuple(warnings) + validation.warnings,
        errors=(),
    )
