# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Regression test for Compare tab IndexError bug.

This test specifically checks the bug where selecting the Compare tab
would cause an IndexError due to incorrect container usage.
"""

import unittest


class TestCompareTabRegression(unittest.TestCase):
    """Test for the Compare tab IndexError regression."""

    def test_compare_prompt_does_not_use_wrong_container(self):
        """Test that show_compare_prompt doesn't use problematic container pattern.

        Regression test for: IndexError when selecting Compare tab.
        Root cause: Using 'with Vertical():' context manager without proper mounting.
        """
        try:
            from tui.widgets.detail_view import DetailView
        except ImportError:
            self.skipTest("textual not installed")

        # Read the source to verify the fix
        import inspect
        source = inspect.getsource(DetailView.show_compare_prompt)

        # Verify the problematic pattern is NOT present
        self.assertNotIn("with Vertical():", source,
                        "show_compare_prompt should not use 'with Vertical()' pattern")

        # Verify correct pattern IS present
        self.assertIn("self.mount(help_static)", source,
                     "show_compare_prompt should mount help_static directly")
        self.assertIn("self.mount(self.compare_input)", source,
                     "show_compare_prompt should mount compare_input directly")

    def test_compare_prompt_execution_no_errors(self):
        """Test that show_compare_prompt executes without IndexError."""
        try:
            from tui.widgets.detail_view import DetailView
        except ImportError:
            self.skipTest("textual not installed")

        detail_view = DetailView()
        test_obj = {'name': 'TEST_OBJ', 'type': 'object', 'detail': '10.0.0.1'}

        # This should NOT raise IndexError
        try:
            detail_view.show_compare_prompt(test_obj)
        except IndexError as e:
            self.fail(f"show_compare_prompt raised IndexError: {e}")
        except Exception as e:
            # Other exceptions might occur due to textual runtime,
            # but IndexError specifically should not happen
            if "list index out of range" in str(e).lower():
                self.fail(f"IndexError occurred in show_compare_prompt: {e}")

    def test_all_tab_handlers_no_index_errors(self):
        """Test that all tab selection handlers don't raise IndexError."""
        from analysis_core import inspect_object, compare_objects, find_object_usage
        from parsers.cisco.asa import ASAConfig

        config_text = """
object network TEST_OBJ
 host 10.0.0.1
"""
        config = ASAConfig(config_text)
        test_obj = {'name': 'TEST_OBJ', 'type': 'object'}

        # Test all analysis functions (backend for tabs)
        try:
            # Inspect tab backend
            result = inspect_object(config, test_obj['name'])
            self.assertIsNotNone(result)

            # Compare tab backend
            result = compare_objects(config, test_obj['name'], 'OTHER_OBJ')
            self.assertIsNotNone(result)

            # ACLs tab backend
            result = find_object_usage(config, test_obj['name'])
            self.assertIsNotNone(result)

        except IndexError as e:
            self.fail(f"Tab handler raised IndexError: {e}")


if __name__ == '__main__':
    unittest.main()
