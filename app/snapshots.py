"""Build, validate, and atomically store private local progress snapshots."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable, Mapping

from .catalog_store import CatalogLoadError, load_catalog
from .discovery import Selection
from .readers.binary_kv import parse_binary_keyvalues
from .readers.isaac_save import IsaacSaveError, parse_secrets
from .readers.steam_stats import extract_schema, extract_unlocked


class SnapshotError(RuntimeError):
    """Raised when a snapshot cannot be generated safely."""


def snapshot_path(output_root: Path, account_id: str, slot: int) -> Path:
    if not isinstance(account_id, str) or not account_id.isdigit():
        raise ValueError("account_id must contain digits only")
    if slot not in (1, 2, 3):
        raise ValueError("slot must be 1, 2, or 3")
    return Path(output_root) / account_id / f"slot-{slot}" / "current.json"


def write_snapshot_atomic(path: Path, payload: Mapping[str, object]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.stem}-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
        temp_name = None
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink()
            except FileNotFoundError:
                pass


def load_snapshot(
    output_root: Path, account_id: str, slot: int
) -> dict[str, object] | None:
    path = snapshot_path(output_root, account_id, slot)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"cannot read snapshot: {exc}") from exc
    if not isinstance(value, dict):
        raise SnapshotError("snapshot root must be a JSON object")
    return value


def merge_progress(
    catalog: Iterable[Mapping[str, object]],
    unlocked: Mapping[tuple[int, int], datetime | None],
    secret_ids: Iterable[int],
) -> tuple[list[dict[str, object]], dict[str, int], list[dict[str, object]]]:
    secrets = set(secret_ids)
    items: list[dict[str, object]] = []
    differences: list[dict[str, object]] = []
    for source_item in catalog:
        item = deepcopy(dict(source_item))
        achievement_id = int(item["id"])
        steam = item.get("steam")
        group = steam.get("group") if isinstance(steam, Mapping) else None
        bit = steam.get("bit") if isinstance(steam, Mapping) else None
        steam_key = (
            (group, bit)
            if isinstance(group, int)
            and not isinstance(group, bool)
            and isinstance(bit, int)
            and not isinstance(bit, bool)
            else None
        )
        steam_unlocked = steam_key in unlocked if steam_key is not None else False
        secret = item.get("secret")
        mapped_secret_id = (
            secret.get("id")
            if isinstance(secret, Mapping)
            and secret.get("status") == "verified"
            and isinstance(secret.get("id"), int)
            and not isinstance(secret.get("id"), bool)
            else None
        )
        secret_unlocked = (
            mapped_secret_id in secrets if mapped_secret_id is not None else None
        )
        unlocked_at = unlocked.get(steam_key) if steam_key is not None else None
        states_disagree = (
            secret_unlocked is not None and steam_unlocked != secret_unlocked
        )
        item["progress"] = {
            "steam_unlocked": steam_unlocked,
            "secret_unlocked": secret_unlocked,
            "unlocked_at": unlocked_at.isoformat() if unlocked_at else None,
            "sync_warning": states_disagree,
        }
        items.append(item)
        if states_disagree:
            differences.append({
                "id": achievement_id,
                "steam_unlocked": steam_unlocked,
                "secret_unlocked": secret_unlocked,
            })
    summary = {
        "total": len(items),
        "steam_unlocked": sum(
            bool(item["progress"]["steam_unlocked"]) for item in items
        ),
        "game_secrets_unlocked": len(secrets),
        "sync_difference_count": len(differences),
    }
    return items, summary, differences


def _read_stable(path: Path) -> tuple[bytes, os.stat_result]:
    source = Path(path)
    before = source.stat()
    data = source.read_bytes()
    after = source.stat()
    before_key = (before.st_size, before.st_mtime_ns)
    after_key = (after.st_size, after.st_mtime_ns)
    if before_key != after_key or len(data) != after.st_size:
        raise SnapshotError(f"source changed while reading: {source.name}")
    return data, after


def _source_record(
    path: Path, data: bytes, stat: os.stat_result
) -> dict[str, object]:
    return {
        "filename": path.name,
        "path": str(path),
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "size": stat.st_size,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def build_snapshot(
    selection: Selection,
    output_root: Path,
    *,
    catalog_path: Path | None = None,
) -> dict[str, object]:
    account = selection.account
    missing = [
        path for path in (account.schema_path, account.stats_path)
        if not path.is_file()
    ]
    if missing:
        raise SnapshotError("missing Steam stats file: " + ", ".join(path.name for path in missing))

    schema_bytes, schema_stat = _read_stable(account.schema_path)
    stats_bytes, stats_stat = _read_stable(account.stats_path)
    save_bytes, save_stat = _read_stable(selection.slot.save_path)
    definitions = extract_schema(parse_binary_keyvalues(schema_bytes))
    unlocked_by_id = extract_unlocked(parse_binary_keyvalues(stats_bytes), definitions)
    unlocked = {
        (definition.group, definition.bit): unlocked_by_id[definition.id]
        for definition in definitions
        if definition.id in unlocked_by_id
    }
    secret_ids: frozenset[int] = frozenset()
    secret_state: dict[str, object]
    try:
        secrets = parse_secrets(save_bytes)
        secret_ids = secrets.unlocked_ids
        secret_state = {
            "format": secrets.format_name,
            "count": secrets.secret_count,
            "unlocked_ids": sorted(secret_ids),
            "error": None,
        }
    except IsaacSaveError as exc:
        secret_state = {
            "format": None,
            "count": None,
            "unlocked_ids": [],
            "error": str(exc),
        }

    active_catalog_path = Path(catalog_path) if catalog_path else (
        Path(output_root).parent / "catalog" / "achievements.json"
    )
    try:
        active_catalog = load_catalog(active_catalog_path)
    except CatalogLoadError as exc:
        raise SnapshotError(f"achievement catalog unavailable: {exc}") from exc
    catalog_items = active_catalog.get("achievements")
    if not isinstance(catalog_items, list):
        raise SnapshotError("achievement catalog has no achievement list")
    items, summary, differences = merge_progress(catalog_items, unlocked, secret_ids)
    target = snapshot_path(output_root, account.id, selection.slot.number)
    previous = load_snapshot(output_root, account.id, selection.slot.number)
    previous_unlocked = {
        int(item["id"])
        for item in (previous or {}).get("achievements", [])
        if isinstance(item, dict)
        and (
            (
                isinstance(item.get("progress"), dict)
                and item["progress"].get("steam_unlocked")
            )
            or item.get("steam_unlocked")
        )
    }
    newly_unlocked = sorted(set(unlocked_by_id) - previous_unlocked) if previous else []
    now = datetime.now(tz=timezone.utc).isoformat()
    payload: dict[str, object] = {
        "schema_version": 1,
        "steam_account_id": account.id,
        "slot": selection.slot.number,
        "generated_at": now,
        "source_files": [
            _source_record(account.schema_path, schema_bytes, schema_stat),
            _source_record(account.stats_path, stats_bytes, stats_stat),
            _source_record(selection.slot.save_path, save_bytes, save_stat),
        ],
        "achievements": items,
        "game_secrets": secret_state,
        "completion_marks": {
            "status": "not_available",
            "reason": "当前存档格式的通关标记偏移尚未经过验证",
        },
        "summary": summary,
        "sync_differences": differences,
        "changes": {"new_steam_unlocks": newly_unlocked},
    }

    if previous:
        history_dir = target.parent / "history"
        stamp = str(previous.get("generated_at", "previous")).replace(":", "-")
        history_path = history_dir / f"{stamp}.json"
        if not history_path.exists():
            write_snapshot_atomic(history_path, previous)
    write_snapshot_atomic(target, payload)
    return payload
