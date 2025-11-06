"""Tests for theme loading helpers."""

import plistlib
import tempfile
import unittest
from pathlib import Path

from webui.themes import (
    DEFAULT_THEMES,
    build_singularity_palette,
    load_iterm_theme,
    load_themes,
)


class ThemeLoaderTest(unittest.TestCase):
    def test_builtin_themes_present_when_directory_missing(self):
        with self.assertLogs("webui.themes", level="INFO") as logs:
            themes = load_themes("/nonexistent")
        names = [t["name"] for t in themes]
        for default in DEFAULT_THEMES:
            self.assertIn(default["name"], names)
        self.assertTrue(
            any("not found" in message.lower() for message in logs.output),
            msg="Expected missing theme directory to emit a log message.",
        )

    def test_empty_directory_still_returns_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            themes = load_themes(tmpdir)
            names = {t["name"] for t in themes}
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


class SingularityPaletteTest(unittest.TestCase):
    def test_palette_contains_expected_tokens(self):
        palette = build_singularity_palette(DEFAULT_THEMES[0])
        required = {
            "bg-base",
            "bg-surface",
            "bg-overlay",
            "accent",
            "accent-contrast",
            "highlight",
            "chip-bg",
            "shadow-color",
            "focus-ring",
        }
        for token in required:
            self.assertIn(token, palette)
        self.assertTrue(palette["bg-base"].startswith("#"))
        self.assertTrue(palette["border"].startswith("rgba"))
        self.assertTrue(palette["highlight"].startswith("rgba"))

    def test_light_and_dark_palettes_differ(self):
        dark_palette = build_singularity_palette(DEFAULT_THEMES[0])
        light_palette = build_singularity_palette(DEFAULT_THEMES[1])
        self.assertNotEqual(dark_palette["bg-base"], light_palette["bg-base"])
        self.assertNotEqual(dark_palette["accent"], light_palette["accent"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
