# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Integration tests for TUI tab functionality.

Tests that all tabs can be activated without errors.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
from parsers.cisco.asa import ASAConfig
from common.vendor_caps import VendorCaps


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
        self._detail_view_cache = None

    def _with_detail_view(self, action):
        """Execute a DetailView action inside a minimal Textual app."""
        try:
            from textual.app import App
            from tui.widgets.detail_view import DetailView
            from textual._context import active_app
        except ImportError:
            self.skipTest("textual not installed")

        class Harness(App):
            def __init__(app_self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                app_self.detail_view = DetailView()

            def compose(app_self):
                yield app_self.detail_view

            async def on_mount(app_self):
                token = active_app.set(app_self)
                try:
                    action(app_self.detail_view)
                    await app_self.action_quit()
                finally:
                    active_app.reset(token)

        harness = Harness()
        harness.run(headless=True)
        return harness.detail_view

    def test_details_tab_no_errors(self):
        """Test that Details tab doesn't raise errors."""
        self._with_detail_view(lambda view: view.update_object(self.test_object, self.config))

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
        all_objects = [
            {'name': 'OBJ1', 'type': 'object', 'detail': '10.0.0.1'},
            {'name': 'OBJ2', 'type': 'object', 'detail': '10.0.0.2'},
        ]

        detail_view = self._with_detail_view(
            lambda view: view.show_compare_prompt(self.test_object, all_objects)
        )
        self.assertTrue(detail_view.compare_mode)
        self.assertEqual(detail_view.current_object, self.test_object)
        self.assertEqual(len(detail_view.compare_suggestions), 2)

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
        def _action(view):
            view.show_compare_prompt(self.test_object)
            mock_event = Mock()
            mock_event.input = view.compare_input
            mock_event.value = "OBJ_OTHER_SERVER"
            view.on_input_submitted(mock_event)

        try:
            self._with_detail_view(_action)
        except unittest.SkipTest:
            raise
        except Exception as e:
            self.fail(f"Compare input handler raised unexpected error: {e}")

    def test_detail_view_clear(self):
        """Test that detail view clear works correctly."""
        def _action(view):
            view.update_object(self.test_object, self.config)
            view.clear()
            self.assertIsNone(view.current_object)
            self.assertFalse(view.compare_mode)

        try:
            self._with_detail_view(_action)
        except unittest.SkipTest:
            raise
        except Exception as e:
            self.fail(f"Detail view clear raised unexpected error: {e}")

    def test_show_content_with_various_types(self):
        """Test that show_content handles different content types."""
        try:
            from rich.text import Text
            from rich.table import Table
            from rich.panel import Panel
        except ImportError:
            self.skipTest("textual/rich not installed")

        self._with_detail_view(lambda view: view.show_content(Text("Test content")))

        def _table_action(view):
            table = Table()
            table.add_column("Column")
            table.add_row("Row")
            view.show_content(table)

        self._with_detail_view(_table_action)
        self._with_detail_view(lambda view: view.show_content(Panel("Panel content")))


    def test_compare_suggestions_filtering(self):
        """Test that compare suggestions are filtered correctly."""
        try:
            from tui.widgets.detail_view import DetailView
        except ImportError:
            self.skipTest("textual not installed")

        all_objects = [
            {'name': 'WEB_SERVER_01', 'type': 'object', 'detail': '10.0.0.1'},
            {'name': 'WEB_SERVER_02', 'type': 'object', 'detail': '10.0.0.2'},
            {'name': 'DB_SERVER_01', 'type': 'object', 'detail': '10.0.1.1'},
            {'name': 'APP_SERVER_01', 'type': 'object', 'detail': '10.0.2.1'},
        ]

        detail_view = self._with_detail_view(
            lambda view: view.show_compare_prompt(self.test_object, all_objects)
        )

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

    def test_action_tabs_has_prev_next_selectors(self):
        """Ensure action tabs support previous/next selection used by on_key."""
        try:
            from tui.widgets.action_tabs import ActionTabs
            from tui.app import SingularityApp
            from analysis_core import path_check_supported
        except ImportError:
            self.skipTest("textual not installed")

        tabs = ActionTabs()
        # default selected is "details"; previous should wrap to last tab
        tabs._select_previous_tab()
        self.assertEqual(tabs.selected_tab, "path")
        # next should advance
        tabs._select_next_tab()
        self.assertEqual(tabs.selected_tab, "details")

        # Verify effective caps helper can disable path when unsupported
        class DummyConfig:
            vendor = "asa"

        app = SingularityApp(vendor="asa", config_path="", vdom="", vendor_targets=[])
        caps = app._effective_caps("asa", DummyConfig())
        self.assertTrue(caps.supports_packet)

    def test_path_tab_gating(self):
        """Path tab should be hidden when capability check fails."""
        try:
            from tui.widgets.action_tabs import ActionTabs
            from tui.app import SingularityApp
        except ImportError:
            self.skipTest("textual not installed")

        class NoPathConfig:
            vendor = "asa"
        class AsaConfig(NoPathConfig):
            pass
        class FortiConfig:
            vendor = "fortigate"

        app = SingularityApp(vendor="asa", config_path="", vdom="", vendor_targets=[])
        tabs = ActionTabs()
        # Force-compose buttons for headless test
        list(tabs.compose())

        # When path not supported, ensure hidden flag is set
        caps_no_path = app._effective_caps("asa", config=None)
        tabs.apply_vendor_caps(caps_no_path)
        path_btn = next((b for b in tabs._buttons if b.id == "tab-path"), None)
        self.assertIsNotNone(path_btn)
        self.assertEqual(path_btn.hidden, not caps_no_path.supports_packet)

        # ASA supported case
        caps_asa = app._effective_caps("asa", AsaConfig())
        tabs.apply_vendor_caps(caps_asa)
        self.assertFalse(path_btn.hidden)

        # Forti supported case
        caps_ftg = app._effective_caps("fortigate", FortiConfig())
        tabs.apply_vendor_caps(caps_ftg)
        self.assertFalse(path_btn.hidden)

    def test_close_detail_restores_cached_results(self):
        """ESC should restore the cached result set and selection."""
        try:
            from tui.app import SingularityApp
            from tui.widgets.search_bar import SearchBar
            from tui.widgets.suggestion_list import SuggestionList
        except ImportError:
            self.skipTest("textual not installed")

        app = SingularityApp(vendor="asa", config_path="", vdom="", vendor_targets=[])
        app._apply_caps_to_tabs = lambda _vendor: None
        app.display_results = [
            {"name": "obj1", "type": "object"},
            {"name": "obj2", "type": "group"},
            {"name": "obj3", "type": "object"},
        ]
        app.last_results = app.display_results[:]
        app.last_selected_index = 1
        app.drill_down_active = True

        class DummyContainer:
            def __init__(self):
                self.classes = set()

            def remove_class(self, _name):
                self.classes.discard(_name)

            def add_class(self, name):
                self.classes.add(name)

        class DummySearchBar:
            def __init__(self):
                self.value = "obj"
                self.has_focus = False
                self._focused = False

            def focus(self):
                self._focused = True

        class DummySuggestionList:
            def __init__(self):
                self.results = []
                self.selected_index = 0
                self.has_focus = False

            def update_results(self, results):
                self.results = list(results)
                if self.selected_index >= len(self.results):
                    self.selected_index = 0

        search_bar = DummySearchBar()
        suggestions = DummySuggestionList()

        containers = {
            "#breadcrumb-container": DummyContainer(),
            "#actions-container": DummyContainer(),
            "#detail-container": DummyContainer(),
            "#suggestions-container": DummyContainer(),
        }

        def fake_query(selector, *_, **__):
            if selector is SearchBar:
                return search_bar
            if selector is SuggestionList:
                return suggestions
            if isinstance(selector, str) and selector in containers:
                return containers[selector]
            raise KeyError(selector)

        app.query_one = fake_query

        app.action_close_detail_or_clear()

        self.assertEqual(suggestions.results, app.display_results)
        self.assertEqual(suggestions.selected_index, app.last_selected_index)
        self.assertTrue(getattr(search_bar, "_focused", False))

    def test_on_key_does_not_double_step_results(self):
        """Navigation should not jump two items when suggestions already have focus."""
        try:
            from tui.app import SingularityApp
            from tui.widgets.search_bar import SearchBar
            from tui.widgets.suggestion_list import SuggestionList
        except ImportError:
            self.skipTest("textual not installed")

        # Minimal fake event to track prevent_default calls
        class DummyEvent:
            def __init__(self, key):
                self.key = key
                self.prevented = False

            def prevent_default(self):
                self.prevented = True

        class DummyContainer:
            def __init__(self):
                self.classes = set()

        app = SingularityApp(vendor="asa", config_path="", vdom="", vendor_targets=[])
        app.drill_down_active = False

        suggestions_container = DummyContainer()

        search_bar = type("DummySearch", (), {"has_focus": True})()
        class DummySuggestions:
            def __init__(self):
                self.results = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
                self.selected_index = 0
                self.has_focus = False

        suggestions = DummySuggestions()

        # When search has focus, app drives list
        def fake_query(selector, *_, **__):
            if selector == "#suggestions-container":
                return suggestions_container
            if selector is SearchBar:
                return search_bar
            if selector.__name__ == "SuggestionList":
                return suggestions
            raise KeyError(selector)

        app.query_one = fake_query

        evt = DummyEvent("down")
        app.on_key(evt)
        self.assertEqual(suggestions.selected_index, 1)
        self.assertTrue(evt.prevented)

        # If suggestions already have focus, app should not change index
        suggestions.has_focus = True
        evt2 = DummyEvent("down")
        app.on_key(evt2)
        self.assertEqual(suggestions.selected_index, 1)
        self.assertFalse(evt2.prevented)


class TestActionTabsCapabilities(unittest.TestCase):
    """Ensure vendor caps hide tabs as expected."""

    def _mount_tabs(self, caps):
        try:
            from textual.app import App
            from textual._context import active_app
            from tui.widgets.action_tabs import ActionTabs
        except ImportError:
            self.skipTest("textual not installed")

        class Harness(App):
            def compose(app_self):
                app_self.tabs = ActionTabs()
                yield app_self.tabs

            async def on_mount(app_self):
                token = active_app.set(app_self)
                try:
                    app_self.tabs.apply_vendor_caps(caps)
                    await app_self.action_quit()
                finally:
                    active_app.reset(token)

        harness = Harness()
        harness.run(headless=True)
        return harness.tabs

    def test_compare_tab_hidden_when_vendor_lacks_compare(self):
        caps = VendorCaps(
            name="test",
            label="Test",
            config_field="config",
            requires_vdom=False,
            supports_inspect=True,
            supports_compare=False,
            supports_find=True,
            supports_packet=True,
        )
        tabs = self._mount_tabs(caps)
        compare_btn = next((btn for btn in tabs._buttons if btn.id == "tab-compare"), None)
        self.assertIsNotNone(compare_btn)
        self.assertTrue(compare_btn.hidden)


class TestOnItemSelected(unittest.TestCase):
    """Regression tests for on_suggestion_list_item_selected (issue #49)."""

    def _make_app_with_stubs(self):
        """Return a SingularityApp with query_one, _get_object_config, and
        _apply_caps_to_tabs stubbed so the handler can run without a real
        Textual event loop."""
        try:
            from tui.app import SingularityApp
            from tui.widgets.suggestion_list import SuggestionList
            from tui.widgets.detail_view import DetailView
            from tui.widgets.action_tabs import ActionTabs
        except ImportError:
            self.skipTest("textual not installed")

        app = SingularityApp(vendor="asa", config_path="", vdom="", vendor_targets=[])

        class _Container:
            def add_class(self, _): pass
            def remove_class(self, _): pass

        class _Breadcrumb:
            def update(self, _): pass

        class _SuggestionList:
            selected_index = 3

        class _DetailView:
            def __init__(self):
                self.last_item = None
                self.last_config = None
            def update_object(self, item, config):
                self.last_item = item
                self.last_config = config

        class _ActionTabs:
            def focus(self):
                pass
            def clear_tabs(self):
                pass
            def add_tab(self, label, view_id):
                pass

        detail_view = _DetailView()

        _widgets = {
            SuggestionList: _SuggestionList(),
            DetailView: detail_view,
            ActionTabs: _ActionTabs(),
            "#breadcrumb": _Breadcrumb(),
            "#breadcrumb-container": _Container(),
            "#actions-container": _Container(),
            "#suggestions-container": _Container(),
            "#detail-container": _Container(),
        }

        def fake_query_one(selector, *_args, **_kwargs):
            if selector in _widgets:
                return _widgets[selector]
            # ActionTabs lookup is wrapped in try/except in the handler; let it fail
            raise Exception(f"no stub for {selector!r}")

        app.query_one = fake_query_one

        return app, detail_view

    def test_obj_config_passed_to_apply_caps_and_detail_view(self):
        """_apply_caps_to_tabs and detail_view.update_object must both receive
        the config returned by _get_object_config (regression for issue #49)."""
        try:
            from tui.app import SingularityApp
            from tui.widgets.suggestion_list import SuggestionList
        except ImportError:
            self.skipTest("textual not installed")

        app, detail_view = self._make_app_with_stubs()

        sentinel_config = object()  # unique identity — proves the right value was passed
        app._get_object_config = Mock(return_value=sentinel_config)

        caps_calls = []
        app._apply_caps_to_tabs = lambda vendor, config=None: caps_calls.append((vendor, config))

        item = {"name": "OBJ_WEB", "type": "object", "vendor": "asa"}

        class _Msg:
            pass
        msg = _Msg()
        msg.item = item

        # This would raise UnboundLocalError before the fix.
        app.on_suggestion_list_item_selected(msg)

        self.assertEqual(len(caps_calls), 1, "_apply_caps_to_tabs should be called once")
        _vendor, _config = caps_calls[0]
        self.assertIs(_config, sentinel_config,
                      "_apply_caps_to_tabs must receive the config from _get_object_config")
        self.assertIs(detail_view.last_config, sentinel_config,
                      "detail_view.update_object must receive the same config")

    def test_vendor_falls_back_to_app_vendor(self):
        """When the item has no 'vendor' key, the app's own vendor is used."""
        try:
            from tui.app import SingularityApp
        except ImportError:
            self.skipTest("textual not installed")

        app, _ = self._make_app_with_stubs()
        app._get_object_config = Mock(return_value=None)

        caps_calls = []
        app._apply_caps_to_tabs = lambda vendor, config=None: caps_calls.append(vendor)

        class _Msg:
            item = {"name": "OBJ_X", "type": "object"}  # no "vendor" key

        app.on_suggestion_list_item_selected(_Msg())

        self.assertEqual(caps_calls, ["asa"])


if __name__ == '__main__':
    unittest.main()
