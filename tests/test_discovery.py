from pathlib import Path
import tempfile
import unittest

from app.discovery import DiscoveryError, discover_accounts, resolve_selection


class DiscoveryTests(unittest.TestCase):
    def test_discovers_numeric_accounts_and_cloud_save_slots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "steam"
            remote = root / "userdata" / "12345" / "250900" / "remote"
            remote.mkdir(parents=True)
            (remote / "rep+persistentgamedata1.dat").write_bytes(b"slot1")
            (remote / "rep+persistentgamedata3.dat").write_bytes(b"slot3")
            (root / "userdata" / "not-an-account" / "250900").mkdir(parents=True)
            stats = root / "appcache" / "stats"
            stats.mkdir(parents=True)
            (stats / "UserGameStats_12345_250900.bin").write_bytes(b"cache")
            (stats / "UserGameStatsSchema_250900.bin").write_bytes(b"schema")

            accounts = discover_accounts([root])

            self.assertEqual([account.id for account in accounts], ["12345"])
            self.assertEqual([slot.number for slot in accounts[0].slots], [1, 3])
            self.assertEqual(accounts[0].stats_path.name, "UserGameStats_12345_250900.bin")

    def test_resolve_selection_rejects_unknown_account(self):
        with self.assertRaisesRegex(DiscoveryError, "unknown Steam account"):
            resolve_selection("999", 1, [])

    def test_resolve_selection_rejects_missing_slot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "steam"
            (root / "userdata" / "123" / "250900" / "remote").mkdir(parents=True)
            account = discover_accounts([root])[0]

            with self.assertRaisesRegex(DiscoveryError, "slot 2 is not available"):
                resolve_selection("123", 2, [account])


if __name__ == "__main__":
    unittest.main()
