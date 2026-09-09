"""Read Chinese achievement metadata from Huiji's JsonConfig table."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Mapping
from urllib.request import Request, urlopen

from .catalog_types import SourceAchievement


HUIJI_RAW_URL = "https://isaac.huijiwiki.com/wiki/Data:Achievement.tabx?action=raw"
USER_AGENT = "IsaacHelper/0.1 catalog maintenance"
DLC_NAMES = {
    "重生": "rebirth",
    "胎衣": "afterbirth",
    "胎衣+": "afterbirth_plus",
    "忏悔": "repentance",
    "忏悔+": "repentance_plus",
}

_FIELD_NAMES = {
    "id": "id",
    "namezh": "name_zh",
    "nameen": "name_en",
    "unlockreq": "unlock_condition_zh",
    "reward": "reward_zh",
    "dlc": "dlc",
}


def _field_key(name: str) -> str:
    return _FIELD_NAMES.get(re.sub(r"[^a-z0-9]", "", name.lower()), name)


def _display_text(value: object) -> object:
    if not isinstance(value, str):
        return value

    def link(match: re.Match[str]) -> str:
        return match.group(1).split("|")[-1]

    def template(match: re.Match[str]) -> str:
        parts = [part.strip() for part in match.group(1).split("|")]
        if len(parts) < 2:
            return ""
        display = [part for part in parts[1:] if "=" not in part]
        return display[-1] if display else ""

    text = re.sub(r"\[\[([^\]]+)\]\]", link, value)
    text = re.sub(r"\{\{([^{}]+)\}\}", template, text)
    return re.sub(r"\s+", " ", text).strip()


def parse_huiji_tabx(
    payload: object, retrieved_at: str | None = None
) -> dict[int, SourceAchievement]:
    if not isinstance(payload, Mapping):
        raise ValueError("Huiji achievement payload must be an object")
    schema = payload.get("schema")
    data = payload.get("data")
    if not isinstance(schema, Mapping) or not isinstance(schema.get("fields"), list):
        raise ValueError("Huiji achievement payload has no schema fields")
    if not isinstance(data, list):
        raise ValueError("Huiji achievement payload has no data rows")

    field_names: list[str] = []
    for field in schema["fields"]:
        if not isinstance(field, Mapping) or not isinstance(field.get("name"), str):
            raise ValueError("Huiji achievement schema contains an invalid field")
        field_names.append(field["name"])
    try:
        id_index = field_names.index("ID")
    except ValueError as exc:
        raise ValueError("Huiji achievement schema has no ID field") from exc

    records: dict[int, SourceAchievement] = {}
    for row in data:
        if not isinstance(row, list) or len(row) != len(field_names):
            raise ValueError("Huiji achievement data row does not match its schema")
        raw_id = row[id_index]
        if isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)):
            raise ValueError("Huiji achievement row has an invalid ID")
        try:
            achievement_id = int(raw_id)
        except ValueError as exc:
            raise ValueError("Huiji achievement row has an invalid ID") from exc
        values: dict[str, object] = {}
        for field_name, raw_value in zip(field_names, row):
            key = _field_key(field_name)
            values[f"raw_{key}"] = raw_value
            values[key] = _display_text(raw_value)
        if isinstance(values.get("dlc"), str):
            values["dlc"] = DLC_NAMES.get(values["dlc"], values["dlc"])
        records[achievement_id] = SourceAchievement(
            id=achievement_id,
            source="huiji",
            source_url=HUIJI_RAW_URL,
            retrieved_at=retrieved_at,
            values=values,
        )
    return records


def fetch_huiji_achievements(timeout: float = 30.0) -> dict[int, SourceAchievement]:
    request = Request(HUIJI_RAW_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    return parse_huiji_tabx(payload, datetime.now(tz=timezone.utc).isoformat())
