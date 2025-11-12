"""Suggestion list widget showing ranked search results."""

from __future__ import annotations

from typing import Any, Dict, List

from textual.widgets import Static
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text


class SuggestionList(VerticalScroll):
    """Scrollable list of search suggestions with type badges."""

    class ItemSelected(Message):
        """Posted when an item is selected (Enter pressed)."""

        def __init__(self, item: Dict[str, Any]) -> None:
            self.item = item
            super().__init__()

    selected_index = reactive(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.results: List[Dict[str, Any]] = []
        self.can_focus = True

    def compose(self):
        """Compose child widgets."""
        # Yield initial placeholder
        yield Static("Start typing to search...", classes="suggestions-placeholder")

    def update_results(self, results: List[Dict[str, Any]]) -> None:
        """Update the displayed suggestions."""
        self.results = results
        self.selected_index = 0  # Reset selection

        # Clear existing children
        try:
            self.remove_children()
        except Exception:
            # In case there's an issue removing children, just continue
            pass

        if not results:
            self.mount(Static("Start typing to search...", classes="suggestions-placeholder"))
            return

        # Add result items
        self._render_results()

    def _render_results(self) -> None:
        """Render all results with current selection."""
        self.remove_children()
        for idx, result in enumerate(self.results):
            is_selected = (idx == self.selected_index)
            result_text = self._format_result(result, is_selected)
            self.mount(Static(result_text, classes="suggestion-item"))

    def watch_selected_index(self, old_value: int, new_value: int) -> None:
        """Re-render when selection changes."""
        if self.results:
            self._render_results()

    def on_key(self, event) -> None:
        """Handle keyboard navigation."""
        if not self.results:
            return

        if event.key == "down" or event.key == "j":
            self.selected_index = min(len(self.results) - 1, self.selected_index + 1)
            event.prevent_default()
        elif event.key == "up" or event.key == "k":
            self.selected_index = max(0, self.selected_index - 1)
            event.prevent_default()
        elif event.key == "enter":
            if 0 <= self.selected_index < len(self.results):
                self.post_message(self.ItemSelected(self.results[self.selected_index]))
            event.prevent_default()

    def _format_result(self, result: Dict[str, Any], is_selected: bool) -> Text:
        """Format a single result for display."""
        name = result.get("name", "Unknown")
        obj_type = result.get("type", "unknown")
        detail = result.get("detail", "")
        source_file = result.get("source_file", "")

        # Type badge colors
        type_colors = {
            "object": "cyan",
            "group": "blue",
            "acl": "magenta",
            "literal": "yellow",
            "context": "green",
        }
        type_color = type_colors.get(obj_type, "white")

        # Build formatted text
        text = Text()

        # Selection indicator
        if is_selected:
            text.append("▶ ", style="bold yellow")
        else:
            text.append("  ")

        # Name
        text.append(f"{name:30s}", style="bold")

        # Type badge
        text.append(f"[{obj_type:8s}]", style=type_color)

        # Source file (if available and multi-config mode)
        if source_file:
            text.append(f" [{source_file}]", style="dim italic")

        # Detail
        if detail:
            text.append(f"  {detail}", style="dim")

        return text
