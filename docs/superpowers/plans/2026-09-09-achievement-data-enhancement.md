# Achievement Data Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a source-aware, manually refreshed local catalog containing all 641 Isaac achievements with Chinese metadata, exact mapping state, multi-label relationships, rewards, DLC data, and offline icons.

**Architecture:** Independent Steam, wiki.gg, and Huiji adapters emit a shared source-record type. A deterministic merge pipeline applies the approved source precedence, records conflicts and missing reasons, validates the whole catalog, and atomically publishes one runtime JSON file. The existing loopback server joins that immutable metadata with separately stored user progress, while the browser continues to use a concise black interface.

**Tech Stack:** Python 3.12 standard library, `unittest`, HTML5, CSS, vanilla JavaScript, PowerShell.

**Spec:** `docs/superpowers/specs/2026-09-09-achievement-data-enhancement-design.md`

## Global Constraints

- The active catalog must contain exactly 641 unique achievements for the installed game version.
- Local Steam and game files are read-only; generated files stay inside the project.
- Steam achievement state and save-slot Secret state remain separate values.
- The application must start and browse the last valid catalog without network access.
- Catalog refresh is user-triggered and never runs automatically at startup.
- Local Steam schema controls IDs and Steam metadata; wiki.gg controls mechanics; Huiji controls Chinese terminology.
- Conflicts are recorded, never silently blended or guessed.
- A failed refresh must not replace the previous active catalog.
- Use only Python's standard library and the existing no-build frontend.
- Preserve the current concise black interface and keyboard-accessible controls.
- Keep verification focused on parsers, merge rules, validation, atomic publication, and one browser/API contract; do not create one test per achievement or a visual-regression suite.

---

## File Map

- `app/catalog_types.py`: shared immutable source-record and update-result types.
- `app/wiki_catalog.py`: parse and fetch wiki.gg achievement metadata.
- `app/huiji_catalog.py`: parse and fetch Huiji `Data:Achievement.tabx` metadata.
- `app/catalog.py`: character/category registries plus deterministic relationship/category extraction.
- `app/catalog_merge.py`: source precedence, field provenance, conflict capture, Secret mapping, and final record construction.
- `app/catalog_store.py`: catalog validation, loading, and atomic publication.
- `app/catalog_update.py`: end-to-end refresh orchestration and icon caching.
- `tools/update_achievement_catalog.py`: command-line entry point using the same updater as the browser.
- `app/server.py`: serve the active catalog and expose manual catalog-update/status endpoints.
- `web/index.html`, `web/app.js`, `web/styles.css`: separate progress/catalog update controls and enhanced achievement details.
- `data/catalog/achievements.json`: checked-in active catalog.
- `web/assets/achievements/`: checked-in local achievement icons plus fallback icon.
- `tests/test_catalog_sources.py`: representative source-parser coverage.
- `tests/test_catalog_pipeline.py`: merge, validation, and atomic-publication coverage.
- Existing `tests/test_server.py` and `tests/test_web_contract.py`: one focused API and UI contract per new flow.

---

### Task 1: Shared source records and source adapters

**Files:**
- Create: `app/catalog_types.py`
- Modify: `app/wiki_catalog.py`
- Create: `app/huiji_catalog.py`
- Create: `tests/test_catalog_sources.py`
- Delete after migration: `tests/test_wiki_catalog.py`

**Interfaces:**
- Produces: `SourceAchievement(id: int, source: str, source_url: str | None, retrieved_at: str | None, values: Mapping[str, object])`
- Produces: `steam_source_records(definitions: Iterable[AchievementDefinition]) -> dict[int, SourceAchievement]`
- Produces: `parse_wiki_achievement_table(html: str, retrieved_at: str | None = None) -> dict[int, SourceAchievement]`
- Produces: `fetch_wiki_achievements(timeout: float = 30.0) -> dict[int, SourceAchievement]`
- Produces: `parse_huiji_tabx(payload: object, retrieved_at: str | None = None) -> dict[int, SourceAchievement]`
- Produces: `fetch_huiji_achievements(timeout: float = 30.0) -> dict[int, SourceAchievement]`

- [ ] **Step 1: Add one representative parser test for each source**

```python
import unittest

from app.catalog_types import SourceAchievement
from app.huiji_catalog import parse_huiji_tabx
from app.wiki_catalog import parse_wiki_achievement_table


class CatalogSourceTests(unittest.TestCase):
    def test_wiki_parser_keeps_mechanic_reward_and_source(self):
        html = """
        <table class="wikitable"><tr>
          <th>Name</th><th>ID</th><th>Icon</th><th>Description</th><th>Unlock</th><th>Reward</th>
        </tr><tr>
          <td>Meat Cleaver</td><td>440</td><td></td><td>Unlocked an item.</td>
          <td>Defeat Mother as Isaac</td><td>Meat Cleaver</td>
        </tr></table>
        """
        item = parse_wiki_achievement_table(html, "2026-09-09T00:00:00+00:00")[440]
        self.assertIsInstance(item, SourceAchievement)
        self.assertEqual(item.values["unlock_condition_en"], "Defeat Mother as Isaac")
        self.assertEqual(item.values["reward_name_en"], "Meat Cleaver")
        self.assertEqual(item.source, "wiki_gg")

    def test_huiji_tabx_maps_columns_by_schema_name_not_position(self):
        payload = {
            "schema": {"fields": [
                {"name": "ID"}, {"name": "NameZH"}, {"name": "NameEN"},
                {"name": "UnlockReq"}, {"name": "Reward"}, {"name": "DLC"},
            ]},
            "data": [[20, "圣遗物", "The Relic", "用{{chara|抹大拉}}获得以撒通关标记。", "{{item|ID=c98}}", "重生"]],
        }
        item = parse_huiji_tabx(payload, "2026-09-09T00:00:00+00:00")[20]
        self.assertEqual(item.values["name_zh"], "圣遗物")
        self.assertEqual(item.values["unlock_condition_zh"], "用抹大拉获得以撒通关标记。")
        self.assertEqual(item.values["dlc"], "rebirth")
```

- [ ] **Step 2: Run the single source-parser module and verify the intended import failures**

Run: `python -m unittest tests.test_catalog_sources -v`

Expected: FAIL because `catalog_types` and `huiji_catalog` do not exist and the wiki parser does not emit `SourceAchievement`.

- [ ] **Step 3: Define the shared immutable source type and Steam adapter**

```python
# app/catalog_types.py
from dataclasses import dataclass
from typing import Iterable, Mapping

from .readers.steam_stats import AchievementDefinition


@dataclass(frozen=True)
class SourceAchievement:
    id: int
    source: str
    source_url: str | None
    retrieved_at: str | None
    values: Mapping[str, object]


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
```

- [ ] **Step 4: Upgrade the wiki.gg parser and add its fetch function**

Keep the current standard-library `HTMLParser`, but determine columns from normalized header labels and accept both `Achievement` and `Achievements` page layouts. Emit `SourceAchievement` records with `name_en`, `steam_description_en`, `unlock_condition_en`, and `reward_name_en`. `fetch_wiki_achievements()` must call the MediaWiki API URL already used by the maintenance script and add the existing project user agent.

```python
def fetch_wiki_achievements(timeout: float = 30.0) -> dict[int, SourceAchievement]:
    request = Request(API_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    retrieved_at = datetime.now(tz=timezone.utc).isoformat()
    return parse_wiki_achievement_table(payload["parse"]["text"], retrieved_at)
```

- [ ] **Step 5: Implement the Huiji tabular-data adapter**

Fetch `https://isaac.huijiwiki.com/wiki/Data:Achievement.tabx?action=raw` with a project user agent. Parse the JsonConfig `schema.fields` names rather than hard-coded positions. Normalize safe display text by stripping wiki links and known display templates while retaining the raw value in `values["raw_<field>"]`. Map the Chinese DLC labels `重生`, `胎衣`, `胎衣+`, `忏悔`, and `忏悔+` to `rebirth`, `afterbirth`, `afterbirth_plus`, `repentance`, and `repentance_plus`.

```python
HUIJI_RAW_URL = "https://isaac.huijiwiki.com/wiki/Data:Achievement.tabx?action=raw"
DLC_NAMES = {
    "重生": "rebirth", "胎衣": "afterbirth", "胎衣+": "afterbirth_plus",
    "忏悔": "repentance", "忏悔+": "repentance_plus",
}

def fetch_huiji_achievements(timeout: float = 30.0) -> dict[int, SourceAchievement]:
    request = Request(HUIJI_RAW_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    return parse_huiji_tabx(payload, datetime.now(tz=timezone.utc).isoformat())
```

- [ ] **Step 6: Run the focused parser tests**

Run: `python -m unittest tests.test_catalog_sources -v`

Expected: PASS. Do not add per-achievement parser tests.

- [ ] **Step 7: Commit the source-adapter unit**

```powershell
git add app/catalog_types.py app/wiki_catalog.py app/huiji_catalog.py tests/test_catalog_sources.py tests/test_wiki_catalog.py
git commit -m "feat: add achievement source adapters"
```

---

### Task 2: Deterministic catalog merge and explicit classification

**Files:**
- Create: `app/catalog_merge.py`
- Modify: `app/catalog.py`
- Create: `tests/test_catalog_pipeline.py`
- Modify: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `dict[int, SourceAchievement]` from Task 1.
- Produces: `extract_character_relations(condition_zh: str, condition_en: str) -> list[dict[str, str]]`
- Produces: `classify_achievement(values: Mapping[str, object], relations: Sequence[Mapping[str, str]]) -> list[str]`
- Produces: `merge_catalog(steam: Mapping[int, SourceAchievement], wiki: Mapping[int, SourceAchievement], huiji: Mapping[int, SourceAchievement], *, generated_at: str, secret_count: int = 641) -> dict[str, object]`
- The returned payload has `schema_version`, `generated_at`, `achievement_count`, `achievements`, and `diagnostics`.

- [ ] **Step 1: Write two merge tests covering precedence, provenance, conflict retention, and Secret verification**

```python
import unittest

from app.catalog_types import SourceAchievement
from app.catalog_merge import merge_catalog


def source(achievement_id: int, source_name: str, **values) -> SourceAchievement:
    return SourceAchievement(
        id=achievement_id,
        source=source_name,
        source_url=f"https://example.test/{source_name}/{achievement_id}",
        retrieved_at="2026-09-09T00:00:00+00:00",
        values=values,
    )


class CatalogMergeTests(unittest.TestCase):
    def test_merge_applies_precedence_and_records_field_sources(self):
        payload = merge_catalog(
            steam={20: source(20, "steam_schema", steam_name="20", name_en="The Relic", steam_group=1, steam_bit=19)},
            wiki={20: source(20, "wiki_gg", unlock_condition_en="Defeat Isaac as Magdalene", reward_name_en="The Relic")},
            huiji={20: source(20, "huiji", name_zh="圣遗物", unlock_condition_zh="用抹大拉获得以撒通关标记。", reward_name_zh="圣遗物", dlc="rebirth")},
            generated_at="2026-09-09T00:00:00+00:00",
        )
        item = payload["achievements"][0]
        self.assertEqual(item["display"]["name_zh"], "圣遗物")
        self.assertEqual(item["display"]["unlock_condition_en"], "Defeat Isaac as Magdalene")
        self.assertEqual(item["secret"], {"id": 20, "status": "verified", "evidence": ["steam_schema", "wiki_gg", "huiji"]})
        self.assertEqual(item["sources"]["display.name_zh"][0]["source"], "huiji")
        self.assertEqual(item["characters"], [{"id": "magdalene", "relation": "required_character"}])

    def test_merge_keeps_conflict_instead_of_overwriting_it(self):
        payload = merge_catalog(
            steam={1: source(1, "steam_schema", steam_name="1", name_en="Magdalene", steam_group=1, steam_bit=0)},
            wiki={1: source(1, "wiki_gg", name_en="Different Name")},
            huiji={},
            generated_at="2026-09-09T00:00:00+00:00",
        )
        item = payload["achievements"][0]
        self.assertEqual(item["display"]["name_en"], "Magdalene")
        self.assertEqual(item["conflicts"][0]["field"], "display.name_en")
```

- [ ] **Step 2: Run the pipeline test module and verify missing-module failure**

Run: `python -m unittest tests.test_catalog_pipeline -v`

Expected: FAIL because `app.catalog_merge` does not exist.

- [ ] **Step 3: Promote character/category rules to public deterministic functions**

Keep `CHARACTERS` and `CATEGORY_DEFINITIONS` in `app/catalog.py`. Rename the existing private helpers to the published interfaces above. Parse both Chinese character templates/text and English `as/with <character>` phrases. Deduplicate by `(character id, relation)` and retain multi-label categories. Every record must receive at least one category, with `other` used only when no specific rule matches.

- [ ] **Step 4: Implement merge helpers with field-level provenance**

Use one helper per selected field so precedence is explicit:

```python
def choose_field(
    field: str,
    candidates: Sequence[tuple[SourceAchievement, object]],
) -> tuple[object | None, list[dict[str, object]], list[dict[str, object]]]:
    """Return selected value, provenance entries, and conflicting alternatives."""
```

Build nested runtime records with the exact top-level keys `id`, `steam`, `secret`, `display`, `reward`, `characters`, `categories`, `dlc`, `icon`, `sources`, `conflicts`, and `missing`. Keep missing reasons as objects shaped `{"field": "reward.name_zh", "reason": "source_missing"}`.

Mark a Secret mapping `verified` only when the numeric Steam name, wiki ID, and Huiji ID agree and the ID is between 1 and `secret_count`. Otherwise use `unverified` or `conflict` with evidence; never infer a different Secret ID from ordering.

- [ ] **Step 5: Replace heuristic-output assertions with normalized-record assertions**

Retain the existing 34-character uniqueness test and one representative category test in `tests/test_catalog.py`. Remove tests that duplicate coverage now provided by `test_catalog_pipeline.py`.

- [ ] **Step 6: Run only the two affected test modules**

Run: `python -m unittest tests.test_catalog tests.test_catalog_pipeline -v`

Expected: PASS.

- [ ] **Step 7: Commit the merge unit**

```powershell
git add app/catalog.py app/catalog_merge.py tests/test_catalog.py tests/test_catalog_pipeline.py
git commit -m "feat: merge achievement metadata with provenance"
```

---

### Task 3: Catalog validation and atomic storage

**Files:**
- Create: `app/catalog_store.py`
- Modify: `tests/test_catalog_pipeline.py`

**Interfaces:**
- Produces: `CatalogValidation(valid: bool, errors: tuple[str, ...], warnings: tuple[str, ...], completeness: Mapping[str, int])`
- Produces: `validate_catalog(payload: Mapping[str, object], *, expected_count: int = 641, assets_root: Path | None = None) -> CatalogValidation`
- Produces: `load_catalog(path: Path) -> dict[str, object]`
- Produces: `publish_catalog(payload: Mapping[str, object], path: Path, *, expected_count: int = 641, assets_root: Path | None = None) -> CatalogValidation`

- [ ] **Step 1: Add one validator test and one preservation test**

```python
from pathlib import Path
import tempfile

from app.catalog_store import CatalogValidationError, publish_catalog, validate_catalog


def catalog_item(achievement_id: int, *, characters=None) -> dict[str, object]:
    return {
        "id": achievement_id,
        "steam": {"group": 1, "bit": achievement_id - 1, "name": str(achievement_id), "name_en": f"Name {achievement_id}", "description_en": "Description"},
        "secret": {"id": achievement_id, "status": "verified", "evidence": ["steam_schema", "wiki_gg", "huiji"]},
        "display": {"name_zh": f"成就 {achievement_id}", "name_en": f"Name {achievement_id}", "unlock_condition_zh": "条件", "unlock_condition_en": "Condition"},
        "reward": {"name_zh": "奖励", "name_en": "Reward", "type": "item"},
        "characters": characters or [],
        "categories": ["other"],
        "dlc": "rebirth",
        "icon": {"path": "assets/achievements/fallback.svg", "fallback": True},
        "sources": {"display.name_zh": [{"source": "huiji", "url": "https://example.test", "retrieved_at": "2026-09-09T00:00:00+00:00"}]},
        "conflicts": [],
        "missing": [],
    }


def catalog_payload(items: list[dict[str, object]]) -> dict[str, object]:
    return {"schema_version": 2, "generated_at": "2026-09-09T00:00:00+00:00", "achievement_count": len(items), "achievements": items, "diagnostics": {}}


class CatalogStoreTests(unittest.TestCase):
    def test_validator_rejects_duplicate_ids_and_bad_character_reference(self):
        payload = catalog_payload([
            catalog_item(1, characters=[{"id": "not-a-character", "relation": "required_character"}]),
            catalog_item(1),
        ])
        result = validate_catalog(payload, expected_count=2)
        self.assertFalse(result.valid)
        self.assertTrue(any("duplicate achievement id 1" in item for item in result.errors))
        self.assertTrue(any("not-a-character" in item for item in result.errors))

    def test_failed_publication_preserves_previous_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "achievements.json"
            target.write_text('{"version":"old"}', encoding="utf-8")
            with self.assertRaises(CatalogValidationError):
                publish_catalog({"achievements": []}, target, expected_count=641)
            self.assertEqual(target.read_text(encoding="utf-8"), '{"version":"old"}')
```

- [ ] **Step 2: Run the storage-focused tests and verify import failure**

Run: `python -m unittest tests.test_catalog_pipeline.CatalogStoreTests -v`

Expected: FAIL because `app.catalog_store` does not exist.

- [ ] **Step 3: Implement complete structural validation**

Validate the exact constraints from the spec: count, unique numeric IDs, unique Steam group/bit coordinates, required-or-missing fields, valid character/category identifiers, explicit Secret mapping status, local icon/fallback presence, and known provenance sources. Return warnings for fallbacks and unverified mappings; return errors for conflicts that make identity ambiguous.

```python
@dataclass(frozen=True)
class CatalogValidation:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    completeness: Mapping[str, int]

def nested_value(record: Mapping[str, object], dotted: str) -> object | None:
    current: object = record
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current

def validate_catalog(payload, *, expected_count=641, assets_root=None):
    errors: list[str] = []
    warnings: list[str] = []
    achievements = payload.get("achievements", [])
    if len(achievements) != expected_count:
        errors.append(f"expected {expected_count} achievements, found {len(achievements)}")
    required = (
        "steam.name", "display.name_en", "display.name_zh",
        "display.unlock_condition_en", "display.unlock_condition_zh",
        "reward.name_zh", "dlc", "icon.path",
    )
    completeness = {field: 0 for field in required}
    ids: set[int] = set()
    steam_keys: set[tuple[int, int]] = set()
    for record in achievements:
        achievement_id = record.get("id")
        if achievement_id in ids:
            errors.append(f"duplicate achievement id {achievement_id}")
        ids.add(achievement_id)
        steam = record.get("steam", {})
        steam_key = (steam.get("group"), steam.get("bit"))
        if steam_key in steam_keys:
            errors.append(f"duplicate Steam coordinate {steam_key}")
        steam_keys.add(steam_key)
        missing = {item.get("field") for item in record.get("missing", [])}
        for field in required:
            if nested_value(record, field) not in (None, ""):
                completeness[field] += 1
            elif field not in missing:
                errors.append(f"achievement {achievement_id}: {field} lacks value or missing reason")
        for relation in record.get("characters", []):
            if relation.get("id") not in {item["id"] for item in CHARACTERS}:
                errors.append(f"achievement {achievement_id}: unknown character {relation.get('id')}")
        for category in record.get("categories", []):
            if category not in CATEGORY_DEFINITIONS:
                errors.append(f"achievement {achievement_id}: unknown category {category}")
        secret_status = record.get("secret", {}).get("status")
        if secret_status not in {"verified", "unverified", "conflict", "not_applicable"}:
            errors.append(f"achievement {achievement_id}: invalid Secret mapping status")
        if secret_status == "conflict":
            errors.append(f"achievement {achievement_id}: conflicting Secret identity")
        icon_path = Path(str(nested_value(record, "icon.path") or ""))
        if icon_path.is_absolute() or ".." in icon_path.parts:
            errors.append(f"achievement {achievement_id}: unsafe icon path")
        elif assets_root is not None and not (assets_root / icon_path).is_file():
            errors.append(f"achievement {achievement_id}: missing icon {icon_path}")
        if record.get("icon", {}).get("fallback"):
            warnings.append(f"achievement {achievement_id}: fallback icon")
        for field, entries in record.get("sources", {}).items():
            for entry in entries:
                if entry.get("source") not in {"steam_schema", "wiki_gg", "huiji", "translated_wiki_gg"}:
                    errors.append(f"achievement {achievement_id}: unknown source for {field}")
                if not entry.get("url") and not entry.get("origin"):
                    errors.append(f"achievement {achievement_id}: source for {field} lacks URL or local origin")
    return CatalogValidation(not errors, tuple(errors), tuple(warnings), completeness)
```

- [ ] **Step 4: Implement safe loading and atomic publication**

`load_catalog()` must reject non-object JSON and invalid schema versions with `CatalogLoadError`. `publish_catalog()` must validate before writing, create a UTF-8 temporary file in the destination directory, flush it, and use `Path.replace()` only after successful serialization. Clean up the temporary candidate in `finally`.

```python
def publish_catalog(payload, path, *, expected_count=641, assets_root=None):
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
```

- [ ] **Step 5: Run the catalog pipeline tests**

Run: `python -m unittest tests.test_catalog_pipeline -v`

Expected: PASS.

- [ ] **Step 6: Commit the storage unit**

```powershell
git add app/catalog_store.py tests/test_catalog_pipeline.py
git commit -m "feat: validate and atomically publish catalogs"
```

---

### Task 4: Refresh orchestration, fallback behavior, and icon cache

**Files:**
- Create: `app/catalog_update.py`
- Create: `tools/update_achievement_catalog.py`
- Delete after migration: `tools/update_wiki_catalog.py`
- Modify: `tests/test_catalog_pipeline.py`
- Create: `web/assets/achievements/fallback.svg`

**Interfaces:**
- Produces: `CatalogUpdateResult(ok: bool, updated_at: str | None, achievement_count: int, completeness: Mapping[str, int], warnings: tuple[str, ...], errors: tuple[str, ...])`
- Produces: `cache_icon(url: str, destination: Path, *, timeout: float = 15.0) -> bool`
- Produces: `update_achievement_catalog(schema_path: Path, catalog_path: Path, icons_dir: Path, *, wiki_fetcher=fetch_wiki_achievements, huiji_fetcher=fetch_huiji_achievements, schema_reader=read_schema, icon_cacher=cache_icon, now: Callable[[], datetime] | None = None, expected_count: int = 641) -> CatalogUpdateResult`

- [ ] **Step 1: Add one orchestration test for a Huiji outage and old-Chinese-data fallback**

```python
from datetime import datetime, timezone

from app.catalog_store import load_catalog, publish_catalog
from app.catalog_types import steam_source_records
from app.catalog_update import update_achievement_catalog
from app.readers.steam_stats import AchievementDefinition


class CatalogUpdateTests(unittest.TestCase):
    def test_update_uses_previous_chinese_fields_when_huiji_is_unavailable(self):
        definition = AchievementDefinition(1, 0, 1, "Magdalene", "Unlocked a character.", "", "")
        old = merge_catalog(
            steam_source_records([definition]),
            {1: source(1, "wiki_gg", unlock_condition_en="Have seven heart containers")},
            {1: source(1, "huiji", name_zh="抹大拉", unlock_condition_zh="同时拥有七个心之容器。")},
            generated_at="2026-09-08T00:00:00+00:00",
            secret_count=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active = root / "achievements.json"
            icons = root / "web" / "assets" / "achievements"
            icons.mkdir(parents=True)
            (icons / "fallback.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
            publish_catalog(old, active, expected_count=1)
            result = update_achievement_catalog(
                schema_path=root / "schema.bin",
                catalog_path=active,
                icons_dir=icons,
                schema_reader=lambda _: [definition],
                wiki_fetcher=lambda: {1: source(1, "wiki_gg", unlock_condition_en="Have seven heart containers")},
                huiji_fetcher=lambda: (_ for _ in ()).throw(OSError("403")),
                icon_cacher=lambda url, destination: False,
                now=lambda: datetime(2026, 9, 9, tzinfo=timezone.utc),
                expected_count=1,
            )
            self.assertTrue(result.ok)
            self.assertEqual(load_catalog(active)["achievements"][0]["display"]["name_zh"], "抹大拉")
            self.assertTrue(any("Huiji" in item for item in result.warnings))
```

- [ ] **Step 2: Run the single orchestration test and verify failure**

Run: `python -m unittest tests.test_catalog_pipeline.CatalogUpdateTests -v`

Expected: FAIL because the updater does not exist.

- [ ] **Step 3: Implement staged update orchestration**

Read the local schema with `read_schema()`, fetch wiki.gg, then attempt Huiji. If Huiji fails, extract prior Huiji-selected Chinese fields from the active catalog and mark them with their old retrieval date. Merge with a fixed `generated_at`, cache icons, validate, and publish. Convert expected network, parse, validation, and filesystem failures into `CatalogUpdateResult`; do not catch `KeyboardInterrupt` or `SystemExit`.

```python
@dataclass(frozen=True)
class CatalogUpdateResult:
    ok: bool
    updated_at: str | None
    achievement_count: int
    completeness: Mapping[str, int]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]

def update_achievement_catalog(
    schema_path: Path,
    catalog_path: Path,
    icons_dir: Path,
    *,
    wiki_fetcher=fetch_wiki_achievements,
    huiji_fetcher=fetch_huiji_achievements,
    schema_reader=read_schema,
    icon_cacher=cache_icon,
    now: Callable[[], datetime] | None = None,
    expected_count: int = 641,
) -> CatalogUpdateResult:
    warnings: list[str] = []
    generated_at = (now or (lambda: datetime.now(tz=timezone.utc)))().isoformat()
    steam = steam_source_records(schema_reader(schema_path))
    wiki = wiki_fetcher()
    try:
        huiji = huiji_fetcher()
    except (OSError, ValueError, KeyError) as error:
        huiji = huiji_records_from_previous_catalog(catalog_path)
        warnings = [f"Huiji update failed: {error}"]
    payload = merge_catalog(steam, wiki, huiji, generated_at=generated_at, secret_count=expected_count)
    apply_icon_cache(payload, icons_dir, icon_cacher)
    validation = publish_catalog(payload, catalog_path, expected_count=expected_count, assets_root=icons_dir.parent.parent)
    return CatalogUpdateResult(True, generated_at, len(payload["achievements"]), validation.completeness, tuple(warnings + list(validation.warnings)), ())
```

Define `huiji_records_from_previous_catalog()` in the same module; it reconstructs only fields whose selected provenance is `huiji` and preserves their recorded URLs and retrieval times. Define `apply_icon_cache()` there as the sole mutator of `record["icon"]` before publication.

- [ ] **Step 4: Implement local icon caching**

Use achievement ID filenames such as `web/assets/achievements/20.jpg`, reuse an existing non-empty file, restrict requests to `https`, cap each response at 2 MiB, verify `Content-Type` begins with `image/`, write through a neighboring temporary file, and fall back to `fallback.svg` on failure. The catalog's `icon.path` is browser-relative and must never contain a remote URL.

```python
def atomic_write_bytes(path: Path, body: bytes) -> None:
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
    if destination.is_file() and destination.stat().st_size:
        return True
    if urlsplit(url).scheme != "https":
        return False
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        if not response.headers.get_content_type().startswith("image/"):
            return False
        body = response.read(MAX_ICON_BYTES + 1)
    if not body or len(body) > MAX_ICON_BYTES:
        return False
    atomic_write_bytes(destination, body)
    return True
```

- [ ] **Step 5: Replace the maintenance CLI**

`tools/update_achievement_catalog.py` must accept `--schema`, `--output`, and `--icons-dir`, defaulting to discovered local schema, `data/catalog/achievements.json`, and `web/assets/achievements`. It calls only `update_achievement_catalog()` and prints the same summary the HTTP API returns.

```python
result = update_achievement_catalog(
    schema_path=args.schema,
    catalog_path=args.output,
    icons_dir=args.icons_dir,
)
print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
raise SystemExit(0 if result.ok else 1)
```

- [ ] **Step 6: Run the focused pipeline module**

Run: `python -m unittest tests.test_catalog_pipeline -v`

Expected: PASS.

- [ ] **Step 7: Commit the update unit**

```powershell
git add app/catalog_update.py tools/update_achievement_catalog.py tools/update_wiki_catalog.py tests/test_catalog_pipeline.py web/assets/achievements/fallback.svg
git commit -m "feat: add safe achievement catalog refresh"
```

---

### Task 5: Serve the unified catalog and manual update endpoints

**Files:**
- Modify: `app/server.py`
- Modify: `app/snapshots.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_snapshots.py`

**Interfaces:**
- `GET /api/catalog` returns the active catalog plus public character/category registries.
- `GET /api/catalog/status` returns `updated_at`, `achievement_count`, `completeness`, and warnings without refreshing.
- `POST /api/catalog/update` takes `{}` and invokes the catalog updater.
- Existing `POST /api/update` remains the personal-progress endpoint.
- `create_server(host: str = "127.0.0.1", port: int = 0, project_root: Path | None = None, accounts_provider=discover_accounts, catalog_loader=load_catalog, catalog_updater=update_achievement_catalog) -> ThreadingHTTPServer` gains injectable catalog callables for focused tests.

- [ ] **Step 1: Add one API test proving the two update actions stay separate**

```python
def test_catalog_update_does_not_require_account_or_slot(self):
    status, _, body = self.request("POST", "/api/catalog/update", {})
    payload = json.loads(body)
    self.assertEqual(status, 200)
    self.assertTrue(payload["ok"])
    self.assertEqual(self.catalog_update_calls, 1)
    self.assertEqual(self.progress_update_calls, 0)
```

- [ ] **Step 2: Run that test and verify the route is missing**

Run: `python -m unittest tests.test_server.ServerTests.test_catalog_update_does_not_require_account_or_slot -v`

Expected: FAIL with HTTP 404.

- [ ] **Step 3: Load the active catalog instead of rebuilding on every request**

Change `/api/catalog` to call `load_catalog(root / "data/catalog/achievements.json")`. Add `characters` and `categories` to the response without mutating the loaded payload. If loading fails, return a stable `catalog_unavailable` error and leave the rest of the server usable.

```python
if parsed.path == "/api/catalog":
    try:
        payload = dict(catalog_loader(catalog_path))
    except (OSError, ValueError, CatalogLoadError) as exc:
        self._error(503, "catalog_unavailable", str(exc))
        return
    payload["characters"] = _public_characters()
    payload["categories"] = CATEGORY_DEFINITIONS
    self._send_json(200, payload)
    return
```

- [ ] **Step 4: Add status and update endpoints with existing loopback protections**

Apply `_loopback_host()`, `_same_site_update()`, JSON content-type validation, and request-size limits to `/api/catalog/update`. Do not accept source URLs or filesystem paths from the request body. The server selects the discovered schema and project-owned output paths.

```python
if parsed.path == "/api/catalog/update":
    payload = self._read_json_object()
    if payload is None:
        return
    if payload:
        self._error(400, "invalid_request", "成就资料更新不接受参数")
        return
    result = catalog_updater(schema_path, catalog_path, icons_dir)
    self._send_json(200 if result.ok else 422, asdict(result))
    return
```

- [ ] **Step 5: Join progress through explicit nested IDs**

Update snapshot assembly to look up `item["steam"]["group"]` and `item["steam"]["bit"]` for Steam state and `item["secret"]["id"]` only when mapping status is `verified`. Store `steam_unlocked`, `secret_unlocked`, `unlocked_at`, and `sync_warning` as runtime response fields without writing them back into the catalog file.

```python
runtime_item = dict(item)
runtime_item["progress"] = {
    "steam_unlocked": steam_key in unlocked_steam,
    "secret_unlocked": secret_id in unlocked_secrets if secret_id is not None else None,
    "unlocked_at": unlocked_steam.get(steam_key),
    "sync_warning": states_disagree,
}
```

- [ ] **Step 6: Run only server and snapshot tests**

Run: `python -m unittest tests.test_server tests.test_snapshots -v`

Expected: PASS.

- [ ] **Step 7: Commit the server integration**

```powershell
git add app/server.py app/snapshots.py tests/test_server.py tests/test_snapshots.py
git commit -m "feat: expose unified catalog update API"
```

---

### Task 6: Present enhanced metadata in the existing black interface

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/styles.css`
- Modify: `tests/test_web_contract.py`

**Interfaces:**
- Consumes the nested achievement shape from Task 2 and the three catalog routes from Task 5.
- Adds DOM controls `catalog-update`, `catalog-updated-at`, `catalog-update-result`, and `achievement-details`.
- Existing views `characters`, `categories`, `all`, and `character/<id>` remain stable.

- [ ] **Step 1: Add one compact web contract for the new update action and nested display fields**

```python
def test_exposes_separate_catalog_update_and_details(self):
    buttons = self.attrs_for("button")
    self.assertTrue(any(item.get("id") == "catalog-update" for item in buttons))
    self.assertTrue(any(item.get("id") == "achievement-details" for item in self.attrs_for("dialog")))
    script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    self.assertIn("item.display.name_zh", script)
    self.assertIn("/api/catalog/update", script)
```

- [ ] **Step 2: Run the web contract module and verify failure**

Run: `python -m unittest tests.test_web_contract -v`

Expected: FAIL because the new controls and nested access are absent.

- [ ] **Step 3: Separate the two update actions in semantic HTML**

Keep the current native update dialog. Add one section containing the account/slot form for personal progress and a second section containing catalog status and the catalog-update button. Give each action its own `aria-live` result element. Add a separate native dialog for achievement details with a visible close button and labeled title.

```html
<section aria-labelledby="catalog-update-title">
  <h2 id="catalog-update-title">成就资料</h2>
  <p id="catalog-updated-at">尚未读取更新时间</p>
  <button id="catalog-update" type="button">更新成就资料</button>
  <p id="catalog-update-result" role="status" aria-live="polite"></p>
</section>
<dialog id="achievement-details" aria-labelledby="achievement-details-title">
  <h2 id="achievement-details-title"></h2>
  <div id="achievement-details-content"></div>
  <button type="button" data-close-achievement>关闭</button>
</dialog>
```

- [ ] **Step 4: Adapt rendering to the unified catalog**

Use these exact fallbacks:

```javascript
const achievementName = item =>
  item.display.name_zh || item.display.name_en || `成就 #${item.id}`;
const achievementCondition = item =>
  item.display.unlock_condition_zh ||
  item.display.unlock_condition_en ||
  item.steam.description_en ||
  "暂无解锁条件";
```

Character and category filters must use `item.characters[].id` and `item.categories`. Cards show Chinese name, condition, reward, compact tags, local icon, and progress state. The detail dialog additionally shows English name, Steam and Secret states separately, unlock timestamp, DLC, provenance links, missing reasons, and conflicts.

- [ ] **Step 5: Implement catalog refresh behavior**

On catalog-update click, disable only that button, post `{}` as JSON, render its summary, refetch `/api/catalog`, and rerender the current route. A failed request retains the displayed catalog and shows the server's concise error. Personal progress controls and selection stay untouched.

```javascript
catalogUpdate.addEventListener("click", async () => {
  catalogUpdate.disabled = true;
  try {
    const result = await api("/api/catalog/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    catalogUpdateResult.textContent = `已更新 ${result.achievement_count} 项成就资料`;
    model.catalog = await api("/api/catalog");
    route();
  } catch (error) {
    catalogUpdateResult.textContent = error.message;
  } finally {
    catalogUpdate.disabled = false;
  }
});
```

- [ ] **Step 6: Extend the existing CSS tokens without redesigning the application**

Add styles only for the second update section, local icons, metadata tags, definition-list details, warning state, and narrow-screen wrapping. Reuse the current colors, spacing, focus rings, and reduced-motion behavior. Do not add gradients, decorative animation, or a new layout system.

- [ ] **Step 7: Run the web contract module**

Run: `python -m unittest tests.test_web_contract -v`

Expected: PASS.

- [ ] **Step 8: Commit the interface unit**

```powershell
git add web/index.html web/app.js web/styles.css tests/test_web_contract.py
git commit -m "feat: show enhanced achievement metadata"
```

---

### Task 7: Generate the complete catalog, document operation, and verify the phase

**Files:**
- Create: `data/catalog/achievements.json`
- Create: `web/assets/achievements/*`
- Remove after successful migration: `data/catalog/wiki_achievements.json`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- The checked-in catalog is the working offline baseline for a fresh checkout.
- Generated diagnostics/log files remain ignored; the active catalog and browser assets are tracked.

- [ ] **Step 1: Run the updater against the installed schema**

Run:

```powershell
python tools/update_achievement_catalog.py --schema "D:\steam\appcache\stats\UserGameStatsSchema_250900.bin"
```

Expected: reports `641 achievements`, zero identity errors, and explicit warning/completeness counts. If Huiji returns HTTP 403, use the last checked-in Huiji-derived fields and confirm the result records their earlier retrieval date; do not substitute guessed translations.

- [ ] **Step 2: Inspect whole-catalog invariants with the validator**

Run:

```powershell
python -c "from pathlib import Path; from app.catalog_store import load_catalog, validate_catalog; p=load_catalog(Path('data/catalog/achievements.json')); r=validate_catalog(p, assets_root=Path('web')); print(p['achievement_count'], r.valid, len(r.errors), len(r.warnings), r.completeness)"
```

Expected: first values are `641 True 0`; review warnings and completeness rather than requiring invented data.

- [ ] **Step 3: Update ignore and attribution documentation**

Track `data/catalog/achievements.json`, the fallback icon, and successfully cached achievement icons. Ignore temporary candidates, local update logs, and downloaded raw source responses. In `README.md`, document the two update actions, offline behavior, field-source precedence, conflict behavior, Huiji fallback, source links, retrieval metadata, and source/image attribution requirements.

- [ ] **Step 4: Run the focused catalog and contract verification once**

Run:

```powershell
python -m unittest tests.test_catalog_sources tests.test_catalog tests.test_catalog_pipeline tests.test_server tests.test_snapshots tests.test_web_contract -v
```

Expected: PASS with no failures. Do not add or run unrelated visual-regression or per-achievement tests.

- [ ] **Step 5: Perform one local smoke check**

Start with `启动以撒助手.bat`, open the update dialog, verify both update actions are distinct, open one locked and one unlocked achievement, and confirm that Chinese condition, reward, local icon, Steam state, Secret state, and source details render. Stop the server without changing any game file.

- [ ] **Step 6: Commit the generated baseline and documentation**

```powershell
git add .gitignore README.md data/catalog/achievements.json data/catalog/wiki_achievements.json web/assets/achievements
git commit -m "data: publish complete achievement catalog"
```

## Plan Self-Review

- Spec coverage: source precedence, all 641 records, Chinese fields, rewards, multi-label character/category relationships, DLC, icon caching, provenance, conflicts, Secret mapping, manual refresh, offline operation, atomic fallback, UI details, attribution, and minimal verification each map to a task.
- Scope control: completion marks, hard-mode progress, dependency graphs, recommendations, notes, and history views remain excluded.
- Type consistency: all source adapters produce `SourceAchievement`; `merge_catalog()` produces the only runtime catalog shape; storage, updater, server, snapshot join, and browser consume that shape in sequence.
- Safety: HTTP clients cannot provide filesystem paths or source URLs; local Steam/save files are read-only; publication occurs only after validation.
- Test restraint: four focused test areas replace broad duplication, with one combined verification run at the end.
