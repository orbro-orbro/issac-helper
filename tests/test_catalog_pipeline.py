import unittest
from pathlib import Path
import tempfile

from app.catalog_types import SourceAchievement
from app.catalog_merge import merge_catalog
from app.catalog_store import CatalogValidationError, publish_catalog, validate_catalog


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


if __name__ == "__main__":
    unittest.main()
