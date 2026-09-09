"""Parse and load the versioned wiki.gg achievement knowledge snapshot."""

from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re


SOURCE_URL = "https://bindingofisaacrebirth.wiki.gg/wiki/Achievement"
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog" / "wiki_achievements.json"


def _clean(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


class _AchievementTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.table_depth = 0
        self.in_row = False
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.cells: list[str] = []
        self.records: dict[int, dict[str, object]] = {}

    def handle_starttag(self, tag, attrs):
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
        elif tag in {"td", "th"} and self.in_row:
            self.in_cell = True
            self.cell_parts = []
        elif tag == "br" and self.in_cell:
            self.cell_parts.append(" ")

    def handle_data(self, data):
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag):
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
        if len(self.cells) < 5 or not self.cells[1].isdigit():
            return
        achievement_id = int(self.cells[1])
        self.records[achievement_id] = {
            "id": achievement_id,
            "name_en": self.cells[0],
            "steam_description": self.cells[3],
            "unlock_condition_en": self.cells[4],
            "url": SOURCE_URL,
        }


def parse_achievement_table(html: str) -> dict[int, dict[str, object]]:
    parser = _AchievementTableParser()
    parser.feed(html)
    return parser.records


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
