"""Unit tests for TUI settings state management."""

import unittest
import tempfile
import json
import os
from pathlib import Path


class TestTUISettings(unittest.TestCase):
    """Test TUI settings persistence and management."""

    def setUp(self):
        """Create temporary config directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "test-settings.json")

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_default_settings_created(self):
        """Test that default settings are created when no file exists."""
        from tui.state import TUISettings

        settings = TUISettings(config_path=self.config_path)

        # Should have all default categories
        self.assertIn("display", settings.settings)
        self.assertIn("search", settings.settings)
        self.assertIn("config", settings.settings)
        self.assertIn("advanced", settings.settings)

        # Check default values
        self.assertEqual(settings.get("display", "theme"), "textual-dark")
        self.assertEqual(settings.get("search", "mode"), "fuzzy")
        self.assertEqual(settings.get("display", "results_per_page"), 20)

    def test_get_set_setting(self):
        """Test getting and setting individual settings."""
        from tui.state import TUISettings

        settings = TUISettings(config_path=self.config_path)

        # Set a value
        settings.set("display", "theme", "textual-light")
        self.assertEqual(settings.get("display", "theme"), "textual-light")

        # Set in new category
        settings.set("custom", "key", "value")
        self.assertEqual(settings.get("custom", "key"), "value")

    def test_save_and_load(self):
        """Test saving and loading settings from disk."""
        from tui.state import TUISettings

        # Create and modify settings
        settings1 = TUISettings(config_path=self.config_path)
        settings1.set("display", "theme", "textual-light")
        settings1.set("search", "max_results", 100)

        # Save
        result = settings1.save()
        self.assertTrue(result)
        self.assertTrue(os.path.exists(self.config_path))

        # Load in new instance
        settings2 = TUISettings(config_path=self.config_path)
        self.assertEqual(settings2.get("display", "theme"), "textual-light")
        self.assertEqual(settings2.get("search", "max_results"), 100)

    def test_reset_to_defaults(self):
        """Test resetting all settings to defaults."""
        from tui.state import TUISettings

        # Ensure clean start
        if os.path.exists(self.config_path):
            os.remove(self.config_path)

        settings = TUISettings(config_path=self.config_path)

        # Modify settings
        settings.set("display", "theme", "textual-light")
        settings.set("search", "max_results", 100)

        # Reset
        settings.reset_to_defaults()

        # Should be back to defaults
        self.assertEqual(settings.get("display", "theme"), "textual-dark")
        self.assertEqual(settings.get("search", "max_results"), 50)

    def test_reset_category(self):
        """Test resetting a single category."""
        from tui.state import TUISettings

        # Ensure clean start
        if os.path.exists(self.config_path):
            os.remove(self.config_path)

        settings = TUISettings(config_path=self.config_path)

        # Modify multiple categories
        settings.set("display", "theme", "textual-light")
        settings.set("search", "max_results", 100)

        # Reset only display
        settings.reset_category("display")

        # Display should be reset, search unchanged
        self.assertEqual(settings.get("display", "theme"), "textual-dark")
        self.assertEqual(settings.get("search", "max_results"), 100)

    def test_merge_with_new_defaults(self):
        """Test that loading merges with defaults (for new settings)."""
        from tui.state import TUISettings

        # Create old-style settings file (missing some keys)
        old_settings = {
            "display": {
                "theme": "textual-light"
                # Missing other display keys
            }
            # Missing other categories
        }

        with open(self.config_path, 'w') as f:
            json.dump(old_settings, f)

        # Load settings
        settings = TUISettings(config_path=self.config_path)

        # Should have user's value
        self.assertEqual(settings.get("display", "theme"), "textual-light")

        # Should have defaults for missing keys
        self.assertEqual(settings.get("display", "results_per_page"), 20)
        self.assertEqual(settings.get("search", "mode"), "fuzzy")

    def test_export_import(self):
        """Test exporting and importing settings."""
        from tui.state import TUISettings

        settings1 = TUISettings(config_path=self.config_path)
        settings1.set("display", "theme", "textual-light")
        settings1.set("search", "case_sensitive", True)

        # Export
        export_path = os.path.join(self.temp_dir, "export.json")
        result = settings1.export_to_file(export_path)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(export_path))

        # Import in new instance
        settings2 = TUISettings(config_path=self.config_path)
        settings2.reset_to_defaults()  # Start fresh

        result = settings2.import_from_file(export_path)
        self.assertTrue(result)

        self.assertEqual(settings2.get("display", "theme"), "textual-light")
        self.assertEqual(settings2.get("search", "case_sensitive"), True)

    def test_get_all(self):
        """Test getting all settings."""
        from tui.state import TUISettings

        settings = TUISettings(config_path=self.config_path)
        all_settings = settings.get_all()

        # Should be a copy
        self.assertIsNot(all_settings, settings.settings)

        # Should have all categories
        self.assertIn("display", all_settings)
        self.assertIn("search", all_settings)
        self.assertIn("config", all_settings)
        self.assertIn("advanced", all_settings)

    def test_invalid_json_falls_back_to_defaults(self):
        """Test that invalid JSON falls back to defaults."""
        from tui.state import TUISettings

        # Ensure file doesn't exist first
        if os.path.exists(self.config_path):
            os.remove(self.config_path)

        # Write invalid JSON
        with open(self.config_path, 'w') as f:
            f.write("{ invalid json }")

        # Should fall back to defaults without crashing
        settings = TUISettings(config_path=self.config_path)
        self.assertEqual(settings.get("display", "theme"), "textual-dark")

    def test_default_with_missing_key(self):
        """Test that get() returns default for missing keys."""
        from tui.state import TUISettings

        settings = TUISettings(config_path=self.config_path)

        # Missing key with default
        value = settings.get("nonexistent", "key", "default_value")
        self.assertEqual(value, "default_value")

        # Missing key without default
        value = settings.get("nonexistent", "key")
        self.assertIsNone(value)


if __name__ == '__main__':
    unittest.main()
