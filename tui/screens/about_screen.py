# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""About screen showing version and credits."""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Button
from textual.containers import Container, Vertical
from rich.text import Text
from rich.panel import Panel


class AboutScreen(ModalScreen):
    """Modal screen showing about information."""

    CSS = """
    AboutScreen {
        align: center middle;
    }

    #about-dialog {
        width: 1fr;
        height: 1fr;
        margin: 2 5;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #about-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: $accent;
        padding: 1;
    }

    #about-content {
        width: 100%;
        padding: 1 2;
    }

    #about-close {
        width: 100%;
        margin: 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the about dialog."""
        with Container(id="about-dialog"):
            yield Static("About ACL-inspector", id="about-title")

            with Vertical(id="about-content"):
                yield Static(self._create_about_content())

            yield Button("Close", id="about-close", variant="primary")

    def _create_about_content(self) -> Text:
        """Create the about content."""
        text = Text()

        # Title
        text.append("ACL-inspector\n", style="bold cyan")
        text.append("Singularity TUI\n\n", style="bold white")

        # Description
        text.append(
            "A Python tool for analyzing firewall configurations.\n"
            "Parse, inspect, and compare ACLs from Cisco ASA and FortiGate firewalls.\n\n",
            style="white"
        )

        # Features
        text.append("Features:\n", style="bold yellow")
        text.append("  • Search-first interface with fuzzy matching\n", style="dim")
        text.append("  • Object inspection and ACL analysis\n", style="dim")
        text.append("  • Compare configurations side-by-side\n", style="dim")
        text.append("  • Multi-vendor support (ASA, FortiGate)\n", style="dim")
        text.append("  • Network object resolution and duplicate detection\n\n", style="dim")

        # Tech stack
        text.append("Built with:\n", style="bold yellow")
        text.append("  • Python 3.9+\n", style="dim")
        text.append("  • Textual (Terminal UI framework)\n", style="dim")
        text.append("  • Rich (Terminal formatting)\n\n", style="dim")

        # Repository
        text.append("Project: ", style="bold yellow")
        text.append("github.com/your-repo/ACL-inspector\n\n", style="cyan underline")

        text.append("Press ESC or Close to return", style="dim italic")

        return text

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "about-close":
            self.dismiss()

    def on_key(self, event) -> None:
        """Handle key presses."""
        if event.key == "escape":
            self.dismiss()
