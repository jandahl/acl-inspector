# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Regression tests for TUI path check UI."""

from __future__ import annotations

import unittest
from types import MethodType
from unittest import mock

from parsers.cisco.asa import ASAConfig
from tests.fixtures.cisco_asa_example import ASA_EXAMPLE

try:
    from tui.app import SingularityApp
    TEXTUAL_AVAILABLE = True
except ImportError:  # pragma: no cover - textual optional in CI
    TEXTUAL_AVAILABLE = False


class FakeDetailView:
    """Lightweight stand-in for the DetailView widget."""

    def __init__(self) -> None:
        self.children = []

    def remove_children(self) -> None:
        self.children.clear()

    def mount(self, *widgets) -> None:
        for widget in widgets:
            if isinstance(widget, FakeVertical):
                widget.attached = True
            self.children.append(widget)


class FakeVertical:
    """Captures mount order to ensure children attach after parent."""

    def __init__(self, *args, **kwargs) -> None:
        self.id = kwargs.get("id")
        self.attached = False
        self.children = []

    def mount(self, *widgets) -> None:
        if not self.attached:
            raise RuntimeError("mount called before container attached")
        self.children.extend(widgets)


class FakeInputWidget:
    """Stub Input that avoids Textual internals."""

    def __init__(self, *args, **kwargs) -> None:
        self.value = kwargs.get("value", "")
        self.placeholder = kwargs.get("placeholder", "")
        self.id = kwargs.get("id")
        self.classes = kwargs.get("classes", "")

    def focus(self) -> None:
        pass

    def blur(self) -> None:
        pass


class FakeButton:
    """Stub Button that captures parameters without using Textual."""

    def __init__(self, label: str, **kwargs) -> None:
        self.label = label
        self.kwargs = kwargs


@unittest.skipUnless(TEXTUAL_AVAILABLE, "textual not installed")
class TestTUIPathSuggestionPanels(unittest.TestCase):
    """The path-check view surfaces correction suggestions + a verify toggle."""

    DENY_CFG = """
interface GigabitEthernet0/0
 nameif outside
 security-level 0
 ip address 203.0.113.2 255.255.255.0
!
interface GigabitEthernet0/1
 nameif inside
 security-level 100
 ip address 10.0.0.1 255.255.255.0
!
object network WEB
 host 10.0.0.10
!
access-list outside_access_in extended permit tcp any host 10.0.0.99 eq 443
access-list outside_access_in extended deny ip any host 10.0.0.10
access-group outside_access_in in interface outside
"""

    def _panels_text(self, result, show_verify):
        from rich.console import Console
        app = SingularityApp(vendor="asa", config_path="")
        app._path_show_verify = show_verify
        panels = app._build_path_suggestion_panels(result)
        console = Console(width=100, record=True)
        for p in panels:
            console.print(p)
        return panels, console.export_text()

    def test_blocked_flow_renders_suggestion_panel(self):
        from parsers.cisco.asa import path_check
        result = path_check(self.DENY_CFG, '203.0.113.5', 'WEB',
                            proto='tcp', dports={443})
        panels, text = self._panels_text(result, show_verify=False)
        self.assertTrue(panels)
        self.assertIn('Correction Suggestion', text)
        self.assertIn('access-list outside_access_in extended permit', text)
        # Verification hidden by default.
        self.assertNotIn('packet-tracer input', text)
        self.assertIn('ctrl+v to show', text)

    def test_verify_toggle_reveals_commands(self):
        from parsers.cisco.asa import path_check
        result = path_check(self.DENY_CFG, '203.0.113.5', 'WEB',
                            proto='tcp', dports={443})
        _panels, text = self._panels_text(result, show_verify=True)
        self.assertIn('packet-tracer input', text)

    def test_allowed_flow_has_no_suggestion_panel(self):
        from parsers.cisco.asa import path_check
        result = path_check(self.DENY_CFG, '203.0.113.5', '10.0.0.99',
                            proto='tcp', dports={443})
        app = SingularityApp(vendor="asa", config_path="")
        self.assertEqual(app._build_path_suggestion_panels(result), [])

    def test_verify_toggle_ignores_stale_object(self):
        # State stored for object 'A'; current selection is 'B' -> toggle no-ops
        # (prevents rendering a previous object's results).
        app = SingularityApp(vendor="asa", config_path="")
        app._path_render_state = ('A', {"allowed": False}, 's', 'd', 'tcp', 443)
        app._path_show_verify = False
        app.selected_object = {"name": "B"}
        app.action_toggle_path_verify()
        self.assertFalse(app._path_show_verify)  # unchanged — stale object
        # Matching object -> toggle flips (render attempt is harmless w/o widget).
        app.selected_object = {"name": "A"}
        app.action_toggle_path_verify()
        self.assertTrue(app._path_show_verify)


@unittest.skipUnless(TEXTUAL_AVAILABLE, "textual not installed")
class TestTUIPathForm(unittest.TestCase):
    """Ensure path check UI mounts controls safely."""

    def test_path_form_mount_order(self):
        """Path form should attach container before mounting children."""
        app = SingularityApp(vendor="asa", config_path="")
        config = ASAConfig(ASA_EXAMPLE)
        app.selected_object = {"name": "OBJ_WEB", "config": config}
        app.parsed_config = config

        detail_view = FakeDetailView()
        app.query_one = MethodType(lambda _self, _selector, *a, **k: detail_view, app)

        with mock.patch("textual.containers.Vertical", FakeVertical):
            with mock.patch("textual.widgets.Input", FakeInputWidget):
                with mock.patch("textual.widgets.Button", FakeButton):
                    app._show_path_check_tab(config)

        form = next((child for child in detail_view.children if getattr(child, "id", "") == "path-form"), None)
        self.assertIsNotNone(form, "Path form container should be mounted")
        self.assertGreater(len(form.children), 0, "Form should include input controls")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
