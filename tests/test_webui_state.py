"""Tests for AppState and supporting components."""

import tempfile
import unittest
from pathlib import Path

from webui import settings as settings_mod
from webui.state import AppState, DiskCache, HistoryTracker, IndexEntry, SearchIndex


class DiskCacheTest(unittest.TestCase):
    def test_disk_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DiskCache(tmpdir)
            cache.write("sample", {"hello": "world"})
            loaded = cache.read("sample")
            self.assertEqual(loaded, {"hello": "world"})

    def test_disk_cache_disabled(self):
        cache = DiskCache(None)
        cache.write("sample", {"ignored": True})
        self.assertIsNone(cache.read("sample"))


class HistoryTrackerTest(unittest.TestCase):
    def test_history_records_when_enabled(self):
        tracker = HistoryTracker(enabled=True, limit=2)
        tracker.record("inspect", "obj1")
        tracker.record("inspect", "obj2")
        tracker.record("inspect", "obj3")
        snapshot = tracker.snapshot()
        entries = snapshot["entries"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["query"], "obj3")
        self.assertEqual(entries[1]["query"], "obj2")

    def test_history_disabled_noop(self):
        tracker = HistoryTracker(enabled=False)
        tracker.record("inspect", "obj")
        self.assertEqual(tracker.snapshot()["entries"], [])


class SearchIndexTest(unittest.TestCase):
    def test_status_reports_keys(self):
        idx = SearchIndex()
        idx.set(
            "asa:sample",
            IndexEntry(
                key="asa:sample",
                vendor="asa",
                os_tag="ASA",
                version="auto",
                built_at=0.0,
                src_mtime=1.0,
                src_size=10,
                index={"objects": []},
            ),
        )
        status = idx.status()
        self.assertEqual(status["entries"], 1)
        self.assertEqual(status["keys"], ["asa:sample"])


class AppStateTest(unittest.TestCase):
    def test_app_state_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = settings_mod.load_settings(
                Path(tmpdir) / "settings.json",
                env={"ACLINSPECTOR_CONFIGS_CISCO": str(Path(tmpdir) / "configs" / "asa")},
            )
            state = AppState.create(settings)
            self.assertTrue(state.themes)
            self.assertIsNotNone(state.disk_cache)
            self.assertIsNotNone(state.search_index)
            self.assertIsNotNone(state.index_manager)
            self.assertIsInstance(state.font_css, str)
            self.assertIsInstance(state.font_files, list)

    def test_app_state_missing_theme_dir_falls_back(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = settings_mod.load_settings(
                Path(tmpdir) / "settings.json",
                env={
                    "ACLINSPECTOR_CONFIGS_CISCO": str(Path(tmpdir) / "configs" / "asa"),
                    "ACLINSPECTOR_THEME_DIR": str(Path(tmpdir) / "nonexistent" / "themes"),
                },
            )
            state = AppState.create(settings)
            names = {theme["name"] for theme in state.themes}
            self.assertIn("Builtin Dark", names)
            self.assertIn("Builtin Light", names)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
