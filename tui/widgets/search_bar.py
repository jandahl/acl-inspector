"""Search bar widget with real-time input and debounced search."""

from __future__ import annotations

import asyncio

from textual import work, on
from textual.widgets import Input
from textual.message import Message


class SearchBar(Input):
    """Search input widget with debounced search triggering."""

    class Searched(Message):
        """Posted when debounced search should be triggered."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """React to input changes with debounce."""
        # Trigger debounced search
        self._trigger_search(event.value)

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
