"""Filter bar widget for Inspect tab."""

from __future__ import annotations

from typing import Optional, Dict, Any

from textual.widgets import Static, Input, Select, Button
from textual.containers import Horizontal, Vertical
from textual.message import Message
from rich.text import Text


class FilterBar(Vertical):
    """Filter bar for Inspect tab with protocol/port/direction filters."""

    class FilterChanged(Message):
        """Posted when filter values change."""

        def __init__(self, filters: Dict[str, Any]) -> None:
            self.filters = filters
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_filters: Dict[str, Any] = {
            "protocol": None,
            "port": None,
            "direction": None,
            "action": None,
        }
        self.classes = "filter-bar"

    def compose(self):
        """Compose filter widgets."""
        # Title
        yield Static("Filters:", classes="filter-label")

        # Filter controls
        with Horizontal(classes="filter-controls"):
            # Protocol filter
            yield Static("Protocol:", classes="filter-field-label")
            yield Input(
                placeholder="tcp, udp, icmp, any",
                id="filter-protocol",
                classes="filter-input"
            )

            # Port filter
            yield Static("Port:", classes="filter-field-label")
            yield Input(
                placeholder="80, 443, 22",
                id="filter-port",
                classes="filter-input"
            )

            # Action filter
            yield Static("Action:", classes="filter-field-label")
            yield Input(
                placeholder="permit, deny",
                id="filter-action",
                classes="filter-input"
            )

        # Buttons
        with Horizontal(classes="filter-buttons"):
            yield Button("Apply Filters", variant="primary", id="btn-apply-filters")
            yield Button("Clear Filters", variant="default", id="btn-clear-filters")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-apply-filters":
            self._apply_filters()
        elif event.button.id == "btn-clear-filters":
            self._clear_filters()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in filter inputs."""
        # Apply filters when Enter is pressed
        self._apply_filters()

    def _apply_filters(self) -> None:
        """Apply current filter values."""
        # Get filter values
        protocol_input = self.query_one("#filter-protocol", Input)
        port_input = self.query_one("#filter-port", Input)
        action_input = self.query_one("#filter-action", Input)

        protocol = protocol_input.value.strip().lower() or None
        port_str = port_input.value.strip()
        action = action_input.value.strip().lower() or None

        # Parse port
        port = None
        if port_str:
            try:
                port = int(port_str)
            except ValueError:
                self.app.notify(f"Invalid port number: {port_str}", severity="error")
                return

        # Validate protocol
        if protocol and protocol not in ("tcp", "udp", "icmp", "ip", "any"):
            self.app.notify(
                f"Invalid protocol: {protocol}. Use tcp, udp, icmp, ip, or any",
                severity="warning"
            )
            # Still allow it, in case it's a valid protocol number

        # Validate action
        if action and action not in ("permit", "deny"):
            self.app.notify(
                f"Invalid action: {action}. Use permit or deny",
                severity="warning"
            )

        # Update current filters
        self.current_filters = {
            "protocol": protocol,
            "port": port,
            "action": action,
        }

        # Post message
        self.post_message(self.FilterChanged(self.current_filters))

        # Show notification
        filter_desc = []
        if protocol:
            filter_desc.append(f"protocol={protocol}")
        if port:
            filter_desc.append(f"port={port}")
        if action:
            filter_desc.append(f"action={action}")

        if filter_desc:
            self.app.notify(f"Filters applied: {', '.join(filter_desc)}", severity="information")
        else:
            self.app.notify("No filters applied (showing all results)", severity="information")

    def _clear_filters(self) -> None:
        """Clear all filter values."""
        # Clear inputs
        self.query_one("#filter-protocol", Input).value = ""
        self.query_one("#filter-port", Input).value = ""
        self.query_one("#filter-action", Input).value = ""

        # Reset current filters
        self.current_filters = {
            "protocol": None,
            "port": None,
            "action": None,
        }

        # Post message
        self.post_message(self.FilterChanged(self.current_filters))

        # Show notification
        self.app.notify("Filters cleared", severity="information")

    def get_filters(self) -> Dict[str, Any]:
        """Get current filter values.

        Returns:
            Dictionary of active filters
        """
        return self.current_filters
