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
