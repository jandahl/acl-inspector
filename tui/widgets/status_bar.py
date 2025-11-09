"""Status bar widget showing key bindings and status."""

from __future__ import annotations

from textual.widgets import Static
from rich.text import Text


class StatusBar(Static):
    """Bottom status bar with key binding hints."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.update_bindings()

    def update_bindings(self, mode: str = "search") -> None:
        """Update displayed key bindings based on current mode."""
        bindings = {
            "search": [
                ("↑↓", "Navigate"),
                ("Enter", "Select"),
                ("ESC", "Clear"),
                ("Q", "Quit"),
            ],
            "detail": [
                ("TAB", "Switch Pane"),
                ("A", "Analyze"),
                ("C", "Compare"),
                ("Q", "Back"),
            ],
        }

        binding_list = bindings.get(mode, bindings["search"])

        text = Text()
        for idx, (key, action) in enumerate(binding_list):
            if idx > 0:
                text.append(" │ ", style="dim")
            text.append(f"{key} ", style="bold cyan")
            text.append(action, style="white")

        self.update(text)
