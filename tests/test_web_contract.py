from html.parser import HTMLParser
from pathlib import Path
import unittest


WEB_ROOT = Path(__file__).resolve().parent.parent / "web"


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        if data.strip():
            self.text.append(data.strip())


class WebContractTests(unittest.TestCase):
    def setUp(self):
        parser = DocumentParser()
        parser.feed((WEB_ROOT / "index.html").read_text(encoding="utf-8"))
        self.parser = parser

    def attrs_for(self, tag: str):
        return [attrs for found, attrs in self.parser.tags if found == tag]

    def test_has_keyboard_skip_link_and_semantic_landmarks(self):
        links = self.attrs_for("a")
        self.assertTrue(any(item.get("href") == "#main" for item in links))
        self.assertTrue(self.attrs_for("header"))
        self.assertTrue(self.attrs_for("nav"))
        self.assertTrue(any(item.get("id") == "main" for item in self.attrs_for("main")))

    def test_exposes_all_primary_views_and_update_action(self):
        buttons = self.attrs_for("button")
        views = {item["data-view"] for item in buttons if item.get("data-view")}
        self.assertEqual(views, {"characters", "categories", "all"})
        self.assertTrue(any(item.get("id") == "open-update" for item in buttons))

    def test_update_dialog_uses_labeled_native_controls(self):
        self.assertTrue(any(item.get("id") == "update-dialog" for item in self.attrs_for("dialog")))
        selects = {item.get("id") for item in self.attrs_for("select")}
        self.assertEqual(selects, {"account-select", "slot-select"})
        labels = {item.get("for") for item in self.attrs_for("label")}
        self.assertTrue({"account-select", "slot-select"}.issubset(labels))

    def test_loads_local_assets_and_has_no_script_guidance(self):
        self.assertTrue(any(item.get("href") == "styles.css" for item in self.attrs_for("link")))
        self.assertTrue(any(item.get("src") == "app.js" for item in self.attrs_for("script")))
        self.assertTrue(self.attrs_for("noscript"))
        self.assertIn("需要启用 JavaScript", " ".join(self.parser.text))

    def test_progress_track_establishes_block_layout(self):
        stylesheet = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
        rule = stylesheet.split(".progress-track {", 1)[1].split("}", 1)[0]

        self.assertIn("display: block", rule)

    def test_achievement_rows_prefer_nested_localized_metadata(self):
        script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

        self.assertIn("item.display.name_zh", script)
        self.assertIn("item.display.name_en", script)
        self.assertIn("item.display.unlock_condition_zh", script)
        self.assertIn("item.display.unlock_condition_en", script)
        self.assertIn("item.steam.description_en", script)

    def test_exposes_separate_catalog_update_and_details(self):
        buttons = self.attrs_for("button")
        self.assertTrue(any(item.get("id") == "catalog-update" for item in buttons))
        self.assertTrue(any(
            item.get("id") == "achievement-details"
            for item in self.attrs_for("dialog")
        ))
        self.assertTrue(any(
            item.get("data-close-achievement") is not None
            for item in buttons
        ))
        script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/catalog/status", script)
        self.assertIn("/api/catalog/update", script)
        self.assertIn('body: "{}"', script)

    def test_catalog_update_reports_full_summary_and_structured_errors(self):
        script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

        self.assertIn("Array.isArray(payload.errors)", script)
        self.assertIn("更新时间", script)
        self.assertIn("字段完整度", script)
        self.assertIn("提醒", script)
        self.assertIn("来源失败", script)

    def test_achievement_rows_show_secondary_english_name_and_character_tags(self):
        script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
        stylesheet = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn("achievement-name-en", script)
        self.assertIn("item.characters", script)
        self.assertIn("tag-character", script)
        self.assertIn(".achievement-name-en", stylesheet)

    def test_achievement_copy_wraps_on_narrow_screens(self):
        stylesheet = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".achievement-row > div { min-width: 0;", stylesheet)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", stylesheet)
        self.assertIn("overflow-wrap: anywhere", stylesheet)

    def test_missing_snapshot_has_explicit_first_update_state(self):
        script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

        self.assertIn("尚未读取进度", script)
        self.assertIn("data-open-update", script)

    def test_character_views_offer_sorting_and_status_filters(self):
        script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="character-order"', script)
        self.assertIn('id="character-status-filter"', script)
        self.assertIn('id="relation-filter"', script)


if __name__ == "__main__":
    unittest.main()
