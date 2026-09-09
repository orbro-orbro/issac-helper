import unittest

from app.wiki_catalog import parse_achievement_table


class WikiCatalogTests(unittest.TestCase):
    def test_extracts_id_name_description_and_unlock_text(self):
        html = """
        <table class="wikitable striped"><tbody>
          <tr><th>Name</th><th>ID</th><th>Icon</th><th>Description</th><th>Unlock</th></tr>
          <tr>
            <td><a>Meat Cleaver</a></td><td>440</td><td><img alt=""></td>
            <td>Complete the Corpse with Isaac.</td>
            <td>Defeat <a>Mother</a> as <a>Isaac</a></td>
          </tr>
        </tbody></table>
        """

        result = parse_achievement_table(html)

        self.assertEqual(result, {440: {
            "id": 440,
            "name_en": "Meat Cleaver",
            "steam_description": "Complete the Corpse with Isaac.",
            "unlock_condition_en": "Defeat Mother as Isaac",
            "url": "https://bindingofisaacrebirth.wiki.gg/wiki/Achievement",
        }})

    def test_ignores_other_tables_and_non_numeric_rows(self):
        html = """
        <table><tr><td>Not achievements</td></tr></table>
        <table class="wikitable"><tr><th>Name</th><th>ID</th><th>Icon</th><th>Description</th><th>Unlock</th></tr>
        <tr><td>Header-like</td><td>N/A</td><td></td><td>None</td><td>None</td></tr></table>
        """

        self.assertEqual(parse_achievement_table(html), {})


if __name__ == "__main__":
    unittest.main()
