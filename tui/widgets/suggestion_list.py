"""Suggestion list widget showing ranked search results."""

from __future__ import annotations

from typing import Any, Dict, List

from textual.widgets import Static
from textual.containers import VerticalScroll
from rich.text import Text


class SuggestionList(VerticalScroll):
    """Scrollable list of search suggestions with type badges."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.results: List[Dict[str, Any]] = []

    def compose(self):
        """Compose child widgets."""
        # Yield initial placeholder
        yield Static("Start typing to search...", classes="suggestions-placeholder")

    def update_results(self, results: List[Dict[str, Any]]) -> None:
        """Update the displayed suggestions."""
        self.results = results

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
        for idx, result in enumerate(results):
            result_text = self._format_result(result, idx == 0)
            self.mount(Static(result_text, classes="suggestion-item"))

    def _format_result(self, result: Dict[str, Any], is_selected: bool) -> Text:
        """Format a single result for display."""
        name = result.get("name", "Unknown")
        obj_type = result.get("type", "unknown")
        detail = result.get("detail", "")

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

        # Detail
        if detail:
            text.append(f"  {detail}", style="dim")

        return text
