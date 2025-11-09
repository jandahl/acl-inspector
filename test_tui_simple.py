#!/usr/bin/env python3
"""Simple TUI test to verify Input widget works."""

from textual.app import App
from textual.widgets import Header, Input, Static
from textual.containers import Vertical


class SimpleTestApp(App):
    """Minimal TUI to test input display."""

    def compose(self):
        yield Header(show_clock=True)
        yield Static("Type something below:")
        yield Input(placeholder="Type here...")
        yield Static("", id="output")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Show what was typed."""
        output = self.query_one("#output", Static)
        output.update(f"You typed: '{event.value}'")


if __name__ == "__main__":
    app = SimpleTestApp()
    app.run()
