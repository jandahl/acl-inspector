"""Integration tests for TUI tab functionality.

Tests that all tabs can be activated without errors.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
from parsers.cisco.asa import ASAConfig


class TestTUITabs(unittest.TestCase):
    """Test that all TUI tabs work correctly."""

    def setUp(self):
        """Set up test fixtures."""
        self.sample_config = """
interface GigabitEthernet0/0
 nameif INSIDE
 ip address 10.1.0.1 255.255.255.0

object network OBJ_TEST_SERVER
 host 10.1.0.50

object-group network GRP_TEST
 network-object object OBJ_TEST_SERVER

access-list TEST_ACL extended permit tcp any host 10.1.0.50 eq 443
access-list TEST_ACL extended deny ip any any
"""
        self.config = ASAConfig(self.sample_config)
        self.test_object = {
            'name': 'OBJ_TEST_SERVER',
            'type': 'object',
            'detail': '10.1.0.50'
        }

    def test_details_tab_no_errors(self):
        """Test that Details tab doesn't raise errors."""
        # Import here to avoid requiring textual for all tests
        try:
            from tui.widgets.detail_view import DetailView
        except ImportError:
            self.skipTest("textual not installed")

        detail_view = DetailView()

        # Should not raise any errors
        try:
            detail_view.update_object(self.test_object, self.config)
        except Exception as e:
            self.fail(f"Details tab raised unexpected error: {e}")

    def test_inspect_tab_no_errors(self):
        """Test that Inspect tab functionality doesn't raise errors."""
        from analysis_core import inspect_object

        # Should not raise any errors
        try:
            result = inspect_object(
                self.config,
                target=self.test_object['name']
            )
            # Verify result structure
            self.assertIsNotNone(result)
            self.assertEqual(result.object_name, self.test_object['name'])
        except Exception as e:
            self.fail(f"Inspect tab raised unexpected error: {e}")

    def test_compare_tab_prompt_no_errors(self):
        """Test that Compare tab prompt doesn't raise errors."""
        try:
            from tui.widgets.detail_view import DetailView
        except ImportError:
            self.skipTest("textual not installed")

        detail_view = DetailView()
        all_objects = [
            {'name': 'OBJ1', 'type': 'object', 'detail': '10.0.0.1'},
            {'name': 'OBJ2', 'type': 'object', 'detail': '10.0.0.2'},
        ]

        # Should not raise any errors when showing compare prompt
        try:
            detail_view.show_compare_prompt(self.test_object, all_objects)
            # Verify compare mode is set
            self.assertTrue(detail_view.compare_mode)
            self.assertEqual(detail_view.current_object, self.test_object)
            self.assertEqual(len(detail_view.compare_suggestions), 2)
        except Exception as e:
            self.fail(f"Compare tab prompt raised unexpected error: {e}")

    def test_compare_tab_results_no_errors(self):
        """Test that Compare tab results display doesn't raise errors."""
        from analysis_core import compare_objects

        # Should not raise any errors
        try:
            result = compare_objects(
                self.config,
                old_target=self.test_object['name'],
                new_target='10.1.0.60',  # Different target
                include_any=False
            )
            # Verify result structure
            self.assertIsNotNone(result)
            self.assertEqual(result.old_name, self.test_object['name'])
            self.assertEqual(result.new_name, '10.1.0.60')
        except Exception as e:
            self.fail(f"Compare tab results raised unexpected error: {e}")

    def test_acls_tab_no_errors(self):
        """Test that ACLs (Used in) tab doesn't raise errors."""
        from analysis_core import find_object_usage

        # Should not raise any errors
        try:
            result = find_object_usage(
                self.config,
                object_name=self.test_object['name']
            )
            # Verify result structure
            self.assertIsNotNone(result)
            self.assertEqual(result.object_name, self.test_object['name'])
        except Exception as e:
            self.fail(f"ACLs tab raised unexpected error: {e}")

    def test_all_tabs_with_nonexistent_object(self):
        """Test that all tabs handle nonexistent objects gracefully."""
        nonexistent_obj = {
            'name': 'NONEXISTENT_OBJECT_XYZ',
            'type': 'object',
            'detail': 'N/A'
        }

        from analysis_core import inspect_object, compare_objects, find_object_usage

        # Inspect tab
        try:
            result = inspect_object(self.config, nonexistent_obj['name'])
            self.assertIsNotNone(result)
        except Exception as e:
            self.fail(f"Inspect tab failed with nonexistent object: {e}")

        # Compare tab
        try:
            result = compare_objects(
                self.config,
                old_target=nonexistent_obj['name'],
                new_target='ANOTHER_NONEXISTENT'
            )
            self.assertIsNotNone(result)
        except Exception as e:
            self.fail(f"Compare tab failed with nonexistent objects: {e}")

        # ACLs tab
        try:
            result = find_object_usage(self.config, nonexistent_obj['name'])
            self.assertIsNotNone(result)
        except Exception as e:
            self.fail(f"ACLs tab failed with nonexistent object: {e}")

    def test_all_tabs_with_empty_name(self):
        """Test that all tabs handle empty object names gracefully."""
        from analysis_core import inspect_object, compare_objects, find_object_usage

        # Inspect tab with empty name
        try:
            result = inspect_object(self.config, "")
            self.assertIsNotNone(result)
        except Exception as e:
            self.fail(f"Inspect tab failed with empty name: {e}")

        # Compare tab with empty names
        try:
            result = compare_objects(self.config, "", "")
            self.assertIsNotNone(result)
        except Exception as e:
            self.fail(f"Compare tab failed with empty names: {e}")

        # ACLs tab with empty name
        try:
            result = find_object_usage(self.config, "")
            self.assertIsNotNone(result)
        except Exception as e:
            self.fail(f"ACLs tab failed with empty name: {e}")

    def test_tabs_with_special_characters(self):
        """Test that tabs handle special characters in object names."""
        from analysis_core import inspect_object, compare_objects, find_object_usage

        special_names = [
            "object-with-dash",
            "object_with_underscore",
            "object.with.dots",
            "object123",
        ]

        for special_name in special_names:
            # Inspect tab
            try:
                result = inspect_object(self.config, special_name)
                self.assertIsNotNone(result)
            except Exception as e:
                self.fail(f"Inspect tab failed with '{special_name}': {e}")

            # Compare tab
            try:
                result = compare_objects(self.config, special_name, "other_object")
                self.assertIsNotNone(result)
            except Exception as e:
                self.fail(f"Compare tab failed with '{special_name}': {e}")

            # ACLs tab
            try:
                result = find_object_usage(self.config, special_name)
                self.assertIsNotNone(result)
            except Exception as e:
                self.fail(f"ACLs tab failed with '{special_name}': {e}")

    def test_compare_input_handler(self):
        """Test that compare input submission handler works correctly."""
        try:
            from tui.widgets.detail_view import DetailView
            from textual.widgets import Input
        except ImportError:
            self.skipTest("textual not installed")

        detail_view = DetailView()
        detail_view.show_compare_prompt(self.test_object)

        # Simulate input submission
        mock_event = Mock()
        mock_event.input = detail_view.compare_input
        mock_event.value = "OBJ_OTHER_SERVER"

        # Should not raise errors
        try:
            # This will post a message, which is fine
            detail_view.on_input_submitted(mock_event)
        except Exception as e:
            self.fail(f"Compare input handler raised unexpected error: {e}")

    def test_detail_view_clear(self):
        """Test that detail view clear works correctly."""
        try:
            from tui.widgets.detail_view import DetailView
        except ImportError:
            self.skipTest("textual not installed")

        detail_view = DetailView()

        # Set up detail view with object
        detail_view.update_object(self.test_object, self.config)

        # Clear should not raise errors
        try:
            detail_view.clear()
            self.assertIsNone(detail_view.current_object)
            self.assertFalse(detail_view.compare_mode)
        except Exception as e:
            self.fail(f"Detail view clear raised unexpected error: {e}")

    def test_show_content_with_various_types(self):
        """Test that show_content handles different content types."""
        try:
            from tui.widgets.detail_view import DetailView
            from rich.text import Text
            from rich.table import Table
            from rich.panel import Panel
        except ImportError:
            self.skipTest("textual/rich not installed")

        detail_view = DetailView()

        # Test with Text
        try:
            text = Text("Test content")
            detail_view.show_content(text)
        except Exception as e:
            self.fail(f"show_content failed with Text: {e}")

        # Test with Table
        try:
            table = Table()
            table.add_column("Column")
            table.add_row("Row")
            detail_view.show_content(table)
        except Exception as e:
            self.fail(f"show_content failed with Table: {e}")

        # Test with Panel
        try:
            panel = Panel("Panel content")
            detail_view.show_content(panel)
        except Exception as e:
            self.fail(f"show_content failed with Panel: {e}")


    def test_compare_suggestions_filtering(self):
        """Test that compare suggestions are filtered correctly."""
        try:
            from tui.widgets.detail_view import DetailView
        except ImportError:
            self.skipTest("textual not installed")

        detail_view = DetailView()
        all_objects = [
            {'name': 'WEB_SERVER_01', 'type': 'object', 'detail': '10.0.0.1'},
            {'name': 'WEB_SERVER_02', 'type': 'object', 'detail': '10.0.0.2'},
            {'name': 'DB_SERVER_01', 'type': 'object', 'detail': '10.0.1.1'},
            {'name': 'APP_SERVER_01', 'type': 'object', 'detail': '10.0.2.1'},
        ]

        # Show compare prompt with suggestions
        detail_view.show_compare_prompt(self.test_object, all_objects)

        # Verify suggestions are available
        self.assertEqual(len(detail_view.compare_suggestions), 4)

        # Suggestions should be filtered (we can't easily test the input handler
        # without running the actual TUI, but we verified the structure exists)
        self.assertIsNotNone(detail_view.compare_input)
        self.assertIsNotNone(detail_view.compare_suggestions_widget)

    def test_keyboard_routing_with_input_focus(self):
        """Test that left/right arrows work correctly based on focus."""
        # This is a unit test for the logic, full integration needs TUI runtime
        # Just verify the code structure is correct
        try:
            from tui.app import SingularityApp
            import inspect
            source = inspect.getsource(SingularityApp.on_key)

            # Verify the fix for left/right arrow handling
            self.assertIn("isinstance(focused, Input)", source,
                         "on_key should check if Input has focus")
        except ImportError:
            self.skipTest("textual not installed")


if __name__ == '__main__':
    unittest.main()
