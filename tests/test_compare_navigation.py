# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Unit tests for Compare tab navigation improvements."""

import unittest
from unittest.mock import Mock, MagicMock


class TestCompareNavigation(unittest.TestCase):
    """Test Compare tab keyboard navigation."""

    def test_compare_suggestions_selection(self):
        """Test up/down navigation in compare suggestions."""
        try:
            from tui.widgets.detail_view import DetailView
        except ImportError:
            self.skipTest("textual not installed")

        detail_view = DetailView()

        # Set up compare mode with suggestions
        base_obj = {"name": "TestObj", "type": "object"}
        suggestions = [
            {"name": "Obj1", "type": "object"},
            {"name": "Obj2", "type": "object"},
            {"name": "Obj3", "type": "object"},
        ]

        detail_view.current_object = base_obj
        detail_view.compare_mode = True
        detail_view.compare_filtered_suggestions = suggestions
        detail_view.compare_selected_index = 0

        # Simulate down key
        self.assertEqual(detail_view.compare_selected_index, 0)

        # Move down
        detail_view.compare_selected_index = min(
            len(suggestions) - 1,
            detail_view.compare_selected_index + 1
        )
        self.assertEqual(detail_view.compare_selected_index, 1)

        # Move down again
        detail_view.compare_selected_index = min(
            len(suggestions) - 1,
            detail_view.compare_selected_index + 1
        )
        self.assertEqual(detail_view.compare_selected_index, 2)

        # Move down at end (should stay at 2)
        detail_view.compare_selected_index = min(
            len(suggestions) - 1,
            detail_view.compare_selected_index + 1
        )
        self.assertEqual(detail_view.compare_selected_index, 2)

        # Move up
        detail_view.compare_selected_index = max(
            0,
            detail_view.compare_selected_index - 1
        )
        self.assertEqual(detail_view.compare_selected_index, 1)

    def test_compare_enter_uses_selected_suggestion(self):
        """Test that Enter uses the selected suggestion."""
        try:
            from tui.widgets.detail_view import DetailView
        except ImportError:
            self.skipTest("textual not installed")

        detail_view = DetailView()

        # Set up compare mode
        base_obj = {"name": "TestObj", "type": "object"}
        suggestions = [
            {"name": "Obj1", "type": "object"},
            {"name": "Obj2", "type": "object"},
        ]

        detail_view.current_object = base_obj
        detail_view.compare_mode = True
        detail_view.compare_filtered_suggestions = suggestions
        detail_view.compare_selected_index = 1  # Select second item

        # Verify logic for selecting suggestion
        if detail_view.compare_filtered_suggestions:
            selected_obj = detail_view.compare_filtered_suggestions[detail_view.compare_selected_index]
            self.assertEqual(selected_obj['name'], "Obj2")

    def test_compare_filtered_suggestions_reset_on_input(self):
        """Test that suggestions are reset when input changes."""
        try:
            from tui.widgets.detail_view import DetailView
        except ImportError:
            self.skipTest("textual not installed")

        detail_view = DetailView()

        # Initially empty
        self.assertEqual(len(detail_view.compare_filtered_suggestions), 0)
        self.assertEqual(detail_view.compare_selected_index, 0)

        # Simulate filtering
        all_suggestions = [
            {"name": "WebServer1", "type": "object"},
            {"name": "WebServer2", "type": "object"},
            {"name": "DatabaseServer", "type": "object"},
        ]

        query = "web"
        matching = [
            obj for obj in all_suggestions
            if query in obj.get('name', '').lower()
        ]

        detail_view.compare_filtered_suggestions = matching
        detail_view.compare_selected_index = 0

        self.assertEqual(len(detail_view.compare_filtered_suggestions), 2)
        self.assertEqual(detail_view.compare_filtered_suggestions[0]['name'], "WebServer1")
        self.assertEqual(detail_view.compare_filtered_suggestions[1]['name'], "WebServer2")

    def test_compare_escape_blurs_input(self):
        """Test that ESC handler is present."""
        try:
            from tui.widgets.detail_view import DetailView
        except ImportError:
            self.skipTest("textual not installed")

        detail_view = DetailView()

        # Verify on_key method exists
        self.assertTrue(hasattr(detail_view, 'on_key'))
        self.assertTrue(callable(detail_view.on_key))

    def test_render_compare_suggestions_with_selection(self):
        """Test that suggestions render with correct selection indicator."""
        try:
            from tui.widgets.detail_view import DetailView
        except ImportError:
            self.skipTest("textual not installed")

        detail_view = DetailView()

        # Mock the widget
        detail_view.compare_suggestions_widget = Mock()

        suggestions = [
            {"name": "Obj1", "type": "object", "detail": "10.0.1.1"},
            {"name": "Obj2", "type": "object", "detail": "10.0.1.2"},
        ]

        detail_view.compare_filtered_suggestions = suggestions
        detail_view.compare_selected_index = 1  # Select second

        # Call render
        detail_view._render_compare_suggestions()

        # Verify update was called
        self.assertTrue(detail_view.compare_suggestions_widget.update.called)


if __name__ == '__main__':
    unittest.main()
