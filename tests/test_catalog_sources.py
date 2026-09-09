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
