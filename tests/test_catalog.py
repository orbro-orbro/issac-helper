import unittest

from app.catalog import CATEGORY_DEFINITIONS, CHARACTERS, build_catalog
from app.readers.steam_stats import AchievementDefinition


def achievement(
    achievement_id: int,
    name: str,
    description: str,
) -> AchievementDefinition:
    return AchievementDefinition(1, achievement_id - 1, achievement_id, name, description, "", "")


class CatalogTests(unittest.TestCase):
    def test_contains_all_normal_and_tainted_characters(self):
        self.assertEqual(len(CHARACTERS), 34)
        self.assertEqual(len({item["id"] for item in CHARACTERS}), 34)

    def test_character_condition_has_explicit_required_relation(self):
        item = build_catalog([
            achievement(1, "The Chest", "Complete the Chest with Isaac.")
        ])[0]

        self.assertIn("character", item["categories"])
        self.assertEqual(item["character_relations"], [
            {"character_id": "isaac", "type": "required_character"}
        ])

    def test_wiki_unlock_condition_supplies_character_relation(self):
        definition = achievement(20, "A Cross", "Unlocked a new item.")
        overrides = {20: {
            "name_en": "A Cross",
            "unlock_condition_en": "Defeat Isaac as Magdalene",
            "url": "https://bindingofisaacrebirth.wiki.gg/wiki/Achievement",
        }}

        item = build_catalog([definition], overrides=overrides)[0]

        self.assertEqual(item["unlock_condition_en"], "Defeat Isaac as Magdalene")
        self.assertIn(
            {"character_id": "magdalene", "type": "required_character"},
            item["character_relations"],
        )

    def test_character_unlock_uses_achievement_name(self):
        item = build_catalog([
            achievement(1, "Magdalene", "Unlocked a new character.")
        ])[0]

        self.assertEqual(item["character_relations"], [
            {"character_id": "magdalene", "type": "unlocks_character"}
        ])

    def test_classifies_each_supported_unlock_method(self):
        items = build_catalog([
            achievement(1, "Challenge", "Complete challenge #3."),
            achievement(2, "Boss", "Defeat Mother."),
            achievement(3, "Collector", "Collect 100 items."),
            achievement(4, "Special", "Beat the chapter without taking damage."),
            achievement(5, "Daily", "Win 5 daily challenges."),
            achievement(6, "Dead God", "Unlock all achievements."),
        ])

        categories = [set(item["categories"]) for item in items]
        self.assertIn("challenge", categories[0])
        self.assertIn("route_boss", categories[1])
        self.assertIn("collection", categories[2])
        self.assertIn("special_run", categories[3])
        self.assertIn("daily_online", categories[4])
        self.assertIn("milestone", categories[5])

    def test_every_achievement_has_category_and_source(self):
        items = build_catalog([
            achievement(8, "A Secret", "Something mysterious happened.")
        ])

        self.assertEqual(items[0]["categories"], ["other"])
        self.assertEqual(items[0]["sources"][0]["type"], "steam_schema")
        self.assertEqual(set(CATEGORY_DEFINITIONS), {
            "character", "challenge", "route_boss", "collection",
            "special_run", "daily_online", "milestone", "other"
        })

    def test_classifies_representative_real_unlock_conditions(self):
        overrides = {
            30: {"unlock_condition_en": "Die 100 times"},
            322: {"unlock_condition_en": "Get a 3-win streak"},
            350: {"unlock_condition_en": "Destroy 500 rocks"},
        }
        items = build_catalog(
            [
                achievement(30, "The Scissors", "Unlocked a new item."),
                achievement(322, "Hat trick!", "Unlocked a new item."),
                achievement(350, "Mystery Gift", "Unlocked a new item."),
            ],
            overrides=overrides,
        )

        self.assertIn("collection", items[0]["categories"])
        self.assertIn("special_run", items[1]["categories"])
        self.assertIn("collection", items[2]["categories"])


if __name__ == "__main__":
    unittest.main()
