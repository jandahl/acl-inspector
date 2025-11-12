"""Help screen showing keyboard shortcuts and usage."""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Button
from textual.containers import Container, Vertical, VerticalScroll
from rich.text import Text
from rich.table import Table


class HelpScreen(ModalScreen):
    """Modal screen showing help and keyboard shortcuts."""

    CSS = """
    HelpScreen {
        align: center middle;
    }

    #help-dialog {
        width: 1fr;
        height: 1fr;
        margin: 2 5;
        border: thick $primary;
        background: $surface;
    }

    #help-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: $accent;
        padding: 1;
        background: $panel;
    }

    #help-content {
        width: 100%;
        height: 1fr;
        padding: 1 2;
    }

    #help-close {
        dock: bottom;
        width: 100%;
        margin: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the help dialog."""
        with Container(id="help-dialog"):
            yield Static("Help & Keyboard Shortcuts", id="help-title")

            with VerticalScroll(id="help-content"):
                yield Static(self._create_help_content())

            yield Button("Close", id="help-close", variant="primary")

    def _create_help_content(self) -> Table:
        """Create the help content table."""
        table = Table(show_header=True, header_style="bold cyan", expand=True)
        table.add_column("Context", style="yellow", width=20)
        table.add_column("Key", style="green", width=15)
        table.add_column("Action", style="white")

        # Global shortcuts
        table.add_row("[bold]Global[/bold]", "", "")
        table.add_row("", "Ctrl+Q", "Quit application")
        table.add_row("", "Ctrl+O", "Open menu")
        table.add_row("", "F1", "Show this help")
        table.add_row("", "Ctrl+T", "Toggle theme")
        table.add_row("", "ESC", "Close modal / Clear search")
        table.add_row("", "Tab", "Navigate between widgets")
        table.add_row("", "Up/Down or j/k", "Navigate menu/lists")

        # Search mode
        table.add_row("", "", "")
        table.add_row("[bold]Search Mode[/bold]", "", "")
        table.add_row("", "Type", "Start searching")
        table.add_row("", "/", "Focus search bar")
        table.add_row("", "Up/Down or j/k", "Navigate results")
        table.add_row("", "Enter", "Select and drill down")
        table.add_row("", "ESC", "Clear search")

        # Drill-down mode
        table.add_row("", "", "")
        table.add_row("[bold]Drill-down Mode[/bold]", "", "")
        table.add_row("", "Left/Right", "Switch tabs")
        table.add_row("", "Tab", "Navigate widgets")
        table.add_row("", "ESC", "Exit drill-down")

        # Compare mode
        table.add_row("", "", "")
        table.add_row("[bold]Compare Mode[/bold]", "", "")
        table.add_row("", "Type", "Filter suggestions")
        table.add_row("", "Enter", "Execute comparison")
        table.add_row("", "ESC", "Cancel")

        return table

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "help-close":
            self.dismiss()

    def on_key(self, event) -> None:
        """Handle key presses."""
        if event.key == "escape":
            self.dismiss()
