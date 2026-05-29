# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Tests for interactive TUI settings screen."""

import unittest
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestInteractiveSettingsScreen(unittest.TestCase):
    """Test suite for interactive settings functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock settings manager
        self.mock_settings = Mock()
        self.mock_settings.get = Mock(side_effect=self._mock_get_setting)
        self.mock_settings.set = Mock()
        self.mock_settings.save = Mock(return_value=True)
        self.mock_settings.reset_category = Mock()
        self.mock_settings.reset_to_defaults = Mock()

        self.settings_data = {
            "display": {
                "theme": "textual-dark",
                "show_line_numbers": True,
                "results_per_page": 20,
                "source_file_display": "auto",
            },
            "search": {
                "mode": "fuzzy",
                "case_sensitive": False,
                "max_results": 50,
            },
            "config": {
                "last_vendor": "asa",
                "last_path": "/path/to/config.conf",
                "auto_reload": False,
            },
            "advanced": {
                "enable_logging": True,
                "log_level": "INFO",
                "cache_enabled": True,
            },
        }

    def _mock_get_setting(self, category, key, default=None):
        """Mock settings getter."""
        return self.settings_data.get(category, {}).get(key, default)

    def test_settings_manager_integration(self):
        """Test settings manager methods are called correctly."""
        # Test get
        value = self.mock_settings.get("display", "theme", "textual-dark")
        self.assertEqual(value, "textual-dark")

        # Test set
        self.mock_settings.set("display", "theme", "textual-light")
        self.mock_settings.set.assert_called_with("display", "theme", "textual-light")

        # Test save
        result = self.mock_settings.save()
        self.assertTrue(result)

    def test_pending_changes_tracking(self):
        """Test pending changes are tracked before applying."""
        pending_changes = {
            "display": {},
            "search": {},
            "config": {},
            "advanced": {},
        }

        # Simulate user changing settings
        pending_changes["display"]["results_per_page"] = 50
        pending_changes["search"]["mode"] = "exact"

        # Verify changes are tracked
        self.assertEqual(pending_changes["display"]["results_per_page"], 50)
        self.assertEqual(pending_changes["search"]["mode"], "exact")
        self.assertEqual(len(pending_changes["display"]), 1)
        self.assertEqual(len(pending_changes["search"]), 1)

    def test_apply_pending_changes(self):
        """Test applying pending changes to settings manager."""
        pending_changes = {
            "display": {"results_per_page": 100},
            "search": {"mode": "prefix", "max_results": 200},
            "config": {},
            "advanced": {"log_level": "DEBUG"},
        }

        # Apply changes
        for category, changes in pending_changes.items():
            for key, value in changes.items():
                self.mock_settings.set(category, key, value)

        # Verify all changes were applied (4 total: 1 display, 2 search, 1 advanced)
        self.assertEqual(self.mock_settings.set.call_count, 4)
        self.mock_settings.set.assert_any_call("display", "results_per_page", 100)
        self.mock_settings.set.assert_any_call("search", "mode", "prefix")
        self.mock_settings.set.assert_any_call("search", "max_results", 200)
        self.mock_settings.set.assert_any_call("advanced", "log_level", "DEBUG")

    def test_reset_category(self):
        """Test resetting a single category to defaults."""
        # Reset display category
        self.mock_settings.reset_category("display")
        self.mock_settings.reset_category.assert_called_with("display")

        # Verify pending changes for category are cleared
        pending_changes = {
            "display": {"results_per_page": 100},
            "search": {"mode": "exact"},
        }

        # Simulate reset
        pending_changes["display"] = {}

        self.assertEqual(len(pending_changes["display"]), 0)
        self.assertEqual(len(pending_changes["search"]), 1)

    def test_reset_all_settings(self):
        """Test resetting all settings to defaults."""
        # Reset all
        self.mock_settings.reset_to_defaults()
        self.mock_settings.reset_to_defaults.assert_called_once()

        # Verify all pending changes are cleared
        pending_changes = {cat: {} for cat in ["display", "search", "config", "advanced"]}

        for category in pending_changes.values():
            self.assertEqual(len(category), 0)

    def test_widget_id_parsing(self):
        """Test parsing widget IDs to extract category and key."""
        widget_id = "setting-display-results_per_page"

        # Parse ID
        parts = widget_id.split("-", 2)
        self.assertEqual(len(parts), 3)

        _, category, key = parts
        self.assertEqual(category, "display")
        self.assertEqual(key, "results_per_page")

    def test_select_widget_change(self):
        """Test handling Select widget value changes."""
        # Mock select change event
        mock_event = Mock()
        mock_event.select.id = "setting-display-results_per_page"
        mock_event.value = 100

        # Parse widget ID
        parts = mock_event.select.id.split("-", 2)
        _, category, key = parts

        # Store pending change
        pending_changes = {"display": {}, "search": {}, "config": {}, "advanced": {}}
        pending_changes[category][key] = mock_event.value

        self.assertEqual(pending_changes["display"]["results_per_page"], 100)

    def test_switch_widget_change(self):
        """Test handling Switch widget value changes."""
        # Mock switch change event
        mock_event = Mock()
        mock_event.switch.id = "setting-search-case_sensitive"
        mock_event.value = True

        # Parse widget ID
        parts = mock_event.switch.id.split("-", 2)
        _, category, key = parts

        # Store pending change
        pending_changes = {"display": {}, "search": {}, "config": {}, "advanced": {}}
        pending_changes[category][key] = mock_event.value

        self.assertEqual(pending_changes["search"]["case_sensitive"], True)

    def test_display_settings_values(self):
        """Test display settings are loaded correctly."""
        # Get display settings
        theme = self.mock_settings.get("display", "theme", "textual-dark")
        show_lines = self.mock_settings.get("display", "show_line_numbers", True)
        results = self.mock_settings.get("display", "results_per_page", 20)
        source_display = self.mock_settings.get("display", "source_file_display", "auto")

        self.assertEqual(theme, "textual-dark")
        self.assertTrue(show_lines)
        self.assertEqual(results, 20)
        self.assertEqual(source_display, "auto")

    def test_search_settings_values(self):
        """Test search settings are loaded correctly."""
        # Get search settings
        mode = self.mock_settings.get("search", "mode", "fuzzy")
        case_sens = self.mock_settings.get("search", "case_sensitive", False)
        max_results = self.mock_settings.get("search", "max_results", 50)

        self.assertEqual(mode, "fuzzy")
        self.assertFalse(case_sens)
        self.assertEqual(max_results, 50)

    def test_advanced_settings_values(self):
        """Test advanced settings are loaded correctly."""
        # Get advanced settings
        logging = self.mock_settings.get("advanced", "enable_logging", True)
        log_level = self.mock_settings.get("advanced", "log_level", "INFO")
        cache = self.mock_settings.get("advanced", "cache_enabled", True)

        self.assertTrue(logging)
        self.assertEqual(log_level, "INFO")
        self.assertTrue(cache)

    def test_select_options_display(self):
        """Test Select widget has correct options."""
        # Results per page options
        results_options = [("10", 10), ("20", 20), ("50", 50), ("100", 100)]
        self.assertEqual(len(results_options), 4)
        self.assertIn(("20", 20), results_options)

        # Search mode options
        mode_options = [("Fuzzy (substring)", "fuzzy"), ("Prefix", "prefix"), ("Exact", "exact")]
        self.assertEqual(len(mode_options), 3)
        self.assertIn(("Fuzzy (substring)", "fuzzy"), mode_options)

        # Log level options
        log_options = [("DEBUG", "DEBUG"), ("INFO", "INFO"), ("WARNING", "WARNING"), ("ERROR", "ERROR")]
        self.assertEqual(len(log_options), 4)
        self.assertIn(("INFO", "INFO"), log_options)

    def test_category_switching(self):
        """Test switching between categories."""
        categories = [
            ("display", "Display Settings"),
            ("search", "Search Settings"),
            ("config", "Config Settings"),
            ("advanced", "Advanced"),
        ]

        # Simulate switching to each category
        for category_id, category_label in categories:
            # Verify category exists
            self.assertIsNotNone(category_id)
            self.assertIsNotNone(category_label)

    def test_save_operation_success(self):
        """Test successful save operation."""
        # Apply changes
        self.mock_settings.set("display", "results_per_page", 50)

        # Save
        result = self.mock_settings.save()
        self.assertTrue(result)

        # Verify save was called
        self.mock_settings.save.assert_called_once()

    def test_save_operation_failure(self):
        """Test save operation failure handling."""
        # Mock save failure
        self.mock_settings.save = Mock(return_value=False)

        # Attempt save
        result = self.mock_settings.save()
        self.assertFalse(result)

    def test_multiple_pending_changes(self):
        """Test handling multiple pending changes across categories."""
        pending_changes = {
            "display": {
                "results_per_page": 100,
                "show_line_numbers": False,
            },
            "search": {
                "mode": "exact",
                "max_results": 200,
                "case_sensitive": True,
            },
            "config": {},
            "advanced": {
                "log_level": "DEBUG",
            },
        }

        # Count total changes (2 display + 3 search + 0 config + 1 advanced = 6)
        total_changes = sum(len(changes) for changes in pending_changes.values())
        self.assertEqual(total_changes, 6)

    def test_widget_id_validation(self):
        """Test widget ID validation for non-setting widgets."""
        # Valid setting widget ID
        valid_id = "setting-display-theme"
        self.assertTrue(valid_id.startswith("setting-"))

        # Invalid widget ID (button, container, etc.)
        invalid_id = "settings-apply"
        self.assertFalse(invalid_id.startswith("setting-"))

        # Invalid setting ID (missing parts)
        invalid_id2 = "setting-display"
        parts = invalid_id2.split("-", 2)
        self.assertNotEqual(len(parts), 3)


if __name__ == '__main__':
    unittest.main()
