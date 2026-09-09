import unittest
from datetime import datetime, timezone
from email.message import Message
from io import BytesIO
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import BaseHandler, build_opener
from urllib.response import addinfourl

from app.catalog_types import SourceAchievement, steam_source_records
from app.catalog_merge import merge_catalog
from app.catalog_store import (
    CatalogValidationError,
    load_catalog,
    publish_catalog,
    validate_catalog,
)
from app.catalog_update import (
    apply_icon_cache,
    cache_icon,
    huiji_records_from_previous_catalog,
    update_achievement_catalog,
)
from app.readers.steam_stats import AchievementDefinition


def source(achievement_id: int, source_name: str, **values) -> SourceAchievement:
    return SourceAchievement(
        id=achievement_id,
        source=source_name,
        source_url=f"https://example.test/{source_name}/{achievement_id}",
        retrieved_at="2026-09-09T00:00:00+00:00",
        values=values,
    )


def catalog_item(achievement_id: int, *, characters=None) -> dict[str, object]:
    return {
        "id": achievement_id,
        "steam": {
            "group": 1,
            "bit": achievement_id - 1,
            "name": str(achievement_id),
            "name_en": f"Name {achievement_id}",
            "description_en": "Description",
        },
        "secret": {
            "id": achievement_id,
            "status": "verified",
            "evidence": ["steam_schema", "wiki_gg", "huiji"],
        },
        "display": {
            "name_zh": f"成就 {achievement_id}",
            "name_en": f"Name {achievement_id}",
            "unlock_condition_zh": "条件",
            "unlock_condition_en": "Condition",
        },
        "reward": {"name_zh": "奖励", "name_en": "Reward", "type": "item"},
        "characters": characters or [],
        "categories": ["other"],
        "dlc": "rebirth",
        "icon": {"path": "assets/achievements/fallback.svg", "fallback": True},
        "sources": {
            "display.name_zh": [{
                "source": "huiji",
                "url": "https://example.test",
                "retrieved_at": "2026-09-09T00:00:00+00:00",
            }]
        },
        "conflicts": [],
        "missing": [],
    }


def catalog_payload(items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 2,
        "generated_at": "2026-09-09T00:00:00+00:00",
        "achievement_count": len(items),
        "achievements": items,
        "diagnostics": {},
    }


class CatalogMergeTests(unittest.TestCase):
    def test_merge_applies_precedence_and_records_field_sources(self):
        payload = merge_catalog(
            steam={20: SourceAchievement(
                id=20,
                source="steam_schema",
                source_url=None,
                retrieved_at=None,
                values={
                    "steam_name": "20",
                    "name_en": "The Relic",
                    "steam_group": 1,
                    "steam_bit": 19,
                },
            )},
            wiki={20: source(20, "wiki_gg", unlock_condition_en="Defeat Isaac as Magdalene", reward_name_en="The Relic")},
            huiji={20: source(20, "huiji", name_zh="圣遗物", unlock_condition_zh="用抹大拉获得以撒通关标记。", reward_name_zh="圣遗物", dlc="rebirth")},
            generated_at="2026-09-09T00:00:00+00:00",
        )
        item = payload["achievements"][0]
        self.assertEqual(item["display"]["name_zh"], "圣遗物")
        self.assertEqual(item["display"]["unlock_condition_en"], "Defeat Isaac as Magdalene")
        self.assertEqual(item["secret"], {"id": 20, "status": "verified", "evidence": ["steam_schema", "wiki_gg", "huiji"]})
        self.assertEqual(item["sources"]["display.name_zh"][0]["source"], "huiji")
        self.assertEqual(
            item["sources"]["steam.name"][0]["origin"],
            "local_steam_schema",
        )
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

    def test_external_only_ids_are_diagnostic_not_canonical(self):
        payload = merge_catalog(
            steam={},
            wiki={
                999: source(999, "wiki_gg", name_en="Future achievement"),
                997: source(997, "wiki_gg", name_en="Earlier future achievement"),
            },
            huiji={
                998: source(998, "huiji", name_zh="未来成就"),
                996: source(996, "huiji", name_zh="较早的未来成就"),
            },
            generated_at="2026-09-09T00:00:00+00:00",
        )

        self.assertEqual(payload["achievements"], [])
        self.assertEqual(payload["diagnostics"]["external_only_ids"], {
            "wiki_gg": [997, 999],
            "huiji": [996, 998],
        })


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

    def test_validator_requires_a_reason_for_missing_fields(self):
        item = catalog_item(1)
        item["display"]["name_en"] = ""
        item["missing"] = [{"field": "display.name_en"}]

        result = validate_catalog(catalog_payload([item]), expected_count=1)

        self.assertFalse(result.valid)
        self.assertTrue(any("missing reason" in error for error in result.errors))

    def test_validator_rejects_mismatched_or_conflicted_identity_fields(self):
        item = catalog_item(1)
        item["secret"]["id"] = 2
        item["conflicts"] = [{"field": "steam.name"}]

        result = validate_catalog(catalog_payload([item]), expected_count=1)

        self.assertFalse(result.valid)
        self.assertTrue(any("Secret id" in error for error in result.errors))
        self.assertTrue(any("conflicting identity field steam.name" in error for error in result.errors))

    def test_validator_aggregates_malformed_relations_and_categories(self):
        invalid_relation = catalog_item(1, characters=[{"id": [], "relation": "required_character"}])
        invalid_category = catalog_item(2)
        invalid_category["categories"] = [{}]
        empty_categories = catalog_item(3)
        empty_categories["categories"] = []

        result = validate_catalog(
            catalog_payload([invalid_relation, invalid_category, empty_categories]),
            expected_count=3,
        )

        self.assertFalse(result.valid)
        self.assertTrue(any("unknown character" in error for error in result.errors))
        self.assertTrue(any("unknown category" in error for error in result.errors))
        self.assertTrue(any("at least one registered category" in error for error in result.errors))

    def test_failed_serialization_cleans_temporary_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "achievements.json"
            payload = catalog_payload([catalog_item(1)])
            payload["not_serializable"] = {1}

            with self.assertRaises(TypeError):
                publish_catalog(payload, target, expected_count=1)

            self.assertEqual(list(Path(directory).iterdir()), [])


class CatalogUpdateTests(unittest.TestCase):
    def test_huiji_fallback_preserves_provenance_for_each_retained_field(self):
        previous = {
            "schema_version": 2,
            "achievements": [{
                "id": 1,
                "display": {
                    "name_zh": "抹大拉",
                    "unlock_condition_zh": "同时拥有七个心之容器。",
                },
                "sources": {
                    "display.name_zh": [{
                        "source": "huiji",
                        "source_url": "https://huiji.example/name",
                        "retrieved_at": "2026-09-07T01:00:00+00:00",
                        "value": "抹大拉",
                    }],
                    "display.unlock_condition_zh": [{
                        "source": "huiji",
                        "source_url": "https://huiji.example/condition",
                        "retrieved_at": "2026-09-08T02:00:00+00:00",
                        "value": "同时拥有七个心之容器。",
                    }],
                },
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            active = Path(directory) / "achievements.json"
            active.write_text(
                json.dumps(previous, ensure_ascii=False), encoding="utf-8"
            )
            huiji = huiji_records_from_previous_catalog(active)

        payload = merge_catalog(
            steam={1: SourceAchievement(
                id=1,
                source="steam_schema",
                source_url=None,
                retrieved_at=None,
                values={
                    "steam_name": "1",
                    "name_en": "Magdalene",
                    "steam_group": 1,
                    "steam_bit": 0,
                },
            )},
            wiki={1: source(
                1,
                "wiki_gg",
                unlock_condition_en="Have seven heart containers",
            )},
            huiji=huiji,
            generated_at="2026-09-09T00:00:00+00:00",
            secret_count=1,
        )
        sources = payload["achievements"][0]["sources"]
        self.assertEqual(sources["display.name_zh"][0]["source_url"],
                         "https://huiji.example/name")
        self.assertEqual(sources["display.name_zh"][0]["retrieved_at"],
                         "2026-09-07T01:00:00+00:00")
        self.assertEqual(sources["display.unlock_condition_zh"][0]["source_url"],
                         "https://huiji.example/condition")
        self.assertEqual(sources["display.unlock_condition_zh"][0]["retrieved_at"],
                         "2026-09-08T02:00:00+00:00")

    def test_icon_cache_rejects_https_to_http_redirect_before_following_it(self):
        http_requests: list[str] = []

        class RedirectTransport(BaseHandler):
            handler_order = 100

            def https_open(self, request):
                headers = Message()
                headers["Location"] = "http://unsafe.example/icon.jpg"
                response = addinfourl(
                    BytesIO(b""), headers, request.full_url, code=302
                )
                response.msg = "Found"
                return response

            def http_open(self, request):
                http_requests.append(request.full_url)
                raise AssertionError("HTTP redirect request was issued")

        transport = RedirectTransport()

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "1.jpg"
            with (
                patch(
                    "app.catalog_update.build_opener",
                    side_effect=lambda *handlers: build_opener(
                        transport, *handlers
                    ),
                ),
                self.assertRaises(HTTPError),
            ):
                cache_icon("https://safe.example/icon.jpg", destination)
            self.assertFalse(destination.exists())

        self.assertEqual(http_requests, [])

    def test_icon_cache_resolves_real_steam_hash_filename(self):
        icon_hash = "a36d7e92df7e991758907a75dfa55d36b52548c4.jpg"
        payload = {
            "achievements": [{"id": 1, "icon": {"unlocked": icon_hash}}]
        }
        cached_urls: list[str] = []

        def cache(url: str, destination: Path) -> bool:
            cached_urls.append(url)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"image")
            return True

        with tempfile.TemporaryDirectory() as directory:
            apply_icon_cache(payload, Path(directory), cache)

        self.assertEqual(cached_urls, [
            "https://shared.fastly.steamstatic.com/community_assets/images/"
            "apps/250900/a36d7e92df7e991758907a75dfa55d36b52548c4.jpg"
        ])
        self.assertEqual(payload["achievements"][0]["icon"], {
            "path": "assets/achievements/1.jpg",
            "fallback": False,
        })

    def test_update_uses_previous_chinese_fields_when_huiji_is_unavailable(self):
        definition = AchievementDefinition(
            1, 0, 1, "Magdalene", "Unlocked a character.", "", ""
        )
        old = merge_catalog(
            steam_source_records([definition]),
            {1: source(
                1,
                "wiki_gg",
                unlock_condition_en="Have seven heart containers",
            )},
            {1: source(
                1,
                "huiji",
                name_zh="抹大拉",
                unlock_condition_zh="同时拥有七个心之容器。",
            )},
            generated_at="2026-09-08T00:00:00+00:00",
            secret_count=1,
        )
        old["achievements"][0]["icon"] = {
            "path": "assets/achievements/fallback.svg",
            "fallback": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active = root / "achievements.json"
            icons = root / "web" / "assets" / "achievements"
            icons.mkdir(parents=True)
            (icons / "fallback.svg").write_text(
                "<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8"
            )
            active.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
            result = update_achievement_catalog(
                schema_path=root / "schema.bin",
                catalog_path=active,
                icons_dir=icons,
                schema_reader=lambda _: [definition],
                wiki_fetcher=lambda: {1: source(
                    1,
                    "wiki_gg",
                    unlock_condition_en="Have seven heart containers",
                )},
                huiji_fetcher=lambda: (_ for _ in ()).throw(OSError("403")),
                icon_cacher=lambda url, destination: False,
                now=lambda: datetime(2026, 9, 9, tzinfo=timezone.utc),
                expected_count=1,
            )
            self.assertTrue(result.ok)
            self.assertEqual(
                load_catalog(active)["achievements"][0]["display"]["name_zh"],
                "抹大拉",
            )
            self.assertTrue(any("Huiji" in item for item in result.warnings))


if __name__ == "__main__":
    unittest.main()
