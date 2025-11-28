"""Tests covering the CLI alias that launches the Singularity TUI."""

import importlib.util
import sys
import uuid
from pathlib import Path
import unittest
from unittest import mock


try:
    import textual  # noqa: F401
    TEXTUAL_AVAILABLE = True
except ImportError:  # pragma: no cover - textual optional in CI
    TEXTUAL_AVAILABLE = False


def load_cli_module():
    """Load the CLI script as a fresh module for each test."""
    root = Path(__file__).resolve().parent.parent
    path = root / "cli/access-list-inspector.py"
    name = f"access_list_inspector_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


class SingularityAliasTest(unittest.TestCase):
    """Ensure the CLI alias routes to the TUI runner."""

    def test_singularitty_invokes_tui_with_custom_args(self):
        if not TEXTUAL_AVAILABLE:
            self.skipTest("textual not installed")
        module = load_cli_module()
        tui_args = ["--vendor", "fortigate", "--config", "configs/sample.conf", "--vdom", "root"]
        argv = ["cli/access-list-inspector.py", "--singularitty"] + tui_args
        with mock.patch("tui.app.main") as tui_main:
            with mock.patch.object(sys, "argv", argv):
                module.main()
        tui_main.assert_called_once_with(argv=tui_args)

    def test_singularitty_defaults_to_tui_from_cli(self):
        if not TEXTUAL_AVAILABLE:
            self.skipTest("textual not installed")
        module = load_cli_module()
        argv = ["cli/access-list-inspector.py", "--singularitty"]
        with mock.patch("tui.app.main") as tui_main:
            with mock.patch.object(sys, "argv", argv):
                module.main()
        tui_main.assert_called_once_with(argv=None)


if __name__ == "__main__":
    unittest.main()
