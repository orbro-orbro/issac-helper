from pathlib import Path
import tempfile
import unittest

from app.discovery import discover_accounts, resolve_selection
from app.readers.isaac_save import read_secrets
from app.readers.steam_stats import read_schema, read_unlocked
from app.snapshots import build_snapshot


class InstalledDataSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.accounts = discover_accounts()
        if not cls.accounts:
            raise unittest.SkipTest("The Binding of Isaac Steam data is not installed")
        cls.account = next(
            (item for item in cls.accounts if item.schema_path.is_file() and item.stats_path.is_file()),
            None,
        )
        if cls.account is None:
            raise unittest.SkipTest("Steam schema/cache files are unavailable")

    def test_installed_schema_and_cache_are_internally_consistent(self):
        definitions = read_schema(self.account.schema_path)
        unlocked = read_unlocked(self.account.stats_path, definitions)

        self.assertGreaterEqual(len(definitions), 600)
        self.assertEqual(len({item.id for item in definitions}), len(definitions))
        self.assertTrue(set(unlocked).issubset({item.id for item in definitions}))

    def test_installed_save_has_plausible_secret_table(self):
        if not self.account.slots:
            self.skipTest("No Repentance+ save slots are available")
        latest = max(self.account.slots, key=lambda item: item.modified_at)

        secrets = read_secrets(latest.save_path)

        self.assertGreaterEqual(secrets.secret_count, 600)
        self.assertTrue(all(1 <= item <= secrets.secret_count for item in secrets.unlocked_ids))

    def test_builds_private_snapshot_in_temporary_directory(self):
        if not self.account.slots:
            self.skipTest("No Repentance+ save slots are available")
        latest = max(self.account.slots, key=lambda item: item.modified_at)
        selection = resolve_selection(self.account.id, latest.number, self.accounts)
        with tempfile.TemporaryDirectory() as temp:
            snapshot = build_snapshot(selection, Path(temp))

            self.assertEqual(snapshot["summary"]["total"], len(snapshot["achievements"]))
            self.assertEqual(snapshot["steam_account_id"], self.account.id)
            self.assertEqual(snapshot["slot"], latest.number)


if __name__ == "__main__":
    unittest.main()
