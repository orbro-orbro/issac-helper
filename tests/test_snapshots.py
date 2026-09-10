from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app.snapshots import (
    SnapshotError,
    _read_stable,
    load_snapshot,
    merge_progress,
    snapshot_path,
    write_snapshot_atomic,
)


class SnapshotTests(unittest.TestCase):
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
