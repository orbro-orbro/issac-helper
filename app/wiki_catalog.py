"""Parse and load the versioned wiki.gg achievement knowledge snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

from .catalog_types import SourceAchievement


SOURCE_URL = "https://bindingofisaacrebirth.wiki.gg/wiki/Achievement"
API_URL = (
    "https://bindingofisaacrebirth.wiki.gg/api.php"
    "?action=parse&page=Achievements&prop=text&format=json&formatversion=2"
)
USER_AGENT = "IsaacHelper/0.1 catalog maintenance"
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog" / "wiki_achievements.json"


def _clean(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


_HEADER_NAMES = {
    "name": "name_en",
    "achievement": "name_en",
    "achievementname": "name_en",
    "id": "id",
    "achievementid": "id",
    "description": "steam_description_en",
    "steamdescription": "steam_description_en",
    "unlock": "unlock_condition_en",
    "unlockcondition": "unlock_condition_en",
    "unlockrequirement": "unlock_condition_en",
    "unlockrequirements": "unlock_condition_en",
    "reward": "reward_name_en",
    "rewardname": "reward_name_en",
}


class _AchievementTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.table_depth = 0
        self.in_row = False
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.cells: list[str] = []
        self.cell_tags: list[str] = []
        self.headers: list[str] | None = None
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attributes = dict(attrs)
        if tag == "table":
            if self.in_table:
                self.table_depth += 1
            elif "wikitable" in attributes.get("class", "").split():
                self.in_table = True
                self.table_depth = 1
            return
        if not self.in_table:
            return
        if tag == "tr" and self.table_depth == 1:
            self.in_row = True
            self.cells = []
            self.cell_tags = []
        elif tag in {"td", "th"} and self.in_row:
            self.in_cell = True
            self.cell_parts = []
            self.cell_tags.append(tag)
        elif tag == "br" and self.in_cell:
            self.cell_parts.append(" ")

    def handle_data(self, data: str):
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str):
        if not self.in_table:
            return
        if tag in {"td", "th"} and self.in_cell:
            self.cells.append(_clean(self.cell_parts))
            self.in_cell = False
            self.cell_parts = []
        elif tag == "tr" and self.in_row:
            self._finish_row()
            self.in_row = False
        elif tag == "table":
            self.table_depth -= 1
            if self.table_depth <= 0:
                self.in_table = False

    def _finish_row(self) -> None:
        if self.headers is None and self.cells and all(tag == "th" for tag in self.cell_tags):
            normalized = [_HEADER_NAMES.get(_header_key(cell), "") for cell in self.cells]
            if "id" in normalized and "name_en" in normalized:
                self.headers = normalized
            return
        if self.headers is not None and len(self.cells) == len(self.headers):
            self.rows.append(self.cells)


def parse_wiki_achievement_table(
    html: str, retrieved_at: str | None = None
) -> dict[int, SourceAchievement]:
    parser = _AchievementTableParser()
    parser.feed(html)
    parser.close()
    if parser.headers is None:
        return {}
    records: dict[int, SourceAchievement] = {}
    for row in parser.rows:
        values = {
            header: value
            for header, value in zip(parser.headers, row)
            if header
        }
        raw_id = values.pop("id", "")
        if not isinstance(raw_id, str) or not raw_id.isdigit():
            continue
        achievement_id = int(raw_id)
        records[achievement_id] = SourceAchievement(
            id=achievement_id,
            source="wiki_gg",
            source_url=SOURCE_URL,
            retrieved_at=retrieved_at,
            values={
                "name_en": values.get("name_en", ""),
                "steam_description_en": values.get("steam_description_en", ""),
                "unlock_condition_en": values.get("unlock_condition_en", ""),
                "reward_name_en": values.get("reward_name_en", ""),
            },
        )
    return records


def parse_achievement_table(html: str) -> dict[int, dict[str, object]]:
    """Return the legacy snapshot shape used by the maintenance command."""

    return {
        achievement_id: {
            "id": achievement_id,
            "name_en": item.values["name_en"],
            "steam_description": item.values["steam_description_en"],
            "unlock_condition_en": item.values["unlock_condition_en"],
            "url": SOURCE_URL,
        }
        for achievement_id, item in parse_wiki_achievement_table(html).items()
    }


def fetch_wiki_achievements(timeout: float = 30.0) -> dict[int, SourceAchievement]:
    request = Request(API_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    retrieved_at = datetime.now(tz=timezone.utc).isoformat()
    return parse_wiki_achievement_table(payload["parse"]["text"], retrieved_at)


def load_wiki_overrides(path: Path = DEFAULT_PATH) -> dict[int, dict[str, object]]:
    source = Path(path)
    if not source.is_file():
        return {}
    payload = json.loads(source.read_text(encoding="utf-8"))
    values = payload.get("achievements", []) if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise ValueError("wiki achievement catalog must contain a list")
    result: dict[int, dict[str, object]] = {}
    for item in values:
        if isinstance(item, dict) and isinstance(item.get("id"), int):
            result[item["id"]] = item
    return result
