"""Search bar widget with real-time input and debounced search."""

from __future__ import annotations

import asyncio

from textual import work
from textual.widgets import Input
from textual.message import Message


class SearchBar(Input):
    """Search input widget with debounced search triggering."""

    class Searched(Message):
        """Posted when debounced search should be triggered."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def watch_value(self, value: str) -> None:
        """React to value changes with debounce."""
        # Use work decorator to debounce
        self._trigger_search(value)

    @work(exclusive=True)
    async def _trigger_search(self, value: str) -> None:
        """Debounced search trigger."""
        # Wait 250ms before posting search message
        await asyncio.sleep(0.25)
        self.post_message(self.Searched(value))

    def action_clear(self) -> None:
        """Clear the search field."""
        self.value = ""
        self.post_message(self.Searched(""))
