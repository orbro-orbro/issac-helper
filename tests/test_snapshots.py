from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app.discovery import AccountInfo, Selection, SlotInfo
from app.readers.steam_stats import AchievementDefinition
from app.snapshots import (
    SnapshotError,
    _read_stable,
    build_snapshot,
    load_snapshot,
    merge_progress,
    snapshot_path,
    write_snapshot_atomic,
)


class SnapshotTests(unittest.TestCase):
    def test_build_snapshot_uses_project_catalog_by_default_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            schema_path = root / "schema.bin"
            stats_path = root / "stats.bin"
            save_path = root / "rep+persistentgamedata1.dat"
            schema_path.write_bytes(b"schema")
            stats_path.write_bytes(b"stats")
            save_path.write_bytes(b"unsupported save")
            slot = SlotInfo(1, save_path, datetime.now(tz=timezone.utc), save_path.stat().st_size)
            account = AccountInfo(
                id="123",
                steam_root=root,
                stats_path=stats_path,
                schema_path=schema_path,
                game_dir=root / "game",
                save_dir=root,
                slots=(slot,),
            )
            loaded_paths = []

            def load_test_catalog(path):
                loaded_paths.append(Path(path))
                return {"achievements": [], "diagnostics": {}}

            explicit_path = root / "custom-catalog.json"
            with (
                mock.patch("app.snapshots.parse_binary_keyvalues", return_value={}),
                mock.patch("app.snapshots.extract_schema", return_value=[]),
                mock.patch("app.snapshots.extract_unlocked", return_value={}),
                mock.patch("app.snapshots.load_catalog", side_effect=load_test_catalog),
            ):
                selection = Selection(account, slot)
                build_snapshot(selection, root / "private-default")
                build_snapshot(
                    selection,
                    root / "private-explicit",
                    catalog_path=explicit_path,
                )

            project_root = Path(__file__).resolve().parents[1]
            self.assertEqual(loaded_paths, [
                project_root / "data" / "catalog" / "achievements.json",
                explicit_path,
            ])

    def test_secret_parse_failure_keeps_verified_secret_progress_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            schema_path = root / "schema.bin"
            stats_path = root / "stats.bin"
            save_path = root / "rep+persistentgamedata1.dat"
            schema_path.write_bytes(b"schema")
            stats_path.write_bytes(b"stats")
            save_path.write_bytes(b"unsupported save")
            catalog_path = root / "achievements.json"
            catalog = {
                "schema_version": 2,
                "generated_at": "2026-09-09T00:00:00+00:00",
                "achievement_count": 1,
                "achievements": [{
                    "id": 1,
                    "steam": {"group": 7, "bit": 2},
                    "secret": {"id": 1, "status": "verified"},
                }],
                "diagnostics": {},
            }
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            modified_at = datetime(2026, 9, 10, tzinfo=timezone.utc)
            slot = SlotInfo(1, save_path, modified_at, save_path.stat().st_size)
            account = AccountInfo(
                id="123",
                steam_root=root,
                stats_path=stats_path,
                schema_path=schema_path,
                game_dir=root / "game",
                save_dir=root,
                slots=(slot,),
            )
            definition = AchievementDefinition(
                7, 2, 1, "Achievement", "Description", "", ""
            )

            with (
                mock.patch("app.snapshots.parse_binary_keyvalues", return_value={}),
                mock.patch("app.snapshots.extract_schema", return_value=[definition]),
                mock.patch(
                    "app.snapshots.extract_unlocked",
                    return_value={1: modified_at},
                ),
            ):
                payload = build_snapshot(
                    Selection(account, slot),
                    root / "profiles",
                    catalog_path=catalog_path,
                )

            progress = payload["achievements"][0]["progress"]
            self.assertTrue(progress["steam_unlocked"])
            self.assertIsNone(progress["secret_unlocked"])
            self.assertFalse(progress["sync_warning"])
            self.assertIsNotNone(payload["game_secrets"]["error"])
            self.assertIsNone(payload["summary"]["game_secrets_unlocked"])
            self.assertEqual(payload["sync_differences"], [])
            self.assertEqual(json.loads(catalog_path.read_text(encoding="utf-8")), catalog)

    def test_merge_keeps_steam_and_secret_states_separate(self):
        catalog = [
            {
                "id": 101,
                "steam": {"group": 3, "bit": 4},
                "secret": {"id": 1, "status": "verified"},
            },
            {
                "id": 102,
                "steam": {"group": 3, "bit": 5},
                "secret": {"id": 2, "status": "verified"},
            },
            {
                "id": 103,
                "steam": {"group": 4, "bit": 0},
                "secret": {"id": 3, "status": "verified"},
            },
        ]
        unlocked_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        unlocked = {(3, 4): unlocked_at, (3, 5): None}

        items, summary, differences = merge_progress(catalog, unlocked, {2, 3})

        progress = [item["progress"] for item in items]
        self.assertEqual([item["steam_unlocked"] for item in progress], [True, True, False])
        self.assertEqual([item["secret_unlocked"] for item in progress], [False, True, True])
        self.assertEqual(progress[0]["unlocked_at"], unlocked_at.isoformat())
        self.assertEqual([item["sync_warning"] for item in progress], [True, False, True])
        self.assertEqual(summary, {
            "total": 3,
            "steam_unlocked": 2,
            "game_secrets_unlocked": 2,
            "sync_difference_count": 2,
        })
        self.assertEqual(differences, [
            {"id": 101, "steam_unlocked": True, "secret_unlocked": False},
            {"id": 103, "steam_unlocked": False, "secret_unlocked": True},
        ])
        self.assertNotIn("progress", catalog[0])

    def test_merge_does_not_guess_secret_mapping(self):
        catalog = [{
            "id": 1,
            "steam": {"group": 1, "bit": 0},
            "secret": {"id": 1, "status": "unverified"},
        }]

        items, summary, differences = merge_progress(catalog, {(1, 0): None}, {1})

        self.assertTrue(items[0]["progress"]["steam_unlocked"])
        self.assertIsNone(items[0]["progress"]["secret_unlocked"])
        self.assertFalse(items[0]["progress"]["sync_warning"])
        self.assertEqual(summary["sync_difference_count"], 0)
        self.assertEqual(differences, [])

    def test_atomic_write_preserves_previous_file_when_serialization_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "current.json"
            target.write_text('{"stable": true}', encoding="utf-8")

            with self.assertRaises(TypeError):
                write_snapshot_atomic(target, {"bad": object()})

            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"stable": True})
            self.assertEqual(list(target.parent.glob("*.tmp")), [])

    def test_snapshot_path_rejects_traversal_and_invalid_slots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                snapshot_path(root, "../other", 1)
            with self.assertRaises(ValueError):
                snapshot_path(root, "123", 4)

    def test_load_snapshot_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertIsNone(load_snapshot(Path(temp), "123", 1))

    def test_stable_read_rejects_a_source_that_changes_during_read(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.bin"
            source.write_bytes(b"before")

            def mutate():
                data = source.read_bytes()
                source.write_bytes(b"changed-size")
                return data

            original_read = Path.read_bytes

            def mutate_during_read(path):
                data = original_read(path)
                if path == source:
                    source.write_bytes(b"changed-size")
                return data

            with mock.patch.object(Path, "read_bytes", new=mutate_during_read):
                with self.assertRaisesRegex(SnapshotError, "changed while reading"):
                    _read_stable(source)


if __name__ == "__main__":
    unittest.main()
