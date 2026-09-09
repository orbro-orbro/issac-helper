import unittest

from app.catalog import CHARACTERS
from app.catalog_merge import merge_catalog
from app.catalog_types import SourceAchievement


def source(achievement_id: int, source_name: str, **values) -> SourceAchievement:
    return SourceAchievement(
        id=achievement_id,
        source=source_name,
        source_url=None,
        retrieved_at=None,
        values=values,
    )


class CatalogTests(unittest.TestCase):
    def test_contains_all_normal_and_tainted_characters(self):
        self.assertEqual(len(CHARACTERS), 34)
        self.assertEqual(len({item["id"] for item in CHARACTERS}), 34)

    def test_normalized_record_retains_multiple_representative_categories(self):
        payload = merge_catalog(
            steam={322: source(
                322,
                "steam_schema",
                steam_name="322",
                name_en="Hat trick!",
                steam_group=6,
                steam_bit=1,
            )},
            wiki={322: source(
                322,
                "wiki_gg",
                unlock_condition_en="Defeat Mother as Isaac without taking damage",
            )},
            huiji={},
            generated_at="2026-09-09T00:00:00+00:00",
        )

        item = payload["achievements"][0]
        self.assertEqual(
            item["categories"],
            ["character", "route_boss", "special_run"],
        )


if __name__ == "__main__":
    unittest.main()
