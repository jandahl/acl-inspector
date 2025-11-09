"""Main Textual application for Singularity TUI."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Static, Input
from textual.binding import Binding

from .widgets.search_bar import SearchBar
from .widgets.suggestion_list import SuggestionList
from .widgets.status_bar import StatusBar
from .widgets.detail_view import DetailView
from .widgets.action_tabs import ActionTabs


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

    #breadcrumb-container {
        width: 100%;
        height: auto;
        padding: 0 2;
        background: $surface;
        display: none;
    }

    #breadcrumb-container.visible {
        display: block;
    }

    .breadcrumb {
        color: $text;
        text-style: bold;
        padding: 1 0;
    }

    #suggestions-container {
        width: 100%;
        height: 1fr;
        padding: 0 1;
        background: $surface;
    }

    #suggestions-container.collapsed {
        display: none;
    }

    #actions-container {
        width: 100%;
        height: auto;
        padding: 0 2 1 2;
        background: $surface;
        display: none;
        border: solid transparent;
    }

    #actions-container.visible {
        display: block;
    }

    #actions-container:focus-within {
        border: solid $accent;
    }

    #detail-container {
        width: 100%;
        height: 1fr;
        padding: 0 1;
        background: $surface;
        display: none;
    }

    #detail-container.visible {
        display: block;
    }

    SuggestionList {
        width: 100%;
        height: 100%;
        border: solid $primary;
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
        border: solid $accent;
    }

    .action-tabs {
        width: 100%;
        height: auto;
    }

    .action-tab {
        width: auto;
        height: 3;
        min-width: 16;
        margin: 0 1 0 0;
        border: solid $primary;
        background: $surface;
        color: $text;
    }

    .action-tab.selected {
        border: solid $accent;
        background: $primary;
        color: $text;
        text-style: bold;
    }

    DetailView {
        width: 100%;
        height: 100%;
        border: solid $success;
    }

    .detail-content {
        padding: 1;
    }

    .detail-placeholder {
        padding: 1;
        color: $text-muted;
        content-align: center middle;
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
        Binding("escape", "close_detail_or_clear", "Close/Clear", show=False),
    ]

    def __init__(self, vendor: str = "asa", config_path: str = ""):
        super().__init__()
        self.vendor = vendor
        self.config_path = config_path
        self.search_results = []
        self.parsed_config = None
        self.all_objects: List[Dict[str, Any]] = []
        self.selected_object: Optional[Dict[str, Any]] = None
        self.drill_down_active = False
        self.last_selected_index = 0  # Track which item was selected

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(show_clock=True)

        with Container(id="main-container"):
            # Search section
            with Vertical(id="search-container"):
                yield Static(f"[{self.vendor.upper()}] {self.config_path or 'No config loaded'}", classes="title")
                yield SearchBar(placeholder="Type to search objects, ACLs, hosts...")

            # Breadcrumb section (hidden until item selected)
            with Vertical(id="breadcrumb-container"):
                yield Static("", id="breadcrumb", classes="breadcrumb")

            # Suggestions/results section
            with Vertical(id="suggestions-container"):
                yield SuggestionList()

            # Action tabs section (hidden until item selected)
            with Vertical(id="actions-container"):
                yield ActionTabs()

            # Detail section (hidden until tab selected)
            with Vertical(id="detail-container"):
                yield DetailView()

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

    def on_key(self, event) -> None:
        """Smart keyboard routing based on context."""
        key = event.key

        # Printable characters go to search bar (unless already focused)
        if len(key) == 1 and key.isprintable():
            search_bar = self.query_one(SearchBar)
            if not search_bar.has_focus:
                search_bar.focus()
                # Let the event propagate to SearchBar
                return

        # Up/Down arrows: route to suggestions list if visible and has results
        if key in ("up", "down", "j", "k"):
            suggestions_container = self.query_one("#suggestions-container")
            if "collapsed" not in suggestions_container.classes:
                # Results are visible, route to suggestions list
                suggestions = self.query_one(SuggestionList)
                if not suggestions.has_focus and suggestions.results:
                    suggestions.focus()
                    # Manually trigger the key on SuggestionList
                    return

        # Left/Right arrows: route to action tabs if in drill-down mode
        if key in ("left", "right"):
            if self.drill_down_active:
                action_tabs = self.query_one(ActionTabs)
                if not action_tabs.has_focus:
                    action_tabs.focus()
                    # Let the event propagate to ActionTabs
                    return

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

    def on_search_bar_enter_pressed(self, message: SearchBar.EnterPressed) -> None:
        """Handle Enter key in search field - focus results."""
        suggestions = self.query_one(SuggestionList)
        if suggestions.results:
            # Focus the results list if there are results
            suggestions.focus()
            logger.debug("Enter pressed in search - focused results list")

    def on_suggestion_list_item_selected(self, message: SuggestionList.ItemSelected) -> None:
        """Handle item selection - enter drill-down mode."""
        logger.info(f"Item selected: {message.item['name']}")

        self.selected_object = message.item
        self.drill_down_active = True

        # Save the current selection index from SuggestionList
        suggestions = self.query_one(SuggestionList)
        self.last_selected_index = suggestions.selected_index

        # Update breadcrumb
        breadcrumb = self.query_one("#breadcrumb", Static)
        obj_type = message.item.get("type", "object").upper()
        breadcrumb.update(f"▶ Selected: {message.item['name']} [{obj_type}]")

        # Show breadcrumb and action tabs
        self.query_one("#breadcrumb-container").add_class("visible")
        self.query_one("#actions-container").add_class("visible")

        # Hide results container (don't show empty list)
        suggestions_container = self.query_one("#suggestions-container")
        suggestions_container.add_class("collapsed")

        # Show detail view with default tab (details)
        detail_view = self.query_one(DetailView)
        detail_view.update_object(message.item, self.parsed_config)
        self.query_one("#detail-container").add_class("visible")

        # Focus action tabs for keyboard navigation
        self.query_one(ActionTabs).focus()

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

    def on_action_tabs_tab_selected(self, message: ActionTabs.TabSelected) -> None:
        """Handle tab selection - update detail view content."""
        logger.info(f"Tab selected: {message.tab_id} ({message.tab_label})")

        if not self.selected_object:
            return

        detail_view = self.query_one(DetailView)

        if message.tab_id == "details":
            # Show object details
            detail_view.update_object(self.selected_object, self.parsed_config)
        elif message.tab_id == "inspect":
            # TODO: Show inspect results (ACL rules for this object)
            detail_view.update_object(self.selected_object, self.parsed_config)
            self.notify(f"Inspect mode for {self.selected_object['name']} (coming soon)", timeout=3)
        elif message.tab_id == "compare":
            # TODO: Show compare UI
            detail_view.update_object(self.selected_object, self.parsed_config)
            self.notify(f"Compare mode (coming soon)", timeout=3)
        elif message.tab_id == "acls":
            # TODO: Show which ACLs reference this object
            detail_view.update_object(self.selected_object, self.parsed_config)
            self.notify(f"Finding ACLs using {self.selected_object['name']} (coming soon)", timeout=3)

    def action_close_detail_or_clear(self) -> None:
        """Exit drill-down mode or clear search."""
        if self.drill_down_active:
            # Exit drill-down mode
            self.drill_down_active = False
            self.selected_object = None

            # Hide breadcrumb, actions, and detail
            self.query_one("#breadcrumb-container").remove_class("visible")
            self.query_one("#actions-container").remove_class("visible")
            self.query_one("#detail-container").remove_class("visible")

            # Show suggestions container again
            suggestions_container = self.query_one("#suggestions-container")
            suggestions_container.remove_class("collapsed")

            # Restore full search results
            search_bar = self.query_one(SearchBar)
            query = search_bar.value.strip().lower()
            if query:
                # Re-run search to restore results
                results = []
                for obj in self.all_objects:
                    if query in obj["name"].lower():
                        results.append(obj)
                        if len(results) >= 20:
                            break
                suggestions = self.query_one(SuggestionList)
                suggestions.update_results(results)

                # Restore the previous selection
                if 0 <= self.last_selected_index < len(results):
                    suggestions.selected_index = self.last_selected_index

                suggestions.focus()
            else:
                self.clear_results()
                search_bar.focus()

            logger.info("Exited drill-down mode")
        else:
            # Clear search
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
        """Show main menu help."""
        # TODO: Create proper modal screen instead of notification
        current_theme = "Light" if self.theme == "textual-light" else "Dark"
        menu_text = (
            "ACL-inspector TUI - Quick Help\n\n"
            f"Theme: {current_theme}\n\n"
            "Search mode:\n"
            "  Type to search • Up/Down/j/k to navigate\n"
            "  Enter to drill down • ESC to clear\n\n"
            "Drill-down mode:\n"
            "  Left/Right arrows to switch tabs\n"
            "  ESC to exit drill-down\n\n"
            "Global:\n"
            "  Ctrl+Q: Quit • Ctrl+M: Help\n"
            "  Ctrl+T: Toggle theme • Tab: Navigate\n"
        )
        self.notify(menu_text, timeout=10)

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
