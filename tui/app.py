"""Main Textual application for Singularity TUI."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Any

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Static, Input
from textual.binding import Binding

from .widgets.search_bar import SearchBar
from .widgets.suggestion_list import SuggestionList
from .widgets.status_bar import StatusBar


# Set up file logging
def setup_logging():
    """Configure logging to file."""
    log_dir = Path("./logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "TUI.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
        ]
    )
    return logging.getLogger("TUI")


logger = setup_logging()


class SingularityApp(App):
    """ACL-inspector Singularity TUI main application."""

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        width: 100%;
        height: 100%;
        layout: vertical;
    }

    #search-container {
        width: 100%;
        height: auto;
        layout: vertical;
        padding: 1 2;
        background: $panel;
    }

    #suggestions-container {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        background: $surface;
        overflow-y: auto;
    }

    .title {
        text-align: center;
        color: $primary;
        text-style: bold;
        height: 1;
        width: 100%;
    }

    .suggestion-item {
        width: 100%;
        height: 1;
        content-align: left middle;
    }

    .suggestions-placeholder {
        width: 100%;
        height: 3;
        padding: 1;
        color: $text-muted;
        content-align: center middle;
    }

    SearchBar {
        width: 100%;
        height: 3;
        border: tall $primary;
    }

    SearchBar:focus {
        border: tall $accent;
    }

    SuggestionList:focus {
        border: solid $warning;
    }
    """

    TITLE = "ACL-inspector Singularity TUI"
    SUB_TITLE = "Search-first firewall configuration analysis"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+m", "menu", "Menu", show=True),
        Binding("ctrl+t", "toggle_theme", "Theme", show=True),
        Binding("ctrl+r", "refresh", "Refresh", show=False),
        Binding("/", "focus_search", "Search", show=False),
        Binding("escape", "clear_search", "Clear", show=False),
    ]

    def __init__(self, vendor: str = "asa", config_path: str = ""):
        super().__init__()
        self.vendor = vendor
        self.config_path = config_path
        self.search_results = []
        self.parsed_config = None
        self.all_objects: List[Dict[str, Any]] = []

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

        # Footer with help text
        yield Footer()

    def on_mount(self) -> None:
        """Called when app starts."""
        self.title = self.TITLE
        self.sub_title = self.SUB_TITLE

        logger.info(f"TUI started: vendor={self.vendor}, config={self.config_path}")

        # Parse config if available
        if self.config_path:
            self._load_config()
        else:
            logger.warning("No config file specified")

        # Focus search bar on startup
        self.query_one(SearchBar).focus()

    def _load_config(self) -> None:
        """Load and parse the firewall config."""
        try:
            import sys
            from pathlib import Path

            # Add parent directory to path to import parsers
            parent_dir = Path(__file__).parent.parent
            if str(parent_dir) not in sys.path:
                sys.path.insert(0, str(parent_dir))

            if self.vendor == "asa":
                from parsers.cisco.asa.parser import ASAConfig
                with open(self.config_path, 'r') as f:
                    config_text = f.read()
                self.parsed_config = ASAConfig(config_text)

                # Build search index from objects
                self.all_objects = []
                for obj_name, networks in self.parsed_config.network_objects.items():
                    # Convert network set to string representation
                    detail = ", ".join(str(net) for net in list(networks)[:3])  # Show first 3
                    if len(networks) > 3:
                        detail += f" (+{len(networks)-3} more)"
                    self.all_objects.append({
                        "name": obj_name,
                        "type": "object",
                        "detail": detail
                    })

                # Add object groups
                for group_name, members in self.parsed_config.network_object_groups.items():
                    member_count = len(members)
                    self.all_objects.append({
                        "name": group_name,
                        "type": "group",
                        "detail": f"{member_count} members"
                    })

                logger.info(f"Loaded {len(self.all_objects)} objects from config")
            elif self.vendor == "fortigate":
                from parsers.fortigate.config import FTGConfig
                with open(self.config_path, 'r') as f:
                    config_text = f.read()
                self.parsed_config = FTGConfig(config_text)
                # TODO: Build index for FortiGate objects
                logger.warning("FortiGate parsing not yet fully implemented for TUI")
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Error loading config: {e}\n{error_details}")
            # Make error notification persistent (timeout=0 means it stays until dismissed)
            self.notify(
                f"Failed to load config: {str(e)[:100]}...\nCheck ./logs/TUI.log for details",
                severity="error",
                timeout=10  # Show for 10 seconds
            )

    def on_search_bar_searched(self, message: SearchBar.Searched) -> None:
        """Handle debounced search events."""
        query = message.value.strip().lower()

        logger.debug(f"Search event received: query='{query}'")

        if not query:
            self.clear_results()
            return

        # Search through loaded objects (simple substring match)
        results = []
        for obj in self.all_objects:
            if query in obj["name"].lower():
                results.append(obj)
                if len(results) >= 20:  # Limit results
                    break

        logger.debug(f"Found {len(results)} matching objects for query '{query}'")

        # Update suggestions
        suggestions = self.query_one(SuggestionList)
        suggestions.update_results(results)

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

    def action_toggle_theme(self) -> None:
        """Toggle between dark and light theme."""
        if self.theme == "textual-dark":
            self.theme = "textual-light"
            logger.info("Switched to light theme")
            self.notify("Light theme activated", timeout=2)
        else:
            self.theme = "textual-dark"
            logger.info("Switched to dark theme")
            self.notify("Dark theme activated", timeout=2)

    def action_menu(self) -> None:
        """Show main menu modal."""
        # TODO: Create proper modal menu
        current_theme = "Light" if self.theme == "textual-light" else "Dark"
        menu_text = (
            "ACL-inspector Menu\n\n"
            "1. Help - Key bindings and usage\n"
            "2. About - Version and info\n"
            "3. Settings - Configure TUI\n\n"
            f"Current theme: {current_theme}\n\n"
            "Ctrl+Q: Quit\n"
            "Ctrl+M: Toggle this menu\n"
            "Ctrl+T: Toggle dark/light theme\n"
            "ESC: Clear search\n"
            "Tab: Navigate between widgets\n"
            "Enter: Select result (coming soon)\n"
            "Type to search objects and groups\n\n"
            "Drill-down view: Coming soon!"
        )
        self.notify(menu_text, timeout=12)

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
