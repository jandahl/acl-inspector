# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Export dialog screen for exporting tab data."""

from __future__ import annotations

from typing import Any, Dict, Optional, Callable
from pathlib import Path

from textual.screen import ModalScreen
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Button, Static, Input, RadioSet, RadioButton, Label
from textual.binding import Binding
from rich.text import Text


class ExportScreen(ModalScreen):
    """Modal screen for exporting data."""

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel", show=False),
    ]

    CSS = """
    ExportScreen {
        align: center middle;
    }

    #export-dialog {
        width: 70;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 1 2;
    }

    .export-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .export-section {
        margin-top: 1;
        margin-bottom: 1;
    }

    .export-label {
        text-style: bold;
        color: $text;
    }

    #export-buttons {
        align: center middle;
        margin-top: 1;
    }

    Button {
        min-width: 16;
        margin: 0 1;
    }

    Input {
        margin-top: 1;
    }

    RadioSet {
        margin-top: 1;
        background: $surface;
        padding: 1;
    }
    """

    def __init__(
        self,
        tab_name: str,
        object_name: str,
        data: Any,
        export_callback: Callable[[str, str], None],
        **kwargs
    ):
        """Initialize export screen.

        Args:
            tab_name: Name of the tab being exported
            object_name: Name of the object
            data: Data to export
            export_callback: Callback function(format, filepath)
        """
        super().__init__(**kwargs)
        self.tab_name = tab_name
        self.object_name = object_name
        self.data = data
        self.export_callback = export_callback

        # Generate default filename (FIX #6: default to txt)
        from ..utils.export import ExportManager
        self.default_filename = ExportManager.get_export_filename(
            tab_name, object_name, "txt"
        )

    def compose(self):
        """Compose the export dialog."""
        with Container(id="export-dialog"):
            yield Static("Export Data", classes="export-title")

            # Tab and object info
            info = Text()
            info.append("Tab: ", style="yellow")
            info.append(f"{self.tab_name}\n", style="white")
            info.append("Object: ", style="yellow")
            info.append(f"{self.object_name}\n", style="white")
            yield Static(info, classes="export-section")

            # Format selection (FIX #6: default to Plain Text)
            yield Label("Export Format:", classes="export-label export-section")
            with RadioSet(id="format-select"):
                yield RadioButton("Plain Text (.txt)", value=True, id="format-txt")
                yield RadioButton("JSON (.json)", id="format-json")
                yield RadioButton("CSV (.csv)", id="format-csv")

            # Filename input
            yield Label("Filename:", classes="export-label export-section")
            yield Input(
                value=self.default_filename,
                placeholder="Enter filename...",
                id="filename-input"
            )

            # Buttons
            with Horizontal(id="export-buttons"):
                yield Button("Export", variant="primary", id="btn-export")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Update filename extension when format changes."""
        format_id = event.pressed.id if event.pressed else "format-txt"

        # Determine file extension (FIX #6: default to txt)
        ext_map = {
            "format-txt": "txt",
            "format-json": "json",
            "format-csv": "csv",
        }
        ext = ext_map.get(format_id, "txt")

        # Update filename input
        filename_input = self.query_one("#filename-input", Input)
        current_name = filename_input.value

        # Replace extension
        from ..utils.export import ExportManager
        new_name = ExportManager.get_export_filename(
            self.tab_name, self.object_name, ext
        )
        filename_input.value = new_name

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "btn-export":
            self._do_export()
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def _do_export(self) -> None:
        """Perform the export operation."""
        # Get selected format
        radio_set = self.query_one("#format-select", RadioSet)
        pressed_button = radio_set.pressed_button

        if not pressed_button:
            self.app.notify("Please select an export format", severity="error")
            return

        format_map = {
            "format-txt": "txt",
            "format-json": "json",
            "format-csv": "csv",
        }
        format_type = format_map.get(pressed_button.id, "txt")

        # Get filename
        filename_input = self.query_one("#filename-input", Input)
        filename = filename_input.value.strip()

        if not filename:
            self.app.notify("Please enter a filename", severity="error")
            return

        # Call export callback
        try:
            self.export_callback(format_type, filename)
            self.dismiss({"format": format_type, "filename": filename})
        except Exception as e:
            self.app.notify(f"Export failed: {str(e)}", severity="error", timeout=10)

    def action_dismiss(self) -> None:
        """Handle ESC key to cancel."""
        self.dismiss(None)
