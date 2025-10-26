"""Tests for theme loading helpers."""

import plistlib
import tempfile
import unittest
from pathlib import Path

from webui.themes import DEFAULT_THEMES, load_iterm_theme, load_themes


class ThemeLoaderTest(unittest.TestCase):
    def test_builtin_themes_present_when_directory_missing(self):
        themes = load_themes("/nonexistent")
        names = [t["name"] for t in themes]
        for default in DEFAULT_THEMES:
            self.assertIn(default["name"], names)

    def test_load_iterm_theme_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "Background Color": {"Red Component": 0.1, "Green Component": 0.1, "Blue Component": 0.1},
                "Foreground Color": {"Red Component": 0.9, "Green Component": 0.9, "Blue Component": 0.9},
                "Ansi 4 Color": {"Red Component": 0.2, "Green Component": 0.4, "Blue Component": 0.9},
            }
            path = Path(tmpdir) / "Test.itermcolors"
            with path.open("wb") as handle:
                plistlib.dump(data, handle)

            theme = load_iterm_theme(str(path))
            self.assertIsNotNone(theme)
            self.assertEqual(theme["name"], "Test")
            themes = load_themes(tmpdir)
            self.assertTrue(any(t["name"] == "Test" for t in themes))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
