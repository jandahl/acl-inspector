"""Main menu modal screen for TUI."""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Static, Label
from textual.containers import Container, Vertical, Grid
from rich.text import Text


class MenuScreen(ModalScreen):
    """Modal screen showing main menu options."""

    CSS = """
    MenuScreen {
        align: center middle;
    }

    #menu-dialog {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #menu-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: $accent;
        padding: 1 0;
    }

    .menu-button {
        width: 100%;
        margin: 0 0 1 0;
    }

    .menu-button:focus {
        background: $accent;
        color: $background;
        border: tall $accent;
        text-style: bold;
    }

    .menu-section {
        width: 100%;
        padding: 1 0;
        border-top: solid $primary;
    }

    .menu-info {
        width: 100%;
        padding: 0 0 1 0;
        color: $text-muted;
    }
    """

    def __init__(self, current_theme: str = "textual-dark", config_info: str = ""):
        super().__init__()
        self.current_theme = current_theme
        self.config_info = config_info

    def compose(self) -> ComposeResult:
        """Compose the menu dialog."""
        with Container(id="menu-dialog"):
            yield Label("ACL-inspector Menu", id="menu-title")

            # Config info
            if self.config_info:
                yield Static(self.config_info, classes="menu-info")

            # Main actions
            yield Button("Help & Shortcuts", id="menu-help", classes="menu-button", variant="primary")
            yield Button("About ACL-inspector", id="menu-about", classes="menu-button")
            yield Button("Settings", id="menu-settings", classes="menu-button")

            # Theme section
            with Vertical(classes="menu-section"):
                yield Static("Theme", classes="menu-info")
                theme_label = "Light" if self.current_theme == "textual-light" else "Dark"
                yield Button(f"Toggle Theme (Currently: {theme_label})", id="menu-theme", classes="menu-button")

            # Close button
            yield Button("Close Menu", id="menu-close", classes="menu-button", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "menu-close":
            self.dismiss(None)
        elif button_id == "menu-help":
            self.dismiss("help")
        elif button_id == "menu-about":
            self.dismiss("about")
        elif button_id == "menu-settings":
            self.dismiss("settings")
        elif button_id == "menu-theme":
            self.dismiss("theme")

    def on_mount(self) -> None:
        """Focus first button when menu opens."""
        help_button = self.query_one("#menu-help")
        help_button.focus()

    def on_key(self, event) -> None:
        """Handle key presses."""
        if event.key == "escape":
            self.dismiss(None)
        elif event.key in ("down", "up"):
            self._focus_relative(1 if event.key == "down" else -1)
            event.prevent_default()

    def _focus_relative(self, delta: int) -> None:
        """Move focus between buttons."""
        buttons = list(self.query(Button))
        if not buttons:
            return
        try:
            current_index = next(i for i, btn in enumerate(buttons) if btn.has_focus)
        except StopIteration:
            current_index = 0 if delta > 0 else len(buttons) - 1
        next_index = (current_index + delta) % len(buttons)
        buttons[next_index].focus()
