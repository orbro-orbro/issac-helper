import unittest

from app.catalog import CHARACTERS, extract_character_relations
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

    def test_question_mark_character_aliases_match_before_punctuation(self):
        cases = (
            ("Defeat Isaac as ???.", "blue_baby"),
            ("Defeat Isaac as Tainted ???.", "tainted_blue_baby"),
        )
        for condition, character_id in cases:
            with self.subTest(condition=condition):
                self.assertEqual(
                    extract_character_relations("", condition),
                    [{"id": character_id, "relation": "required_character"}],
                )

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

    def test_normalized_record_exposes_steam_description_in_both_namespaces(self):
        payload = merge_catalog(
            steam={1: source(
                1,
                "steam_schema",
                steam_name="1",
                name_en="The Sad Onion",
                steam_description_en="Complete the first chapter.",
                steam_group=1,
                steam_bit=0,
            )},
            wiki={},
            huiji={},
            generated_at="2026-09-10T00:00:00+00:00",
        )

        item = payload["achievements"][0]
        self.assertEqual(item["steam"]["description_en"], "Complete the first chapter.")
        self.assertEqual(item["display"]["description_en"], "Complete the first chapter.")

    def test_character_unlock_relation_uses_retained_steam_metadata(self):
        payload = merge_catalog(
            steam={1: source(
                1,
                "steam_schema",
                steam_name="1",
                name_en="Magdalene",
                steam_description_en="Unlocked a new character.",
                steam_group=1,
                steam_bit=0,
            )},
            wiki={1: source(
                1,
                "wiki_gg",
                unlock_condition_en="Have 7 or more Red Heart Containers at one time",
            )},
            huiji={},
            generated_at="2026-09-10T00:00:00+00:00",
        )

        item = payload["achievements"][0]
        self.assertEqual(
            item["characters"],
            [{"id": "magdalene", "relation": "unlocks_character"}],
        )
        self.assertIn("character", item["categories"])

    def test_starting_item_relation_coexists_with_required_character(self):
        payload = merge_catalog(
            steam={29: source(
                29,
                "steam_schema",
                steam_name="29",
                name_en="The D6",
                steam_description_en="Isaac now holds the D6!",
                steam_group=1,
                steam_bit=28,
            )},
            wiki={29: source(
                29,
                "wiki_gg",
                unlock_condition_en="Defeat Isaac as ???",
            )},
            huiji={},
            generated_at="2026-09-10T00:00:00+00:00",
        )

        self.assertEqual(
            payload["achievements"][0]["characters"],
            [
                {"id": "isaac", "relation": "starting_item_for_character"},
                {"id": "blue_baby", "relation": "required_character"},
            ],
        )

    def test_character_unlock_relations_cover_prior_named_mappings(self):
        cases = (
            (2, "Cain", "cain"),
            (32, "???", "blue_baby"),
            (390, "The Forgotten", "forgotten"),
        )
        for achievement_id, name, character_id in cases:
            with self.subTest(achievement_id=achievement_id):
                payload = merge_catalog(
                    steam={achievement_id: source(
                        achievement_id,
                        "steam_schema",
                        steam_name=str(achievement_id),
                        name_en=name,
                        steam_description_en="Unlocked a new character.",
                        steam_group=1,
                        steam_bit=achievement_id - 1,
                    )},
                    wiki={},
                    huiji={},
                    generated_at="2026-09-10T00:00:00+00:00",
                )

                self.assertEqual(
                    payload["achievements"][0]["characters"],
                    [{"id": character_id, "relation": "unlocks_character"}],
                )


if __name__ == "__main__":
    unittest.main()
