"""Main Textual application for Singularity TUI."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Static, Input
from textual.binding import Binding

from .widgets.search_bar import SearchBar
from .widgets.suggestion_list import SuggestionList
from .widgets.status_bar import StatusBar


class SingularityApp(App):
    """ACL-inspector Singularity TUI main application."""

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        width: 100%;
        height: 100%;
        background: $surface;
    }

    #search-container {
        width: 100%;
        height: 3;
        padding: 1 2;
        background: $panel;
    }

    #suggestions-container {
        width: 100%;
        height: 1fr;
        padding: 0 2;
        background: $surface;
    }

    #status-container {
        width: 100%;
        height: 1;
        background: $accent;
        color: $text;
    }

    .title {
        text-align: center;
        color: $primary;
        text-style: bold;
    }
    """

    TITLE = "ACL-inspector Singularity TUI"
    SUB_TITLE = "Search-first firewall configuration analysis"

    BINDINGS = [
        Binding("ctrl+c,q", "quit", "Quit", show=True),
        Binding("ctrl+r", "refresh", "Refresh", show=True),
        Binding("/", "focus_search", "Search", show=True),
        Binding("?", "help", "Help", show=True),
        Binding("escape", "clear_search", "Clear", show=False),
    ]

    def __init__(self, vendor: str = "asa", config_path: str = ""):
        super().__init__()
        self.vendor = vendor
        self.config_path = config_path
        self.search_results = []

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(show_clock=True)

        with Container(id="main-container"):
            # Search section
            with Vertical(id="search-container"):
                yield Static(f"[{self.vendor.upper()}] {self.config_path or 'No config loaded'}", classes="title")
                yield SearchBar(placeholder="Type to search objects, ACLs, hosts...")

            # Suggestions section
            with Vertical(id="suggestions-container"):
                yield SuggestionList()

        # Status bar at bottom
        yield StatusBar()

    def on_mount(self) -> None:
        """Called when app starts."""
        self.title = self.TITLE
        self.sub_title = self.SUB_TITLE
        # Focus search bar on startup
        self.query_one(SearchBar).focus()

    def on_search_bar_searched(self, message: SearchBar.Searched) -> None:
        """Handle debounced search events."""
        query = message.value.strip()
        if not query:
            self.clear_results()
            return

        # TODO: Perform actual search using indexer
        # For now, just show placeholder results with proper object names
        suggestions = self.query_one(SuggestionList)
        suggestions.update_results([
            {"name": f"TestObject{i}", "type": "object", "detail": f"10.0.0.{i}/32"}
            for i in range(1, 11)
        ])

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def action_refresh(self) -> None:
        """Refresh the current view."""
        # TODO: Reload config and rebuild index
        self.notify("Refreshing...")

    def action_focus_search(self) -> None:
        """Focus the search bar."""
        self.query_one(SearchBar).focus()

    def action_clear_search(self) -> None:
        """Clear the search field."""
        search_bar = self.query_one(SearchBar)
        search_bar.value = ""
        search_bar.focus()
        self.clear_results()

    def action_help(self) -> None:
        """Show help overlay."""
        # TODO: Display help modal
        self.notify("Help: / to search, q to quit, ESC to clear")

    def clear_results(self) -> None:
        """Clear search results."""
        suggestions = self.query_one(SuggestionList)
        suggestions.update_results([])


def main():
    """Entry point for TUI application."""
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="ACL-inspector Singularity TUI")
    parser.add_argument("--vendor", default="asa", choices=["asa", "fortigate"], help="Firewall vendor")
    parser.add_argument("--config", dest="config_path", default="", help="Path to config file")
    parser.add_argument("--vdom", default="", help="FortiGate VDOM (if applicable)")

    args = parser.parse_args()

    # Fall back to first config file in vendor's default directory if not specified
    config_path = args.config_path
    if not config_path:
        # Default config directories
        default_dirs = {
            "asa": "configs/cisco",
            "fortigate": "configs/fortigate"
        }

        default_dir = Path(default_dirs.get(args.vendor, "configs"))
        if default_dir.exists() and default_dir.is_dir():
            # Get first config file in directory (files only, not subdirs)
            config_files = sorted([f for f in default_dir.iterdir() if f.is_file()])
            if config_files:
                config_path = str(config_files[0])

    app = SingularityApp(vendor=args.vendor, config_path=config_path)
    app.run()


if __name__ == "__main__":
    main()
