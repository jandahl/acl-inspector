"""Interactive settings screen with editable controls."""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Static, Label, OptionList, Select, Input, Switch
from textual.widgets.option_list import Option
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.binding import Binding
from rich.text import Text
from typing import Dict, Any


class SettingsScreen(ModalScreen):
    """Modal screen for managing TUI settings."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    CSS = """
    SettingsScreen {
        align: center middle;
    }

    #settings-dialog {
        width: 1fr;
        height: 1fr;
        margin: 2 5;
        border: thick $primary;
        background: $surface;
    }

    #settings-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: $accent;
        padding: 1;
        background: $panel;
    }

    #settings-content {
        layout: horizontal;
        width: 100%;
        height: 1fr;
    }

    #settings-categories {
        width: 30;
        height: 100%;
        border-right: solid $primary;
        padding: 1;
    }

    #settings-options {
        width: 1fr;
        height: 100%;
        padding: 1 2;
    }

    #settings-buttons {
        dock: bottom;
        width: 100%;
        height: auto;
        layout: horizontal;
        padding: 1;
        background: $panel;
    }

    .settings-button {
        width: 1fr;
        margin: 0 1;
    }

    .category-list {
        width: 100%;
        height: 1fr;
    }

    .setting-row {
        layout: horizontal;
        width: 100%;
        height: auto;
        margin: 1 0;
        padding: 0 1;
    }

    .setting-label {
        width: 30%;
        height: auto;
        padding: 0 1 0 0;
        color: $text;
    }

    .setting-control {
        width: 70%;
        height: auto;
    }

    .setting-description {
        width: 100%;
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
        color: $text-muted;
    }

    .category-title {
        width: 100%;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    Select {
        width: 100%;
    }

    Input {
        width: 100%;
    }

    Switch {
        width: auto;
    }
    """

    def __init__(self, settings_manager):
        """Initialize settings screen.

        Args:
            settings_manager: TUISettings instance
        """
        super().__init__()
        self.settings_manager = settings_manager
        self.current_category = "display"
        self.categories = [
            ("display", "Display Settings"),
            ("search", "Search Settings"),
            ("config", "Config Settings"),
            ("advanced", "Advanced"),
        ]
        # Track pending changes
        self.pending_changes: Dict[str, Dict[str, Any]] = {
            "display": {},
            "search": {},
            "config": {},
            "advanced": {},
        }

    def compose(self) -> ComposeResult:
        """Compose the settings dialog."""
        with Container(id="settings-dialog"):
            yield Label("Settings", id="settings-title")

            with Horizontal(id="settings-content"):
                # Left: Category list
                with Vertical(id="settings-categories"):
                    yield Static("Categories:", classes="category-title")
                    yield OptionList(
                        *[Option(label) for _, label in self.categories],
                        id="category-list",
                        classes="category-list"
                    )

                # Right: Options for selected category (scrollable)
                with VerticalScroll(id="settings-options"):
                    pass  # Will be populated dynamically

            # Bottom: Action buttons
            with Horizontal(id="settings-buttons"):
                yield Button("Apply", id="settings-apply", classes="settings-button", variant="primary")
                yield Button("Reset Category", id="settings-reset-cat", classes="settings-button")
                yield Button("Reset All", id="settings-reset-all", classes="settings-button")
                yield Button("Cancel", id="settings-cancel", classes="settings-button", variant="error")

    def on_mount(self) -> None:
        """Initialize when mounted."""
        # Select first category
        category_list = self.query_one("#category-list", OptionList)
        category_list.highlighted = 0
        category_list.focus()
        self._show_category_options("display")

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Handle category highlight change (instant switching)."""
        if event.option_list.id == "category-list" and event.option_index is not None:
            # Map index to category ID
            category_id, _ = self.categories[event.option_index]
            self.current_category = category_id
            self._show_category_options(category_id)

    def _show_category_options(self, category: str) -> None:
        """Display editable options for the selected category.

        Args:
            category: Category ID (display, search, config, advanced)
        """
        options_container = self.query_one("#settings-options", VerticalScroll)

        # Clear existing widgets
        options_container.remove_children()

        # Add category title
        title_text = dict(self.categories).get(category, "Settings")
        options_container.mount(Static(title_text, classes="category-title"))

        # Build appropriate widgets for this category
        if category == "display":
            self._build_display_widgets(options_container)
        elif category == "search":
            self._build_search_widgets(options_container)
        elif category == "config":
            self._build_config_widgets(options_container)
        elif category == "advanced":
            self._build_advanced_widgets(options_container)

    def _build_display_widgets(self, container: VerticalScroll) -> None:
        """Build display settings widgets."""
        # Theme (informational - toggle with Ctrl+T)
        theme = self.settings_manager.get("display", "theme", "textual-dark")
        theme_label = "Dark" if theme == "textual-dark" else "Light"

        container.mount(Static("Theme (toggle with Ctrl+T)", classes="setting-label"))
        container.mount(Static(f"Current: {theme_label}", classes="setting-description"))

        # Show line numbers
        show_lines = self.settings_manager.get("display", "show_line_numbers", True)

        with container:
            with Horizontal(classes="setting-row"):
                yield Label("Show line numbers", classes="setting-label")
                yield Switch(value=show_lines, id="setting-display-show_line_numbers", classes="setting-control")
            yield Static("Display line numbers in detail views", classes="setting-description")

        # Results per page
        results = self.settings_manager.get("display", "results_per_page", 20)

        with container:
            with Horizontal(classes="setting-row"):
                yield Label("Results per page", classes="setting-label")
                yield Select(
                    [("10", 10), ("20", 20), ("50", 50), ("100", 100)],
                    value=results,
                    id="setting-display-results_per_page",
                    classes="setting-control"
                )
            yield Static("Number of search results to display", classes="setting-description")

        # Source file display
        source_display = self.settings_manager.get("display", "source_file_display", "auto")

        with container:
            with Horizontal(classes="setting-row"):
                yield Label("Source file display", classes="setting-label")
                yield Select(
                    [("Auto (multi-config only)", "auto"), ("Always", "always"), ("Never", "never")],
                    value=source_display,
                    id="setting-display-source_file_display",
                    classes="setting-control"
                )
            yield Static("When to show config file source", classes="setting-description")

    def _build_search_widgets(self, container: VerticalScroll) -> None:
        """Build search settings widgets."""
        # Search mode
        mode = self.settings_manager.get("search", "mode", "fuzzy")

        with container:
            with Horizontal(classes="setting-row"):
                yield Label("Search mode", classes="setting-label")
                yield Select(
                    [("Fuzzy (substring)", "fuzzy"), ("Prefix", "prefix"), ("Exact", "exact")],
                    value=mode,
                    id="setting-search-mode",
                    classes="setting-control"
                )
            yield Static("Fuzzy mode is recommended for most use cases", classes="setting-description")

        # Case sensitive
        case_sens = self.settings_manager.get("search", "case_sensitive", False)

        with container:
            with Horizontal(classes="setting-row"):
                yield Label("Case sensitive", classes="setting-label")
                yield Switch(value=case_sens, id="setting-search-case_sensitive", classes="setting-control")
            yield Static("When disabled, search ignores case", classes="setting-description")

        # Max results
        max_results = self.settings_manager.get("search", "max_results", 50)

        with container:
            with Horizontal(classes="setting-row"):
                yield Label("Max results", classes="setting-label")
                yield Select(
                    [("20", 20), ("50", 50), ("100", 100), ("500", 500)],
                    value=max_results,
                    id="setting-search-max_results",
                    classes="setting-control"
                )
            yield Static("Higher values may slow down large configs", classes="setting-description")

    def _build_config_widgets(self, container: VerticalScroll) -> None:
        """Build config settings widgets (informational only)."""
        # Last vendor
        vendor = self.settings_manager.get("config", "last_vendor", "asa")

        container.mount(Static(f"\nLast vendor: {vendor.upper()}", classes="setting-description"))

        # Last path
        last_path = self.settings_manager.get("config", "last_path", "")
        container.mount(Static(f"Last config path: {last_path if last_path else '(none)'}", classes="setting-description"))

        # Auto reload
        auto_reload = self.settings_manager.get("config", "auto_reload", False)

        with container:
            with Horizontal(classes="setting-row"):
                yield Label("Auto reload", classes="setting-label")
                yield Switch(value=auto_reload, id="setting-config-auto_reload", classes="setting-control")
            yield Static("Automatically reload config on file changes", classes="setting-description")

        container.mount(Static("\nNote: Config loading is managed at startup.", classes="setting-description"))

    def _build_advanced_widgets(self, container: VerticalScroll) -> None:
        """Build advanced settings widgets."""
        # Logging enabled
        logging_enabled = self.settings_manager.get("advanced", "enable_logging", True)

        with container:
            with Horizontal(classes="setting-row"):
                yield Label("Enable logging", classes="setting-label")
                yield Switch(value=logging_enabled, id="setting-advanced-enable_logging", classes="setting-control")
            yield Static("Write diagnostic logs to logs/ directory", classes="setting-description")

        # Log level
        log_level = self.settings_manager.get("advanced", "log_level", "INFO")

        with container:
            with Horizontal(classes="setting-row"):
                yield Label("Log level", classes="setting-label")
                yield Select(
                    [("DEBUG", "DEBUG"), ("INFO", "INFO"), ("WARNING", "WARNING"), ("ERROR", "ERROR")],
                    value=log_level,
                    id="setting-advanced-log_level",
                    classes="setting-control"
                )
            yield Static("Verbosity of log messages", classes="setting-description")

        # Cache enabled
        cache_enabled = self.settings_manager.get("advanced", "cache_enabled", True)

        with container:
            with Horizontal(classes="setting-row"):
                yield Label("Cache enabled", classes="setting-label")
                yield Switch(value=cache_enabled, id="setting-advanced-cache_enabled", classes="setting-control")
            yield Static("Enable disk cache for faster startup", classes="setting-description")

        container.mount(Static("\nNote: Advanced settings require restart to take effect.", classes="setting-description"))

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select widget changes."""
        # Parse widget ID to get category and key
        # Format: setting-{category}-{key}
        widget_id = event.select.id
        if not widget_id or not widget_id.startswith("setting-"):
            return

        parts = widget_id.split("-", 2)
        if len(parts) != 3:
            return

        _, category, key = parts

        # Store pending change
        if category not in self.pending_changes:
            self.pending_changes[category] = {}

        self.pending_changes[category][key] = event.value

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle switch widget changes."""
        # Parse widget ID to get category and key
        widget_id = event.switch.id
        if not widget_id or not widget_id.startswith("setting-"):
            return

        parts = widget_id.split("-", 2)
        if len(parts) != 3:
            return

        _, category, key = parts

        # Store pending change
        if category not in self.pending_changes:
            self.pending_changes[category] = {}

        self.pending_changes[category][key] = event.value

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input widget changes."""
        # Parse widget ID to get category and key
        widget_id = event.input.id
        if not widget_id or not widget_id.startswith("setting-"):
            return

        parts = widget_id.split("-", 2)
        if len(parts) != 3:
            return

        _, category, key = parts

        # Store pending change
        if category not in self.pending_changes:
            self.pending_changes[category] = {}

        self.pending_changes[category][key] = event.value

    def _apply_pending_changes(self) -> None:
        """Apply all pending changes to settings manager."""
        for category, changes in self.pending_changes.items():
            for key, value in changes.items():
                self.settings_manager.set(category, key, value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "settings-cancel":
            self.dismiss(None)
        elif button_id == "settings-apply":
            # Apply pending changes and save
            self._apply_pending_changes()
            if self.settings_manager.save():
                self.dismiss("saved")
            else:
                self.dismiss("error")
        elif button_id == "settings-reset-cat":
            # Reset current category
            self.settings_manager.reset_category(self.current_category)
            # Clear pending changes for this category
            self.pending_changes[self.current_category] = {}
            # Refresh display
            self._show_category_options(self.current_category)
            self.app.notify(f"Reset {self.current_category} settings to defaults", severity="information")
        elif button_id == "settings-reset-all":
            # Reset all settings
            self.settings_manager.reset_to_defaults()
            # Clear all pending changes
            self.pending_changes = {cat: {} for cat, _ in self.categories}
            # Refresh display
            self._show_category_options(self.current_category)
            self.app.notify("Reset all settings to defaults", severity="information")

    def action_cancel(self) -> None:
        """Handle ESC key to cancel."""
        self.dismiss(None)
