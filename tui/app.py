"""Main Textual application for Singularity TUI."""

from __future__ import annotations

import logging
from datetime import datetime
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

    .filter-bar {
        width: 100%;
        height: auto;
        padding: 1;
        background: $panel;
        border: solid $primary;
        margin-bottom: 1;
    }

    .filter-label {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .filter-controls {
        width: 100%;
        height: auto;
        align: left middle;
    }

    .filter-field-label {
        width: auto;
        padding: 0 1;
        color: $text;
    }

    .filter-input {
        width: 20;
        margin: 0 2 0 0;
    }

    .filter-buttons {
        width: 100%;
        height: auto;
        align: left middle;
        margin-top: 1;
    }

    .filter-buttons Button {
        min-width: 16;
        margin: 0 1 0 0;
    }
    """

    TITLE = "ACL-inspector Singularity TUI"
    SUB_TITLE = "Search-first firewall configuration analysis"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+o", "open_menu", "Menu", show=True),
        Binding("f1", "show_help", "Help", show=True),
        Binding("ctrl+t", "toggle_theme", "Theme", show=True),
        Binding("ctrl+e", "export_current", "Export", show=True),
        Binding("ctrl+r", "refresh", "Refresh", show=False),
        Binding("/", "focus_search", "Search", show=False),
        Binding("escape", "close_detail_or_clear", "Close/Clear", show=False),
    ]

    def __init__(self, vendor: str = "asa", config_path: str = ""):
        super().__init__()
        self.vendor = vendor
        self.config_path = config_path
        self.is_directory = False
        self.config_files: List[str] = []
        self.parsed_configs: Dict[str, Any] = {}  # filename -> parsed config
        self.search_results = []
        self.parsed_config = None  # For single file mode compatibility
        self.all_objects: List[Dict[str, Any]] = []
        self.selected_object: Optional[Dict[str, Any]] = None
        self.drill_down_active = False
        self.last_selected_index = 0  # Track which item was selected

        # Track current tab and data for export
        self.current_tab_id = "details"
        self.current_tab_data: Optional[Any] = None
        self.current_tab_result: Optional[Any] = None  # Stores InspectResult, CompareResult, etc.

        # Track inspect filters
        self.inspect_filters: Dict[str, Any] = {
            "protocol": None,
            "port": None,
            "action": None,
        }

        # Initialize settings manager
        from .state import TUISettings
        self.settings = TUISettings()

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

        # FIX #5a: Printable characters - additive typing (don't auto-focus in drill-down mode)
        if len(key) == 1 and key.isprintable():
            search_bar = self.query_one(SearchBar)

            # If in drill-down mode and typing, exit drill-down and append to search
            if self.drill_down_active and not search_bar.has_focus:
                # Exit drill-down mode first
                self.action_close_detail_or_clear()
                # Append the character to search
                search_bar.value = search_bar.value + key
                search_bar.focus()
                # Move cursor to end
                search_bar.cursor_position = len(search_bar.value)
                event.prevent_default()
                return

            # If not in drill-down and search bar doesn't have focus, focus it
            if not search_bar.has_focus and not self.drill_down_active:
                search_bar.focus()
                # Let the event propagate to SearchBar
                return

        # FIX #1: Up/Down arrows: unified focus for search+results
        if key in ("up", "down", "j", "k"):
            suggestions_container = self.query_one("#suggestions-container")
            if "collapsed" not in suggestions_container.classes:
                # Results are visible - search bar and suggestions share focus
                suggestions = self.query_one(SuggestionList)
                if suggestions.results:
                    search_bar = self.query_one(SearchBar)
                    # If EITHER search bar OR suggestions have focus, navigate suggestions
                    if search_bar.has_focus or suggestions.has_focus:
                        # Manually update selection in suggestions
                        if key in ("down", "j"):
                            suggestions.selected_index = min(
                                len(suggestions.results) - 1,
                                suggestions.selected_index + 1
                            )
                        elif key in ("up", "k"):
                            suggestions.selected_index = max(0, suggestions.selected_index - 1)
                        event.prevent_default()
                        return

        # Left/Right arrows: route to action tabs if in drill-down mode
        # But only if an input field doesn't have focus
        if key in ("left", "right"):
            if self.drill_down_active:
                # Check if any input field has focus
                try:
                    from textual.widgets import Input
                    focused = self.focused
                    if not isinstance(focused, Input):
                        # No input has focus, route to tabs
                        action_tabs = self.query_one(ActionTabs)
                        if not action_tabs.has_focus:
                            action_tabs.focus()
                            # Let the event propagate to ActionTabs
                            return
                except:
                    # If we can't check, default to old behavior
                    action_tabs = self.query_one(ActionTabs)
                    if not action_tabs.has_focus:
                        action_tabs.focus()
                        return

    def _load_config(self) -> None:
        """Load and parse the firewall config(s)."""
        try:
            import sys
            from pathlib import Path
            import os

            # Add parent directory to path to import parsers
            parent_dir = Path(__file__).parent.parent
            if str(parent_dir) not in sys.path:
                sys.path.insert(0, str(parent_dir))

            config_path = Path(self.config_path)

            # Check if path is a directory
            if config_path.is_dir():
                self.is_directory = True
                logger.info(f"Loading configs from directory: {config_path}")

                # Find all config files in directory
                self.config_files = sorted([
                    str(f) for f in config_path.iterdir()
                    if f.is_file() and not f.name.startswith('.')
                ])

                if not self.config_files:
                    raise ValueError(f"No config files found in directory: {config_path}")

                logger.info(f"Found {len(self.config_files)} config files")

                # Load all configs
                self.all_objects = []
                for config_file in self.config_files:
                    self._load_single_config(config_file)

                logger.info(f"Loaded {len(self.all_objects)} total objects from {len(self.config_files)} configs")

                # Update title bar to show config count
                title_static = self.query_one("#search-container Static.title")
                title_static.update(f"[{self.vendor.upper()}] {len(self.config_files)} configs loaded from {config_path.name}")

            else:
                # Single file mode
                self.is_directory = False
                self._load_single_config(str(config_path))
                logger.info(f"Loaded {len(self.all_objects)} objects from single config")

                # Update title bar for single file
                title_static = self.query_one("#search-container Static.title")
                title_static.update(f"[{self.vendor.upper()}] {config_path.name}")

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Error loading config: {e}\n{error_details}")
            self.notify(
                f"Failed to load config: {str(e)[:100]}...\nCheck ./logs/TUI.log for details",
                severity="error",
                timeout=10
            )

    def _load_single_config(self, config_file: str) -> None:
        """Load and parse a single config file.

        Args:
            config_file: Path to the config file
        """
        from pathlib import Path
        filename = Path(config_file).name

        try:
            if self.vendor == "asa":
                from parsers.cisco.asa.parser import ASAConfig
                with open(config_file, 'r') as f:
                    config_text = f.read()
                parsed = ASAConfig(config_text)

                # Store parsed config
                self.parsed_configs[filename] = parsed

                # For single file mode, also set as main config
                if not self.is_directory:
                    self.parsed_config = parsed

                # Build search index from objects
                for obj_name, networks in parsed.network_objects.items():
                    # Convert network set to string representation
                    detail = ", ".join(str(net) for net in list(networks)[:3])
                    if len(networks) > 3:
                        detail += f" (+{len(networks)-3} more)"

                    # Add source file to object
                    obj_entry = {
                        "name": obj_name,
                        "type": "object",
                        "detail": detail,
                        "source_file": filename,
                        "config": parsed  # Keep reference to parsed config
                    }
                    self.all_objects.append(obj_entry)

                # Add object groups
                for group_name, members in parsed.network_object_groups.items():
                    member_count = len(members)
                    obj_entry = {
                        "name": group_name,
                        "type": "group",
                        "detail": f"{member_count} members",
                        "source_file": filename,
                        "config": parsed
                    }
                    self.all_objects.append(obj_entry)

                logger.info(f"Loaded {filename}: {len(parsed.network_objects)} objects, {len(parsed.network_object_groups)} groups")

            elif self.vendor == "fortigate":
                from parsers.fortigate.config import FTGConfig
                with open(config_file, 'r') as f:
                    config_text = f.read()
                parsed = FTGConfig(config_text)
                self.parsed_configs[filename] = parsed

                if not self.is_directory:
                    self.parsed_config = parsed

                logger.warning(f"FortiGate parsing not yet fully implemented for TUI: {filename}")

        except Exception as e:
            logger.error(f"Failed to load {filename}: {e}")
            # Don't fail the entire load, just skip this file
            self.notify(f"Failed to load {filename}: {str(e)[:50]}", severity="warning", timeout=3)

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

    def _show_inspect_tab(self, obj_config) -> None:
        """Show Inspect tab with filter bar and results.

        Args:
            obj_config: Parsed configuration object
        """
        from analysis_core import inspect_object, format_inspect_rich
        from rich.console import Group
        from rich.text import Text
        from .widgets.filter_bar import FilterBar

        detail_view = self.query_one(DetailView)

        # Clear detail view and add filter bar + results container
        detail_view.remove_children()

        # Mount filter bar
        filter_bar = FilterBar()
        detail_view.mount(filter_bar)

        # Run inspect with current filters
        result = inspect_object(
            obj_config,
            self.selected_object['name'],
            protocol=self.inspect_filters.get("protocol"),
            dport=self.inspect_filters.get("port"),
            include_any=False
        )

        # Apply action filter client-side if specified
        if self.inspect_filters.get("action"):
            action_filter = self.inspect_filters["action"]
            filtered_rules = [
                rule for rule in result.matching_rules
                if rule.get("action", "").lower() == action_filter
            ]
            # Create new result with filtered rules
            from analysis_core import InspectResult
            result = InspectResult(
                object_name=result.object_name,
                resolved_addresses=result.resolved_addresses,
                matching_rules=filtered_rules,
                duplicates=result.duplicates,
                total_rules=len(filtered_rules)
            )

        # Store result for export
        self.current_tab_result = result

        # Format and show results
        rich_content = format_inspect_rich(result)

        # Add filter summary if filters are active
        filter_parts = []
        if self.inspect_filters.get("protocol"):
            filter_parts.append(f"protocol={self.inspect_filters['protocol']}")
        if self.inspect_filters.get("port"):
            filter_parts.append(f"port={self.inspect_filters['port']}")
        if self.inspect_filters.get("action"):
            filter_parts.append(f"action={self.inspect_filters['action']}")

        if filter_parts:
            filter_text = Text()
            filter_text.append("\nActive Filters: ", style="bold yellow")
            filter_text.append(", ".join(filter_parts), style="cyan")
            filter_text.append("\n", style="dim")
            rich_content = Group(filter_text, rich_content)

        from textual.widgets import Static
        detail_view.mount(Static(rich_content, classes="detail-content"))

        logger.info(f"Inspect completed: {result.total_rules} rules found (filters: {self.inspect_filters})")

    def on_filter_bar_filter_changed(self, message) -> None:
        """Handle filter changes from FilterBar widget.

        Args:
            message: FilterBar.FilterChanged message
        """
        logger.info(f"Filters changed: {message.filters}")

        # Update current filters
        self.inspect_filters = message.filters

        # Re-run inspect if we're on the inspect tab
        if self.current_tab_id == "inspect" and self.selected_object:
            obj_config = self.selected_object.get('config', self.parsed_config)
            try:
                self._show_inspect_tab(obj_config)
            except Exception as e:
                logger.error(f"Failed to re-run inspect with filters: {e}", exc_info=True)
                self.notify(f"Filter error: {str(e)}", severity="error", timeout=5)

    def _show_path_check_tab(self, obj_config) -> None:
        """Show Path Check tab with packet simulation form.

        Args:
            obj_config: Parsed configuration object
        """
        from rich.text import Text
        from rich.table import Table
        from rich.panel import Panel
        from rich.console import Group
        from textual.widgets import Static, Input, Button
        from textual.containers import Vertical, Horizontal

        detail_view = self.query_one(DetailView)
        detail_view.remove_children()

        # Create form for packet parameters
        help_text = Text()
        help_text.append("Path Check - Packet Flow Simulation\n\n", style="bold cyan")
        help_text.append("Simulate a packet flow through the firewall to see NAT + ACL outcome.\n", style="white")
        help_text.append("Source is pre-filled with the selected object.\n\n", style="dim")

        detail_view.mount(Static(help_text, classes="detail-content"))

        # Form container
        form_container = Vertical(id="path-form")

        # Source field (pre-filled with selected object)
        form_container.mount(Static("Source IP/Object:", classes="filter-field-label"))
        src_input = Input(value=self.selected_object['name'], id="path-src", classes="filter-input")
        form_container.mount(src_input)

        # Destination field
        form_container.mount(Static("Destination IP/Object:", classes="filter-field-label"))
        dst_input = Input(placeholder="e.g., 10.1.1.1 or WebServer", id="path-dst", classes="filter-input")
        form_container.mount(dst_input)

        # Protocol field
        form_container.mount(Static("Protocol:", classes="filter-field-label"))
        proto_input = Input(placeholder="tcp, udp, icmp, ip", id="path-proto", classes="filter-input")
        form_container.mount(proto_input)

        # Port field
        form_container.mount(Static("Destination Port:", classes="filter-field-label"))
        port_input = Input(placeholder="e.g., 80, 443", id="path-port", classes="filter-input")
        form_container.mount(port_input)

        # Run button
        run_button = Button("Simulate Packet Flow", variant="primary", id="btn-run-path")
        form_container.mount(run_button)

        detail_view.mount(form_container)

        # Placeholder for results
        detail_view.mount(Static("", id="path-results", classes="detail-content"))

    def _run_path_check(self, src: str, dst: str, protocol: Optional[str], port: Optional[int]) -> None:
        """Run path check and display results.

        Args:
            src: Source IP/object
            dst: Destination IP/object
            protocol: Protocol (tcp, udp, icmp, etc.)
            port: Destination port
        """
        from parsers.cisco.asa.path import path_check
        from rich.table import Table
        from rich.panel import Panel
        from rich.text import Text
        from rich.console import Group
        from textual.widgets import Static

        # Get config for selected object
        obj_config = self.selected_object.get('config', self.parsed_config)

        # Get raw config text
        if hasattr(obj_config, 'raw_text'):
            cfg_text = obj_config.raw_text
        else:
            raise ValueError("Config does not have raw_text attribute")

        # Run path check
        dports = {port} if port else set()
        result = path_check(
            cfg_text,
            src=src,
            dst=dst,
            proto=protocol,
            dports=dports,
            include_any=True
        )

        # Format results
        content_parts = []

        # Header
        header = Text()
        header.append("Path Check Result\n", style="bold cyan")
        header.append(f"Flow: {src} → {dst}", style="white")
        if protocol:
            header.append(f" ({protocol}", style="dim")
            if port:
                header.append(f":{port}", style="dim")
            header.append(")", style="dim")
        header.append("\n")
        content_parts.append(header)

        # Verdict
        verdict_text = Text()
        allowed = result.get("allowed", False)
        verdict_text.append("\nVerdict: ", style="bold yellow")
        if allowed:
            verdict_text.append("ALLOWED", style="bold green")
        else:
            verdict_text.append("DENIED", style="bold red")
        verdict_text.append("\n\n", style="white")
        content_parts.append(verdict_text)

        # NAT info
        nat_info = result.get("nat", {})
        if nat_info.get("applied"):
            nat_text = Text()
            nat_text.append("NAT Translation Applied\n", style="bold yellow")
            rule = nat_info.get("rule", {})
            nat_text.append(f"  Type: {nat_info.get('type', 'unknown')}\n", style="cyan")
            if rule.get("raw"):
                nat_text.append(f"  Rule: {rule['raw'][:100]}...\n", style="dim")
            content_parts.append(Panel(nat_text, title="NAT", border_style="yellow"))
        else:
            content_parts.append(Text("No NAT translation applied\n", style="dim"))

        # ACL decision
        acl_info = result.get("acl", {})
        decision = acl_info.get("decision", "unknown")
        matches = acl_info.get("matches", [])

        if matches:
            acl_text = Text()
            acl_text.append(f"Decision: {decision.upper()}\n\n", style="bold cyan")
            acl_text.append(f"Matching ACL Rules ({len(matches)} total):\n", style="yellow")

            for i, match in enumerate(matches[:10]):  # Show first 10 matches
                acl_text.append(f"\n{i+1}. ", style="bold")
                acl_text.append(f"[{match.get('action', 'unknown')}] ", style="green" if match.get('action') == 'permit' else "red")
                acl_text.append(f"{match.get('acl', 'unknown')}", style="cyan")
                if match.get('interface'):
                    acl_text.append(f" (interface: {match['interface']}", style="dim")
                    if match.get('direction'):
                        acl_text.append(f" {match['direction']}", style="dim")
                    acl_text.append(")", style="dim")
                acl_text.append(f"\n   {match.get('raw', '')[:120]}\n", style="dim")

            if len(matches) > 10:
                acl_text.append(f"\n... and {len(matches) - 10} more matches\n", style="dim")

            content_parts.append(Panel(acl_text, title="ACL Evaluation", border_style="cyan"))
        else:
            content_parts.append(Text("No matching ACL rules found\n", style="yellow"))

        # Show results
        detail_view = self.query_one(DetailView)
        results_widget = detail_view.query_one("#path-results", Static)
        results_widget.update(Group(*content_parts))

        # Store result for export
        self.current_tab_result = result
        logger.info(f"Path check completed: verdict={allowed}, NAT={nat_info.get('applied')}, matches={len(matches)}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses in path check form."""
        if event.button.id == "btn-run-path":
            # Get form values
            try:
                src_input = self.query_one("#path-src", Input)
                dst_input = self.query_one("#path-dst", Input)
                proto_input = self.query_one("#path-proto", Input)
                port_input = self.query_one("#path-port", Input)

                src = src_input.value.strip()
                dst = dst_input.value.strip()
                protocol = proto_input.value.strip().lower() or None
                port_str = port_input.value.strip()
                port = int(port_str) if port_str else None

                if not src or not dst:
                    self.notify("Source and destination are required", severity="error")
                    return

                # Run path check
                self._run_path_check(src, dst, protocol, port)
            except ValueError as e:
                self.notify(f"Invalid port number: {str(e)}", severity="error")
            except Exception as e:
                logger.error(f"Path check failed: {e}", exc_info=True)
                self.notify(f"Path check error: {str(e)}", severity="error", timeout=10)

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

    def on_detail_view_compare_requested(self, message: DetailView.CompareRequested) -> None:
        """Handle comparison request from detail view."""
        logger.info(f"Compare requested: {message.old_obj['name']} vs {message.new_obj['name']}")

        detail_view = self.query_one(DetailView)
        # Use the config from the old_obj (selected object)
        obj_config = message.old_obj.get('config', self.parsed_config)

        try:
            # Perform comparison and store result for export
            from analysis_core import compare_objects

            result = compare_objects(
                obj_config,
                old_target=message.old_obj['name'],
                new_target=message.new_obj['name'],
                include_any=False
            )
            self.current_tab_result = result

            # Show results
            detail_view.show_compare_results(
                message.old_obj,
                message.new_obj,
                obj_config
            )
        except Exception as e:
            logger.error(f"Comparison failed: {e}", exc_info=True)
            self.notify(f"Comparison error: {str(e)}", severity="error", timeout=5)

    def on_action_tabs_tab_selected(self, message: ActionTabs.TabSelected) -> None:
        """Handle tab selection - update detail view content."""
        logger.info(f"Tab selected: {message.tab_id} ({message.tab_label})")

        if not self.selected_object:
            return

        # Update current tab tracking
        self.current_tab_id = message.tab_id
        self.current_tab_data = None
        self.current_tab_result = None

        detail_view = self.query_one(DetailView)

        # Get the config for the selected object
        obj_config = self.selected_object.get('config', self.parsed_config)

        if message.tab_id == "details":
            # Show object details
            try:
                detail_view.update_object(self.selected_object, obj_config)
                # Store data for export
                self.current_tab_data = self.selected_object
                self.current_tab_result = obj_config
                logger.info(f"Details tab shown for {self.selected_object['name']}")
            except Exception as e:
                logger.error(f"Details tab failed: {e}", exc_info=True)
                self.notify(f"Details error: {str(e)}", severity="error", timeout=5)

        elif message.tab_id == "inspect":
            # Show Inspect tab with filter bar
            try:
                self._show_inspect_tab(obj_config)
            except ImportError as e:
                logger.error(f"Inspect import failed (rich not installed?): {e}")
                self.notify(f"Inspect requires 'rich' module: pip install rich textual", severity="error", timeout=5)
            except Exception as e:
                logger.error(f"Inspect failed: {e}", exc_info=True)
                self.notify(f"Inspect error: {str(e)}", severity="error", timeout=5)

        elif message.tab_id == "compare":
            # Show compare prompt with suggestions
            try:
                detail_view.show_compare_prompt(self.selected_object, self.all_objects)
                logger.info(f"Compare tab shown for {self.selected_object['name']}")
            except Exception as e:
                logger.error(f"Compare tab failed: {e}", exc_info=True)
                self.notify(f"Compare error: {str(e)}", severity="error", timeout=5)

        elif message.tab_id == "acls":
            # Show ACL usage for this object using shared analysis_core
            try:
                from analysis_core import find_object_usage, format_usage_rich

                result = find_object_usage(
                    obj_config,
                    self.selected_object['name']
                )
                rich_content = format_usage_rich(result)
                detail_view.show_content(rich_content)
                # Store result for export
                self.current_tab_result = result
                logger.info(f"ACL usage completed: {result.total_references} references found")
            except ImportError as e:
                logger.error(f"ACL usage import failed (rich not installed?): {e}")
                self.notify(f"ACL Usage requires 'rich' module: pip install rich textual", severity="error", timeout=5)
            except Exception as e:
                logger.error(f"ACL usage failed: {e}", exc_info=True)
                self.notify(f"ACL usage error: {str(e)}", severity="error", timeout=5)

        elif message.tab_id == "path":
            # Show Path Check tab (packet flow simulation)
            try:
                self._show_path_check_tab(obj_config)
            except Exception as e:
                logger.error(f"Path check failed: {e}", exc_info=True)
                self.notify(f"Path check error: {str(e)}", severity="error", timeout=5)

    def action_close_detail_or_clear(self) -> None:
        """Exit drill-down mode (FIX #4: don't clear search)."""
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

            # Restore full search results (FIX #5b: keep search term)
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

                # FIX #5b: Focus search bar (not suggestions)
                search_bar.focus()
            else:
                self.clear_results()
                search_bar.focus()

            logger.info("Exited drill-down mode")
        else:
            # FIX #4: ESC when not in drill-down just focuses search bar (don't clear)
            search_bar = self.query_one(SearchBar)
            search_bar.focus()

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

        # Save theme preference
        self.settings.set("display", "theme", self.theme)
        self.settings.save()

    def action_open_menu(self) -> None:
        """Open the main menu modal."""
        from .screens.menu_screen import MenuScreen

        # Get current config info
        config_info = f"Config: {self.config_path or 'No config loaded'}"

        def handle_menu_result(action):
            """Handle menu selection."""
            if action == "help":
                self.action_show_help()
            elif action == "about":
                self.action_show_about()
            elif action == "settings":
                self.action_show_settings()
            elif action == "theme":
                self.action_toggle_theme()

        self.push_screen(MenuScreen(self.theme, config_info), handle_menu_result)

    def action_show_settings(self) -> None:
        """Show settings screen."""
        from .screens.settings_screen import SettingsScreen

        def handle_settings_result(result):
            """Handle settings screen result."""
            if result == "saved":
                self.notify("Settings saved successfully", timeout=3)
                # Reload settings that can be applied immediately
                self._apply_settings()
            elif result == "error":
                self.notify("Error saving settings", severity="error", timeout=5)

        self.push_screen(SettingsScreen(self.settings), handle_settings_result)

    def _apply_settings(self) -> None:
        """Apply settings that can be changed at runtime."""
        # Apply theme setting
        theme = self.settings.get("display", "theme", "textual-dark")
        if self.theme != theme:
            self.theme = theme

    def action_show_help(self) -> None:
        """Show help screen."""
        from .screens.help_screen import HelpScreen
        self.push_screen(HelpScreen())

    def action_show_about(self) -> None:
        """Show about screen."""
        from .screens.about_screen import AboutScreen
        self.push_screen(AboutScreen())

    def action_export_current(self) -> None:
        """Export current tab data."""
        # Check if we're in drill-down mode with an object selected
        if not self.drill_down_active or not self.selected_object:
            self.notify("No data to export. Please select an object first.", severity="warning")
            return

        # Check if we have data to export
        if not self.current_tab_result and not self.current_tab_data:
            self.notify("No data available for export on this tab.", severity="warning")
            return

        # Show export dialog
        from .screens.export_screen import ExportScreen

        def export_callback(format_type: str, filename: str) -> None:
            """Handle the actual export operation."""
            try:
                self._perform_export(format_type, filename)
                self.notify(f"Data exported to {filename}", severity="information", timeout=5)
                logger.info(f"Exported {self.current_tab_id} data to {filename} ({format_type})")
            except Exception as e:
                logger.error(f"Export failed: {e}", exc_info=True)
                raise

        # Get tab label for display
        action_tabs = self.query_one(ActionTabs)
        tab_label = next((t["label"] for t in action_tabs.tabs if t["id"] == self.current_tab_id), self.current_tab_id)

        self.push_screen(
            ExportScreen(
                tab_name=tab_label,
                object_name=self.selected_object['name'],
                data=self.current_tab_result or self.current_tab_data,
                export_callback=export_callback
            )
        )

    def _perform_export(self, format_type: str, filename: str) -> None:
        """Perform the actual export operation.

        Args:
            format_type: Export format (json, csv, txt)
            filename: Output filename
        """
        from .utils.export import ExportManager
        from analysis_core import format_inspect_json, format_compare_json, format_usage_json

        if self.current_tab_id == "details":
            # Export object details
            if format_type == "json":
                export_data = ExportManager.format_details_for_export(
                    self.selected_object,
                    self.current_tab_result
                )
                ExportManager.export_to_json(export_data, filename)
            elif format_type == "txt":
                # Plain text format
                lines = []
                lines.append(f"Object Details: {self.selected_object['name']}")
                lines.append("=" * 60)
                lines.append(f"Type: {self.selected_object.get('type', 'unknown')}")
                lines.append(f"Detail: {self.selected_object.get('detail', '')}")
                if self.selected_object.get('source_file'):
                    lines.append(f"Source: {self.selected_object['source_file']}")
                ExportManager.export_to_text("\n".join(lines), filename)
            else:
                raise ValueError(f"CSV export not supported for Details tab")

        elif self.current_tab_id == "inspect":
            # Export inspect results
            if not self.current_tab_result:
                raise ValueError("No inspect data available")

            if format_type == "json":
                export_data = format_inspect_json(self.current_tab_result)
                ExportManager.export_to_json(export_data, filename)
            elif format_type == "csv":
                headers, rows = ExportManager.format_inspect_for_csv(self.current_tab_result)
                ExportManager.export_to_csv(headers, rows, filename)
            elif format_type == "txt":
                # Plain text format
                result = self.current_tab_result
                lines = []
                lines.append(f"Inspect Results: {result.target_name}")
                lines.append("=" * 60)
                lines.append(f"Total rules: {result.total_rules}")
                lines.append("")
                for rule in result.matching_rules:
                    lines.append(f"ACL: {rule.get('acl', '')}")
                    lines.append(f"  Action: {rule.get('action', '')}")
                    lines.append(f"  Protocol: {rule.get('protocol', '')}")
                    lines.append(f"  Source: {rule.get('src', '')}")
                    lines.append(f"  Destination: {rule.get('dst', '')}")
                    lines.append(f"  Port: {rule.get('port', '')}")
                    lines.append(f"  Raw: {rule.get('raw', '')}")
                    lines.append("")
                ExportManager.export_to_text("\n".join(lines), filename)

        elif self.current_tab_id == "compare":
            # Export compare results
            if not self.current_tab_result:
                raise ValueError("No comparison data available")

            if format_type == "json":
                export_data = format_compare_json(self.current_tab_result)
                ExportManager.export_to_json(export_data, filename)
            elif format_type == "csv":
                headers, rows = ExportManager.format_compare_for_csv(self.current_tab_result)
                ExportManager.export_to_csv(headers, rows, filename)
            elif format_type == "txt":
                # Plain text format
                result = self.current_tab_result
                lines = []
                lines.append(f"Compare Results: {result.old_name} vs {result.new_name}")
                lines.append("=" * 60)
                lines.append(f"Rules in OLD only: {len(result.old_only_rules)}")
                lines.append(f"Rules in NEW only: {len(result.new_only_rules)}")
                lines.append(f"Common rules: {len(result.common_rules)}")
                lines.append("")
                lines.append("REMOVED RULES:")
                lines.append("-" * 60)
                for rule in result.old_only_rules:
                    lines.append(f"  - [{rule.get('action', '')}] {rule.get('raw', '')}")
                lines.append("")
                lines.append("ADDED RULES:")
                lines.append("-" * 60)
                for rule in result.new_only_rules:
                    lines.append(f"  + [{rule.get('action', '')}] {rule.get('raw', '')}")
                ExportManager.export_to_text("\n".join(lines), filename)

        elif self.current_tab_id == "acls":
            # Export ACL usage results
            if not self.current_tab_result:
                raise ValueError("No ACL usage data available")

            if format_type == "json":
                export_data = format_usage_json(self.current_tab_result)
                ExportManager.export_to_json(export_data, filename)
            elif format_type == "csv":
                headers, rows = ExportManager.format_usage_for_csv(self.current_tab_result)
                ExportManager.export_to_csv(headers, rows, filename)
            elif format_type == "txt":
                # Plain text format with original config syntax
                result = self.current_tab_result
                obj_config = self.selected_object.get('config', self.parsed_config)
                obj_name = result.object_name

                lines = []
                lines.append("!" * 70)
                lines.append(f"! ACL Usage Report: {obj_name}")
                lines.append(f"! Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                lines.append(f"! Total references: {result.total_references}")
                lines.append("!" * 70)
                lines.append("")

                # 1. Object definition in original syntax
                lines.append("!" + "=" * 68)
                lines.append("! OBJECT DEFINITION")
                lines.append("!" + "=" * 68)
                if hasattr(obj_config, 'network_object_literals'):
                    if obj_name in obj_config.network_object_literals:
                        obj_def = obj_config.network_object_literals[obj_name]
                        lines.append(f"object network {obj_name}")
                        lines.append(f" {obj_def}")
                lines.append("")

                # 2. Group membership definitions (where this object is referenced)
                if result.group_memberships:
                    lines.append("!" + "=" * 68)
                    lines.append(f"! GROUP MEMBERSHIPS ({len(result.group_memberships)})")
                    lines.append("!" + "=" * 68)
                    for group in result.group_memberships:
                        lines.append(f"object-group network {group}")
                        lines.append(f" network-object object {obj_name}")
                        lines.append("!")
                    lines.append("")

                # 3. Direct ACL references (clean format)
                if result.direct_acl_references:
                    lines.append("!" + "=" * 68)
                    lines.append(f"! DIRECT ACL REFERENCES ({len(result.direct_acl_references)})")
                    lines.append("!" + "=" * 68)
                    for ref in result.direct_acl_references:
                        lines.append(ref.get('raw', ''))
                    lines.append("")

                # 4. Indirect ACL references (via groups)
                if result.indirect_acl_references:
                    lines.append("!" + "=" * 68)
                    lines.append(f"! INDIRECT ACL REFERENCES ({len(result.indirect_acl_references)})")
                    lines.append(f"! (Rules that reference groups containing {obj_name})")
                    lines.append("!" + "=" * 68)

                    # Group by via_group for clarity
                    by_group = {}
                    for ref in result.indirect_acl_references:
                        via = ref.get('via_group', 'unknown')
                        if via not in by_group:
                            by_group[via] = []
                        by_group[via].append(ref)

                    for group_name, refs in by_group.items():
                        lines.append(f"! Via group: {group_name}")
                        for ref in refs:
                            lines.append(ref.get('raw', ''))
                        lines.append("!")
                    lines.append("")

                ExportManager.export_to_text("\n".join(lines), filename)

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
