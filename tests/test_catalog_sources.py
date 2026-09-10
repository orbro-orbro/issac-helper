import unittest
from io import BytesIO
import json
from unittest.mock import patch
from urllib.error import HTTPError

from app.catalog_types import SourceAchievement
from app.huiji_catalog import (
    HUIJI_RAW_URL,
    HUIJI_READER_URL,
    fetch_huiji_achievements,
    parse_huiji_name_lookup,
    parse_huiji_tabx,
)
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
                {"name": "id"}, {"name": "NameZH"}, {"name": "NameEN"},
                {"name": "UnlockReq"}, {"name": "bonus"}, {"name": "source"},
            ]},
            "data": [[20, "圣遗物", "The Relic", "用{{chara|抹大拉}}获得以撒通关标记。", "{{item|ID=c98}}", "重生"]],
        }
        item = parse_huiji_tabx(payload, "2026-09-09T00:00:00+00:00")[20]
        self.assertEqual(item.values["name_zh"], "圣遗物")
        self.assertEqual(item.values["unlock_condition_zh"], "用抹大拉获得以撒通关标记。")
        self.assertEqual(item.values["reward_zh"], "")
        self.assertEqual(item.values["dlc"], "rebirth")

    def test_huiji_fetch_falls_back_to_reader_when_direct_access_is_forbidden(self):
        payload = '''{"schema":{"fields":[
            {"name":"id"},{"name":"NameZH"},{"name":"UnlockReq"}
        ]},"data":[[1,"抹大拉","同时拥有七个心之容器。"]]}'''.encode("utf-8")
        reader_response = BytesIO(
            b"Title: \n\nURL Source: "
            + HUIJI_RAW_URL.encode("utf-8")
            + b"\n\nMarkdown Content:\n"
            + payload
        )
        empty_lookup = json.dumps({
            "schema": {"fields": [
                {"name": "page"}, {"name": "namezh"},
            ]},
            "data": [],
        }).encode("utf-8")

        with patch(
            "app.huiji_catalog.urlopen",
            side_effect=[
                HTTPError(HUIJI_RAW_URL, 403, "Forbidden", None, None),
                reader_response,
                BytesIO(empty_lookup),
                BytesIO(empty_lookup),
                BytesIO(empty_lookup),
            ],
        ) as mocked_open:
            item = fetch_huiji_achievements()[1]

        self.assertEqual(item.values["name_zh"], "\u62b9\u5927\u62c9")
        self.assertEqual(
            item.values["unlock_condition_zh"],
            "\u540c\u65f6\u62e5\u6709\u4e03\u4e2a\u5fc3\u4e4b\u5bb9\u5668\u3002",
        )
        self.assertEqual(
            [call.args[0].full_url for call in mocked_open.call_args_list],
            [
                HUIJI_RAW_URL,
                HUIJI_READER_URL,
                "https://isaac.huijiwiki.com/wiki/Data:Entity.tabx?action=raw",
                "https://isaac.huijiwiki.com/wiki/Data:Item.tabx?action=raw",
                "https://isaac.huijiwiki.com/wiki/Data:Challenge.tabx?action=raw",
            ],
        )

    def test_huiji_parser_fills_the_verified_missing_condition_for_1000000_percent(self):
        payload = {
            "schema": {"fields": [
                {"name": "id"}, {"name": "NameZH"}, {"name": "UnlockReq"},
            ]},
            "data": [[339, "1000000%", ""]],
        }

        item = parse_huiji_tabx(payload)[339]

        self.assertEqual(
            item.values["unlock_condition_zh"],
            "解锁除本成就以外的其他任意402个成就。",
        )

    def test_huiji_name_lookup_uses_the_template_identity_from_each_page(self):
        payload = {
            "schema": {"fields": [
                {"name": "namezh"}, {"name": "page"},
            ]},
            "data": [
                ["撒但", "实体/84#84.0.0"],
                ["钥匙碎片1", "c238"],
            ],
        }

        self.assertEqual(
            parse_huiji_name_lookup(payload),
            {"84.0.0": "撒但", "c238": "钥匙碎片1"},
        )

    def test_huiji_parser_resolves_named_entity_and_item_templates(self):
        payload = {
            "schema": {"fields": [
                {"name": "id"}, {"name": "UnlockReq"},
            ]},
            "data": [[58, "击败{{entity|ID=84.0.0}}、拥有{{item|ID=c238}}并通过{{挑战|13}}。"]],
        }

        item = parse_huiji_tabx(
            payload,
            template_names={
                "entity": {"84.0.0": "撒但"},
                "item": {"c238": "钥匙碎片1"},
                "挑战": {"13": "挑战#13：豆子！"},
            },
        )[58]

        self.assertEqual(
            item.values["unlock_condition_zh"],
            "击败撒但、拥有钥匙碎片1并通过挑战#13：豆子！。",
        )

    def test_huiji_fetch_uses_entity_and_item_tables_for_template_names(self):
        achievement_payload = {
            "schema": {"fields": [
                {"name": "id"}, {"name": "UnlockReq"},
            ]},
            "data": [[58, "击败{{entity|ID=84.0.0}}、拥有{{item|ID=c238}}并通过{{挑战|13}}。"]],
        }
        entity_payload = {
            "schema": {"fields": [
                {"name": "page"}, {"name": "namezh"},
            ]},
            "data": [["实体/84#84.0.0", "撒但"]],
        }
        item_payload = {
            "schema": {"fields": [
                {"name": "page"}, {"name": "namezh"},
            ]},
            "data": [["c238", "钥匙碎片1"]],
        }
        challenge_payload = {
            "schema": {"fields": [
                {"name": "page"}, {"name": "namezh"},
            ]},
            "data": [["挑战/13", "豆子！"]],
        }
        responses = [
            BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            for payload in (
                achievement_payload,
                entity_payload,
                item_payload,
                challenge_payload,
            )
        ]

        with patch("app.huiji_catalog.urlopen", side_effect=responses):
            item = fetch_huiji_achievements()[58]

        self.assertEqual(
            item.values["unlock_condition_zh"],
            "击败撒但、拥有钥匙碎片1并通过挑战#13：豆子！。",
        )

    def test_huiji_parser_keeps_the_number_for_the_unnamed_challenge_45(self):
        payload = {
            "schema": {"fields": [
                {"name": "id"}, {"name": "UnlockReq"},
            ]},
            "data": [[538, "通过{{挑战|45}}。"]],
        }

        item = parse_huiji_tabx(payload, template_names={"挑战": {}})[538]

        self.assertEqual(item.values["unlock_condition_zh"], "通过挑战#45。")
