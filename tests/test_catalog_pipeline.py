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

    def test_external_only_ids_are_diagnostic_not_canonical(self):
        payload = merge_catalog(
            steam={},
            wiki={999: source(999, "wiki_gg", name_en="Future achievement")},
            huiji={},
            generated_at="2026-09-09T00:00:00+00:00",
        )

        self.assertEqual(payload["achievements"], [])
        self.assertEqual(payload["diagnostics"]["external_only_ids"], [
            {"id": 999, "sources": ["wiki_gg"]}
        ])


if __name__ == "__main__":
    unittest.main()
