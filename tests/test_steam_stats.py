from datetime import timezone
import unittest

from app.readers.steam_stats import (
    AchievementDefinition,
    SteamStatsError,
    extract_schema,
    extract_unlocked,
)


def bit(achievement_id: int, name: str = "Achievement", desc: str = "Do a thing"):
    return {
        "name": str(achievement_id),
        "display": {
            "name": {"english": name},
            "desc": {"english": desc},
            "icon": "icon.jpg",
            "icon_gray": "locked.jpg",
        },
    }


class SteamStatsTests(unittest.TestCase):
    def test_extracts_and_sorts_schema_bits(self):
        root = {
            "250900": {
                "stats": {
                    "2": {"bits": {"0": bit(33, "Third")}},
                    "1": {"bits": {"31": bit(99, "Last"), "0": bit(1, "First")}},
                }
            }
        }

        definitions = extract_schema(root)

        self.assertEqual([(item.group, item.bit, item.id) for item in definitions], [
            (1, 0, 1), (1, 31, 99), (2, 0, 33)
        ])
        self.assertEqual(definitions[0].name, "First")
        self.assertEqual(definitions[0].icon, "icon.jpg")

    def test_maps_signed_cache_mask_to_schema_ids(self):
        definitions = [
            AchievementDefinition(1, 0, 1, "First", "", "", ""),
            AchievementDefinition(1, 31, 99, "Last", "", "", ""),
        ]
        root = {"cache": {"1": {"data": -2147483647}}}

        unlocked = extract_unlocked(root, definitions)

        self.assertEqual(set(unlocked), {1, 99})

    def test_uses_utc_achievement_time(self):
        definitions = [AchievementDefinition(1, 2, 3, "Third", "", "", "")]
        root = {"cache": {"1": {"data": 4, "AchievementTimes": {"2": 1_700_000_000}}}}

        unlocked = extract_unlocked(root, definitions)

        self.assertEqual(unlocked[3].tzinfo, timezone.utc)
        self.assertEqual(unlocked[3].timestamp(), 1_700_000_000)

    def test_rejects_schema_without_numeric_achievements(self):
        with self.assertRaisesRegex(SteamStatsError, "no achievement definitions"):
            extract_schema({"250900": {"stats": {"crc": 1}}})


if __name__ == "__main__":
    unittest.main()
