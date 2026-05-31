# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Main Textual application for Singularity TUI."""

from __future__ import annotations

import logging
import signal
from datetime import datetime
import os
from pathlib import Path
from collections.abc import MutableMapping
from typing import Dict, List, Any, Optional, Set, Tuple

# Suppress Textual's Ctrl+C nag; we handle SIGINT ourselves.
os.environ.setdefault("TEXTUAL_DISABLE_EARLY_EXIT", "1")

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Static, Input
from textual.binding import Binding
from textual.css.query import NoMatches
from rich.text import Text

from .widgets.search_bar import SearchBar
from .widgets.suggestion_list import SuggestionList
from .widgets.status_bar import StatusBar
from .widgets.detail_view import DetailView
from .widgets.action_tabs import ActionTabs
from common.vendor_caps import get_caps, VendorCaps
from analysis_core import path_check_supported
from parsers.suggest import as_str_list


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


class ParsedConfigStore(MutableMapping):
    """Mapping that prefers path keys but falls back to filenames when requested."""

    def __init__(self):
        self._store: Dict[str, Any] = {}

    def __getitem__(self, key: str) -> Any:
        if key in self._store:
            return self._store[key]
        for path, value in self._store.items():
            if Path(path).name == key:
                return value
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self._store[key] = value

    def __delitem__(self, key: str) -> None:
        del self._store[key]

    def __iter__(self):
        return iter(self._store)

    def __len__(self) -> int:
        return len(self._store)

    def items(self):
        return self._store.items()

    def keys(self):
        return self._store.keys()

    def values(self):
        return self._store.values()

    def clear(self) -> None:
        self._store.clear()

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


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

    #vendor-hint {
        width: 100%;
        padding: 0 0 1 0;
        color: $text-muted;
        text-style: italic;
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
        Binding("ctrl+v", "toggle_path_verify", "Verify cmds", show=False),
        Binding("/", "focus_search", "Search", show=False),
        Binding("escape", "close_detail_or_clear", "Close/Clear", show=False),
    ]

    def __init__(
        self,
        vendor: str = "asa",
        config_path: str = "",
        vdom: str = "",
        vendor_targets: Optional[List[tuple]] = None,
    ):
        super().__init__()
        self.vendor = vendor
        self.config_path = config_path
        self.vdom = vdom
        self.vendor_targets: List[Tuple[str, str]] = vendor_targets or [(vendor, config_path)]
        self.config_files: List[str] = []
        self.parsed_configs = ParsedConfigStore()
        self.parsed_config: Optional[Any] = None
        self.search_results: List[Dict[str, Any]] = []
        self.display_results: List[Dict[str, Any]] = []
        self.last_results: List[Dict[str, Any]] = []
        self.last_query: str = ""
        self.all_objects: List[Dict[str, Any]] = []
        self.selected_object: Optional[Dict[str, Any]] = None
        self.drill_down_active = False
        self.last_selected_index = 0  # Track which item was selected
        self.modal_depth = 0
        self.title_summary = f"[{self.vendor.upper()}] {self.config_path or 'No config loaded'}"
        self.loaded_vendors: Set[str] = set()
        self.is_directory: bool = False

        # Initialize settings manager
        from .state import TUISettings
        self.settings = TUISettings()

        # Track current tab and data for export
        self.current_tab_id = "details"
        self.last_tab_id = "details"
        self.current_tab_data: Optional[Any] = None
        self.current_tab_result: Optional[Any] = None  # Stores InspectResult, CompareResult, etc.

        # Path-check rendering state (for the verification-commands toggle)
        self._path_render_state: Optional[tuple] = None
        self._path_show_verify: bool = False

        # Track inspect filters
        self.inspect_filters: Dict[str, Any] = {
            "protocol": None,
            "port": None,
            "action": None,
        }

        # Result limits from settings (advanced overrides display)
        self.results_limit = self.settings.get(
            "advanced",
            "results_per_page",
            self.settings.get("display", "results_per_page", 20),
        )

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(show_clock=True)

        with Container(id="main-container"):
            # Search section
            with Vertical(id="search-container"):
                yield Static(self.title_summary, classes="title")
                yield Static("", id="vendor-hint")
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

        # Apply settings defaults for vendor/path if provided
        try:
            default_vendor = self.settings.get("config", "last_vendor", self.vendor)
            default_path = self.settings.get("config", "last_path", self.config_path)
            if default_vendor:
                self.vendor = default_vendor
            if default_path:
                self.config_path = default_path
                self.vendor_targets = [(self.vendor, self.config_path)]
        except Exception:
            pass

        # Parse config if vendor targets are configured
        if self.vendor_targets:
            self._load_config()
        else:
            logger.warning("No vendor targets configured")

        # Focus search bar on startup
        self.query_one(SearchBar).focus()

        self._apply_caps_to_tabs(self.vendor, self.parsed_config)

    def on_key(self, event) -> None:
        """Smart keyboard routing based on context."""
        key = event.key

        if self.modal_depth > 0:
            return

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
                    # If list has focus, let it handle navigation to avoid double-steps
                    if suggestions.has_focus:
                        return
                    # If search bar has focus, steer the suggestion list directly
                    if search_bar.has_focus:
                        if key in ("down", "j"):
                            suggestions.selected_index = min(
                                len(suggestions.results) - 1,
                                suggestions.selected_index + 1
                            )
                        elif key in ("up", "k"):
                            suggestions.selected_index = max(0, suggestions.selected_index - 1)
                        event.prevent_default()
                        return

        # Emergency exit: Ctrl+C should quit immediately
        if key == "ctrl+c":
            try:
                print("\n\n", flush=True)
            except Exception:
                pass
            os._exit(0)

        # Left/Right arrows: change tabs in one step when in drill-down mode
        if key in ("left", "right") and self.drill_down_active:
            from textual.widgets import Input
            focused = self.focused
            # Allow tab switching even when filter/path inputs have focus
            filter_inputs = {"filter-protocol", "filter-port", "filter-action", "path-src", "path-dst", "path-proto", "path-port"}
            if isinstance(focused, Input) and getattr(focused, "id", None) not in filter_inputs:
                return
            action_tabs = self.query_one(ActionTabs)
            if key == "left":
                action_tabs._select_previous_tab()
            else:
                action_tabs._select_next_tab()
            action_tabs.focus()
            event.prevent_default()
            return

    def _default_path_for_vendor(self, vendor: str) -> Path:
        env_map = {
            "asa": os.getenv("ACLINSPECTOR_CONFIGS_CISCO"),
            "fortigate": os.getenv("ACLINSPECTOR_CONFIGS_FORTIGATE"),
        }
        env_path = env_map.get(vendor)
        if env_path:
            return Path(env_path)
        defaults = {
            "asa": Path("configs/cisco"),
            "fortigate": Path("configs/fortigate"),
        }
        return defaults.get(vendor, Path("configs"))

    def _load_config(self) -> None:
        """Load and parse the firewall config(s)."""
        try:
            self.config_files = []
            self.parsed_configs.clear()
            self.all_objects = []
            self.loaded_vendors.clear()
            self.is_directory = False
            self.parsed_config = None

            had_success = False
            for vendor_name, target in self.vendor_targets:
                try:
                    self._load_vendor_configs(vendor_name, target)
                    had_success = True
                except Exception as exc:
                    logger.error(f"Failed to load configs for {vendor_name}: {exc}")
                    self.notify(
                        f"Failed to load {vendor_name} configs: {str(exc)[:80]}",
                        severity="warning",
                        timeout=5,
                    )

            if not had_success:
                raise ValueError("No valid configurations loaded.")

            self._update_title_summary()

        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            logger.error(f"Error loading config: {e}\n{error_details}")
            self.notify(
                f"Failed to load config: {str(e)[:100]}...\nCheck ./logs/TUI.log for details",
                severity="error",
                timeout=10,
            )

    def _load_vendor_configs(self, vendor: str, config_path: str) -> None:
        """Load configs for a specific vendor."""
        base_path = Path(config_path) if config_path else self._default_path_for_vendor(vendor)
        self.is_directory = self.is_directory or base_path.is_dir()
        if not base_path.exists():
            raise ValueError(f"{base_path} does not exist")

        if base_path.is_dir():
            files = sorted(
                str(f)
                for f in base_path.iterdir()
                if f.is_file() and not f.name.startswith(".")
            )
            if not files:
                raise ValueError(f"No config files found in directory: {base_path}")
            for file_path in files:
                self._load_single_config(vendor, file_path)
        else:
            self._load_single_config(vendor, str(base_path))

    def _load_single_config(self, vendor: str, config_file: str) -> None:
        """Load and parse a single config file."""
        filename = Path(config_file).name
        logger.info(f"Loading {vendor} config: {config_file}")

        try:
            if vendor == "asa":
                from parsers.cisco.asa.parser import ASAConfig

                with open(config_file, "r") as handle:
                    config_text = handle.read()
                parsed = ASAConfig(config_text)
                self.parsed_config = parsed
                self._index_asa_objects(parsed, filename, config_file)
                self.config_files.append(config_file)
                self.parsed_configs[config_file] = parsed
                self.loaded_vendors.add(vendor)
                self._add_config_entry(vendor, filename, config_file, parsed)

            elif vendor == "fortigate":
                from parsers.fortigate.config import load_fortigate_vdoms

                with open(config_file, "r") as handle:
                    config_text = handle.read()
                vdoms = load_fortigate_vdoms(config_text, target_vdom=self.vdom or None)
                if not vdoms:
                    raise ValueError(f"No VDOMs parsed from {config_file}")
                for parsed in vdoms:
                    source_key = f"{config_file}#vdom={parsed.vdom or 'default'}"
                    self.parsed_config = parsed
                    self._index_fortigate_objects(parsed, filename, source_key, vendor)
                    self.config_files.append(source_key)
                    self.parsed_configs[source_key] = parsed
                    self.loaded_vendors.add(vendor)
                    self._add_config_entry(vendor, filename, source_key, parsed)
                return

            else:
                raise ValueError(f"Unsupported vendor: {vendor}")

        except Exception as exc:
            logger.error(f"Failed to load {config_file}: {exc}")
            raise

    def _index_asa_objects(self, parsed, filename: str, full_path: str) -> None:
        for obj_name, networks in parsed.network_objects.items():
            detail = ", ".join(str(net) for net in list(networks)[:3])
            if len(networks) > 3:
                detail += f" (+{len(networks) - 3} more)"
            self.all_objects.append(
                {
                    "name": obj_name,
                    "type": "object",
                    "detail": detail,
                    "source_file": filename,
                    "source_path": full_path,
                    "config": parsed,
                    "vendor": "asa",
                }
            )

        for group_name, members in parsed.network_object_groups.items():
            member_count = len(members)
            self.all_objects.append(
                {
                    "name": group_name,
                    "type": "group",
                    "detail": f"{member_count} members",
                    "source_file": filename,
                    "source_path": full_path,
                    "config": parsed,
                    "vendor": "asa",
                }
            )

    def _index_fortigate_objects(self, parsed, filename: str, source_path: str, vendor: str) -> None:
        """Populate object list for FortiGate configs."""
        for obj_name, networks in parsed.addresses.items():
            literals = sorted(str(net) for net in networks)
            detail = ", ".join(literals[:3]) if literals else "dynamic"
            if len(literals) > 3:
                detail += f" (+{len(literals) - 3} more)"
            self.all_objects.append(
                {
                    "name": obj_name,
                    "type": "object",
                    "detail": detail,
                    "source_file": filename,
                    "source_path": source_path,
                    "config": parsed,
                    "vendor": vendor,
                    "vdom": parsed.vdom,
                }
            )

        # VIPs
        for vip_name, vip in getattr(parsed, "vips", {}).items():
            extip = vip.get("extip")
            detail = f"VIP to {extip}" if extip else "VIP"
            self.all_objects.append(
                {
                    "name": vip_name,
                    "type": "vip",
                    "detail": detail,
                    "source_file": filename,
                    "source_path": source_path,
                    "config": parsed,
                    "vendor": vendor,
                    "vdom": parsed.vdom,
                }
            )

        # VIP groups
        for vipgrp_name, members in getattr(parsed, "vipgrps", {}).items():
            detail = f"{len(members)} VIP members"
            self.all_objects.append(
                {
                    "name": vipgrp_name,
                    "type": "vipgrp",
                    "detail": detail,
                    "source_file": filename,
                    "source_path": source_path,
                    "config": parsed,
                    "vendor": vendor,
                    "vdom": parsed.vdom,
                }
            )
        for group_name, members in parsed.addrgrps.items():
            detail = f"{len(members)} members"
            self.all_objects.append(
                {
                    "name": group_name,
                    "type": "group",
                    "detail": detail,
                    "source_file": filename,
                    "source_path": source_path,
                    "config": parsed,
                    "vendor": vendor,
                    "vdom": parsed.vdom,
                }
            )

        # VDOM entry for search visibility
        if getattr(parsed, "vdom", None):
            self.all_objects.append(
                {
                    "name": parsed.vdom,
                    "type": "vdom",
                    "detail": f"VDOM ({len(parsed.policies)} policies)",
                    "source_file": filename,
                    "source_path": source_path,
                    "config": parsed,
                    "vendor": vendor,
                    "vdom": parsed.vdom,
                }
            )

    def _add_config_entry(self, vendor: str, filename: str, full_path: str, parsed) -> None:
        """Add a searchable entry for the raw configuration file."""
        summary_parts: List[str] = []
        if hasattr(parsed, "network_objects"):
            summary_parts.append(f"{len(parsed.network_objects)} objects")
        if hasattr(parsed, "network_object_groups"):
            summary_parts.append(f"{len(parsed.network_object_groups)} groups")
        if hasattr(parsed, "acls"):
            summary_parts.append(f"{len(parsed.acls)} ACLs")
        if hasattr(parsed, "addresses"):
            summary_parts.append(f"{len(parsed.addresses)} addresses")
        if hasattr(parsed, "addrgrps"):
            summary_parts.append(f"{len(parsed.addrgrps)} addrgrps")
        detail = ", ".join(summary_parts) if summary_parts else "Full configuration"
        label_name = filename
        if getattr(parsed, "vdom", None):
            label_name = f"{filename} ({parsed.vdom})"
        self.all_objects.append(
            {
                "name": label_name,
                "type": "config",
                "detail": detail,
                "source_file": filename,
                "source_path": full_path,
                "config": parsed,
                "vendor": vendor,
                "vdom": getattr(parsed, "vdom", None),
            }
        )

    def _update_title_summary(self) -> None:
        if self.loaded_vendors:
            vendors = sorted(self.loaded_vendors)
        else:
            vendors = [self.vendor]

        if len(vendors) > 1:
            summary = f"[MULTI] {len(self.config_files)} configs loaded ({', '.join(vendors).upper()})"
        else:
            label = vendors[0].upper()
            if len(self.config_files) == 1:
                summary = f"[{label}] {Path(self.config_files[0]).name}"
            else:
                summary = f"[{label}] {len(self.config_files)} configs loaded"

        self.title_summary = summary
        try:
            title_static = self.query_one("#search-container Static.title")
            title_static.update(summary)
        except Exception:
            pass

    def _effective_caps(self, vendor: str, config: Optional[Any] = None) -> Optional[VendorCaps]:
        """Return vendor caps adjusted for config-specific support (e.g., path check)."""
        caps = get_caps(vendor)
        if not caps:
            return None
        try:
            if config is not None and not path_check_supported(config):
                caps = VendorCaps(
                    name=caps.name,
                    label=caps.label,
                    config_field=caps.config_field,
                    requires_vdom=caps.requires_vdom,
                    supports_inspect=caps.supports_inspect,
                    supports_compare=caps.supports_compare,
                    supports_find=caps.supports_find,
                    supports_packet=False,
                )
        except Exception:
            pass
        return caps

    def _apply_caps_to_tabs(self, vendor: str, config: Optional[Any] = None) -> None:
        """Update the action tabs when the selected vendor changes."""
        caps = self._effective_caps(vendor, config)
        try:
            self.query_one(ActionTabs).apply_vendor_caps(caps)
        except Exception:
            pass
        self._update_vendor_hint(vendor, caps)

    @staticmethod
    def _describe_vendor_caps(caps: Optional[VendorCaps], vendor: str) -> str:
        """Return a user-facing capability summary string."""
        if caps:
            label = caps.label
            features = []
            if caps.supports_inspect:
                features.append("Inspect")
            if caps.supports_compare:
                features.append("Compare")
            if caps.supports_find:
                features.append("Find")
            if caps.supports_packet:
                features.append("Packet")
            feature_text = ", ".join(features) if features else "No features enabled"
            suffix = "Requires VDOM" if caps.requires_vdom else ""
        elif vendor == "all":
            label = "ALL"
            feature_text = "Multi-vendor: capabilities depend on each config"
            suffix = ""
        else:
            label = vendor.upper() if vendor else "Unknown"
            feature_text = "Capabilities unknown"
            suffix = ""
        parts = [f"{label}: {feature_text}"]
        if suffix:
            parts.append(suffix)
        return " · ".join(parts)

    def _update_vendor_hint(self, vendor: str, caps: Optional[VendorCaps]) -> None:
        """Update the vendor capability hint beneath the title."""
        try:
            widget = self.query_one("#vendor-hint", Static)
        except NoMatches:
            return
        summary = self._describe_vendor_caps(caps, vendor)
        widget.update(Text(summary))

    def _get_object_config(self, obj: Optional[Dict[str, Any]]) -> Optional[Any]:
        if not obj:
            return None
        config = obj.get("config")
        if config is not None:
            return config
        source_path = obj.get("source_path")
        if source_path:
            return self.parsed_configs.get(source_path)
        source_file = obj.get("source_file")
        if source_file:
            return self.parsed_configs.get(source_file)
        return None

    def _format_fortigate_inspect(self, result) -> Group:
        """Build a rich renderable summarizing FortiGate inspect output."""
        from rich.table import Table
        from rich.panel import Panel
        from rich.text import Text
        from rich.console import Group

        header = Text()
        header.append(f"Object: {result.object_name}\n", style="bold cyan")
        header.append("Resolved to: ", style="bold yellow")
        if result.resolved_addresses:
            header.append(", ".join(result.resolved_addresses[:5]), style="green")
            if len(result.resolved_addresses) > 5:
                header.append(f" (+{len(result.resolved_addresses) - 5} more)", style="dim")
        else:
            header.append("(not found)", style="red")
        header.append("\nMatching policies: ", style="bold yellow")
        header.append(str(result.total_rules), style="cyan")

        rules_table = Table(title="Policies", show_lines=True, header_style="bold")
        rules_table.add_column("Policy", justify="left", style="cyan")
        rules_table.add_column("Src Zones", style="green")
        rules_table.add_column("Dst Zones", style="blue")
        rules_table.add_column("Service", style="yellow")
        rules_table.add_column("Action", style="magenta")

        vip_lines: List[str] = []

        for rule in result.matching_rules[:50]:
            binding = rule.get("binding") or {}
            policy = binding.get("policy_id") or binding.get("name") or rule.get("acl", "policy")
            src_zone = ", ".join(binding.get("srczone") or binding.get("srcintf") or ["any"])
            dst_zone = ", ".join(binding.get("dstzone") or binding.get("dstintf") or ["any"])
            svc = self._describe_service(rule)
            action = rule.get("action", "permit")
            rules_table.add_row(str(policy), src_zone, dst_zone, svc, action.upper())

            if binding.get("vip_refs"):
                for vip in binding["vip_refs"]:
                    vip_lines.append(f"{policy}: {vip}")

        extras: List[Panel] = []
        if vip_lines:
            vip_text = "\n".join(vip_lines)
            extras.append(Panel(vip_text, title="VIP References", border_style="blue"))

        if len(result.matching_rules) > 50:
            footer = Text(f"... and {len(result.matching_rules) - 50} more policies", style="dim")
            extras.append(Panel(footer, border_style="dim"))

        return Group(Panel(header, border_style="cyan"), rules_table, *extras)

    @staticmethod
    def _describe_service(rule: dict) -> str:
        svc = rule.get("svc") or {}
        proto = svc.get("proto") or rule.get("proto") or "any"
        parts: List[str] = []
        if proto and proto != "any":
            parts.append(proto)
        ports: List[str] = []
        for op, (p1, p2) in svc.get("dst_ports", []):
            if op == "range" and p1 is not None and p2 is not None and p1 != p2:
                ports.append(f"{p1}-{p2}")
            elif p1 is not None:
                ports.append(f"{op} {p1}")
        for name in svc.get("dst_service_groups", []) or []:
            ports.append(f"group:{name}")
        for name in svc.get("dst_service_objects", []) or []:
            ports.append(f"object:{name}")
        if ports:
            parts.append("ports=" + ",".join(ports))
        return " ".join(parts) if parts else "any"

    def _search_objects(self, query: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return search results for a query."""
        if not query:
            return []
        if limit is None:
            limit = self.results_limit
        query_lower = query.lower()
        matches: List[Dict[str, Any]] = []
        for obj in self.all_objects:
            name_hit = query_lower in obj["name"].lower()
            source_hit = query_lower in (obj.get("source_file", "") or "").lower()
            path_hit = query_lower in (obj.get("source_path", "") or "").lower()
            detail_hit = query_lower in (obj.get("detail", "") or "").lower()
            vdom_hit = query_lower in (obj.get("vdom", "") or "").lower()
            if name_hit or source_hit or path_hit or detail_hit or vdom_hit:
                matches.append(obj)
                if len(matches) >= limit:
                    break
        return matches

    def on_search_bar_searched(self, message: SearchBar.Searched) -> None:
        """Handle debounced search events."""
        query = message.value.strip()

        logger.debug(f"Search event received: query='{query}'")

        if not query:
            self.last_query = ""
            self.last_results = []
            self.display_results = []
            self.clear_results()
            return

        results = self._search_objects(query)
        logger.debug(f"Found {len(results)} matching objects for query '{query}'")

        self.last_query = query.lower()
        self.last_results = results[:]
        self.display_results = results[:]
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
        self.current_tab_id = "details"

        # Save the current selection index from SuggestionList
        suggestions = self.query_one(SuggestionList)
        self.last_selected_index = suggestions.selected_index

        obj_vendor = message.item.get("vendor", self.vendor)
        self._apply_caps_to_tabs(obj_vendor, obj_config)

        # Update breadcrumb
        breadcrumb = self.query_one("#breadcrumb", Static)
        obj_type = message.item.get("type", "object").upper()
        breadcrumb.update(f"▶ Selected: {message.item['name']} [{obj_type}]")

        # Show breadcrumb
        self.query_one("#breadcrumb-container").add_class("visible")
        actions_container = self.query_one("#actions-container")
        actions_container.remove_class("visible")

        # Hide results container (don't show empty list)
        suggestions_container = self.query_one("#suggestions-container")
        suggestions_container.add_class("collapsed")

        # Show detail view with remembered tab (falls back to details)
        detail_view = self.query_one(DetailView)
        obj_config = self._get_object_config(message.item)
        detail_view.update_object(message.item, obj_config)
        self.query_one("#detail-container").add_class("visible")

        is_config_entry = message.item.get("type") == "config"
        try:
            action_tabs = self.query_one(ActionTabs)
            target_tab = "details" if is_config_entry else getattr(self, "last_tab_id", "details") or "details"
            btn = next((b for b in action_tabs._buttons if b.id == f"tab-{target_tab}"), None)
            if btn and btn.hidden:
                target_tab = "details"
            if is_config_entry:
                self.last_tab_id = "details"
            self.current_tab_id = target_tab
            action_tabs._select_tab(target_tab)
            tab_label = next((t["label"] for t in action_tabs.tabs if t["id"] == target_tab), target_tab)
            self.on_action_tabs_tab_selected(ActionTabs.TabSelected(target_tab, tab_label))
        except Exception as exc:
            logger.error(f"Failed to restore tab selection, falling back to details: {exc}", exc_info=True)
            self.current_tab_id = "details"
            try:
                self.on_action_tabs_tab_selected(ActionTabs.TabSelected("details", "Details"))
            except Exception:
                pass

        if is_config_entry:
            actions_container.remove_class("visible")
        else:
            actions_container.add_class("visible")
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
        from rich.panel import Panel
        from textual.widgets import Static, Input
        from .widgets.filter_bar import FilterBar

        detail_view = self.query_one(DetailView)

        if obj_config is None:
            detail_view.remove_children()
            detail_view.mount(
                Static(
                    "No configuration data available for this object.",
                    classes="detail-content",
                )
            )
            self.current_tab_result = None
            return

        # Clear detail view and add filter bar + results container
        detail_view.remove_children()

        # Mount filter bar
        filter_bar = FilterBar()
        detail_view.mount(filter_bar)
        self.current_filter_bar = filter_bar

        # Run inspect with current filters
        try:
            result = inspect_object(
                obj_config,
                self.selected_object['name'],
                protocol=self.inspect_filters.get("protocol"),
                dport=self.inspect_filters.get("port"),
                include_any=False
            )
        except RuntimeError as err:
            detail_view.remove_children()
            detail_view.mount(
                Static(
                    f"Inspect unavailable: {err}",
                    classes="detail-content",
                )
            )
            self.current_tab_result = None
            return

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
        obj_vendor = self.selected_object.get("vendor", self.vendor)
        if obj_vendor == "fortigate":
            rich_content = self._format_fortigate_inspect(result)
        else:
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

        detail_view.mount(Static(rich_content, classes="detail-content"))
        try:
            filter_bar.query_one("#filter-protocol", Input).focus()
        except Exception:
            try:
                detail_view.focus()
            except Exception:
                pass

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
            obj_config = self._get_object_config(self.selected_object)
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
        help_text.append("Destination is pre-filled with the selected object.\n\n", style="dim")

        detail_view.mount(Static(help_text, classes="detail-content"))

        # Form container
        form_container = Vertical(id="path-form")
        detail_view.mount(form_container)

        # Source field
        form_container.mount(Static("Source IP/Object:", classes="filter-field-label"))
        src_input = Input(placeholder="e.g., 10.1.1.1 or InsideHost", id="path-src", classes="filter-input")
        form_container.mount(src_input)

        # Destination field
        form_container.mount(Static("Destination IP/Object:", classes="filter-field-label"))
        dst_input = Input(value=self.selected_object['name'], placeholder="e.g., 10.1.1.1 or WebServer", id="path-dst", classes="filter-input")
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
        from parsers.cisco.asa.path import path_check as asa_path_check
        from parsers.fortigate.path import path_check as forti_path_check
        from rich.table import Table
        from rich.panel import Panel
        from rich.text import Text
        from rich.console import Group
        from textual.widgets import Static

        obj_config = self._get_object_config(self.selected_object)
        if obj_config is None:
            self.notify("No configuration available for this object", severity="error")
            return

        # Get raw config text
        if hasattr(obj_config, 'raw_text'):
            cfg_text = obj_config.raw_text
        else:
            raise ValueError("Config does not have raw_text attribute")

        # Run path check
        dports = {port} if port else set()
        object_vendor = self.selected_object.get("vendor", self.vendor)
        if object_vendor == "fortigate":
            result = forti_path_check(
                cfg_text,
                src=src,
                dst=dst,
                proto=protocol,
                dports=dports,
                include_any=True,
                vdom=self.vdom or getattr(obj_config, "vdom", None),
            )
        else:
            result = asa_path_check(
                cfg_text,
                src=src,
                dst=dst,
                proto=protocol,
                dports=dports,
                include_any=True
            )

        # Store and render. The verification toggle re-renders from this state.
        # Key it by object name so a stale render can't leak across objects.
        obj_name = self.selected_object.get("name") if self.selected_object else None
        self.current_tab_result = result
        # Reset the verify toggle so each new run starts hidden (consistent default).
        self._path_show_verify = False
        self._path_render_state = (obj_name, result, src, dst, protocol, port)
        self._render_path_results()
        logger.info(
            "Path check completed: verdict=%s, NAT=%s, matches=%s",
            result.get("allowed"),
            result.get("nat", {}).get("applied"),
            len(result.get("acl", {}).get("matches", [])),
        )

    def _render_path_results(self) -> None:
        """Render the stored path-check result (incl. correction suggestion).

        Reads ``self._path_render_state`` so the verification toggle
        (``action_toggle_path_verify``) can re-render without re-running the
        path check.
        """
        from rich.panel import Panel
        from rich.text import Text
        from rich.console import Group
        from textual.widgets import Static

        if not self._path_render_state:
            return
        obj_name, result, src, dst, protocol, port = self._path_render_state
        # Don't render stale results for a different (or no) selected object.
        current = self.selected_object.get("name") if self.selected_object else None
        if obj_name != current:
            return
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

        # Correction suggestion (only when the flow is blocked)
        for panel in self._build_path_suggestion_panels(result):
            content_parts.append(panel)

        # Show results
        detail_view = self.query_one(DetailView)
        results_widget = detail_view.query_one("#path-results", Static)
        results_widget.update(Group(*content_parts))

    def _build_path_suggestion_panels(self, result: dict) -> list:
        """Build Rich panels for the correction suggestion + verification toggle."""
        from rich.panel import Panel
        from rich.text import Text

        suggestion = result.get("suggestion") or {}
        if not suggestion.get("needed"):
            return []
        panels = []

        reason = (suggestion.get("reason") or "deny").replace("-", " ").title()
        sugg_text = Text()
        blocking = suggestion.get("blocking_rule") or {}
        if blocking.get("raw"):
            sugg_text.append("Blocked by: ", style="bold red")
            sugg_text.append(f"{blocking['raw']}\n\n", style="dim")
        for idx, sug in enumerate(suggestion.get("suggestions", [])):
            if idx:
                sugg_text.append("\n")
            scenario = (sug.get("scenario") or "").upper()
            sugg_text.append(f"[{scenario}] ", style="bold cyan")
            sugg_text.append(f"{sug.get('rationale', '')}\n", style="white")
            for cmd in as_str_list(sug.get("commands")):
                sugg_text.append(f"  {cmd}\n", style="green")
            for note in as_str_list(sug.get("notes")):
                sugg_text.append(f"  note: {note}\n", style="dim")
        panels.append(Panel(sugg_text, title=f"Correction Suggestion ({reason})",
                            border_style="green"))

        verifications = suggestion.get("verification") or []
        if verifications:
            ver_text = Text()
            if self._path_show_verify:
                for ver in verifications:
                    desc = ver.get("description")
                    if desc:
                        ver_text.append(f"{desc}\n", style="cyan")
                    for line in (ver.get("command") or "").splitlines():
                        ver_text.append(f"  {line}\n", style="green")
                title = "Live Verification (ctrl+v to hide)"
            else:
                ver_text.append(
                    f"{len(verifications)} live-verification command(s) hidden — "
                    "press ctrl+v to show.\n", style="dim")
                title = "Live Verification (ctrl+v to show)"
            panels.append(Panel(ver_text, title=title, border_style="cyan"))
        return panels

    def action_toggle_path_verify(self) -> None:
        """Toggle display of live-verification commands in the path-check view."""
        # Cheap guard: ctrl+v on any other tab has no path results to toggle, so
        # bail before touching render state (avoids relying on the except below).
        if self.current_tab_id != "path":
            return
        current = self.selected_object.get("name") if self.selected_object else None
        # Only act when the stored results belong to the current object.
        if not self._path_render_state or self._path_render_state[0] != current:
            return
        self._path_show_verify = not self._path_show_verify
        try:
            self._render_path_results()
        except Exception as exc:
            # Path results widget not mounted (different tab) — ignore, but log
            # so a real rendering bug isn't silently swallowed during dev.
            logger.debug("toggle_path_verify: render skipped (%s)", exc)

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
        obj_config = self._get_object_config(message.old_obj)

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
        self.last_tab_id = message.tab_id
        self.current_tab_data = None
        self.current_tab_result = None

        detail_view = self.query_one(DetailView)

        # Get the config for the selected object
        obj_config = self._get_object_config(self.selected_object)

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

            self._apply_caps_to_tabs(self.vendor)

            # Hide breadcrumb, actions, and detail
            self.query_one("#breadcrumb-container").remove_class("visible")
            self.query_one("#actions-container").remove_class("visible")
            self.query_one("#detail-container").remove_class("visible")

            # Show suggestions container again
            suggestions_container = self.query_one("#suggestions-container")
            suggestions_container.remove_class("collapsed")

            # Restore full search results (FIX #5b: keep search term)
            search_bar = self.query_one(SearchBar)
            query = search_bar.value.strip().lower() or self.last_query or ""

            # Prefer cached display results to avoid truncation
            cached_results = list(self.display_results or self.last_results or [])
            results = cached_results

            # If cache is empty but query exists, re-run search
            if not results and query:
                results = self._search_objects(query, limit=len(self.all_objects))

            suggestions = self.query_one(SuggestionList)
            suggestions.update_results(results)

            # Restore the previous selection
            if 0 <= self.last_selected_index < len(results):
                suggestions.selected_index = self.last_selected_index

            # Prefer focusing suggestions so arrows continue list navigation
            try:
                suggestions.focus()
            except Exception:
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

    def _push_modal_screen(self, screen, callback=None) -> None:
        """Push a modal screen and track modal depth for key handling."""

        def _wrapped(result):
            self.modal_depth = max(0, self.modal_depth - 1)
            if callback:
                callback(result)

        self.modal_depth += 1
        super().push_screen(screen, _wrapped)

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

        self._push_modal_screen(MenuScreen(self.theme, config_info), handle_menu_result)

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

        self._push_modal_screen(SettingsScreen(self.settings), handle_settings_result)

    def _apply_settings(self) -> None:
        """Apply settings that can be changed at runtime."""
        # Apply theme setting
        theme = self.settings.get("display", "theme", "textual-dark")
        if self.theme != theme:
            self.theme = theme

    def action_show_help(self) -> None:
        """Show help screen."""
        from .screens.help_screen import HelpScreen
        self._push_modal_screen(HelpScreen())

    def action_show_about(self) -> None:
        """Show about screen."""
        from .screens.about_screen import AboutScreen
        self._push_modal_screen(AboutScreen())

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

        self._push_modal_screen(
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
                obj_config = self._get_object_config(self.selected_object)
                if obj_config is None:
                    raise ValueError("No configuration data available")
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
        self.display_results = []
        suggestions = self.query_one(SuggestionList)
        suggestions.update_results([])


def main(argv=None):
    """Entry point for TUI application."""
    import argparse

    parser = argparse.ArgumentParser(description="ACL-inspector Singularity TUI")
    parser.add_argument("--vendor", default="all", choices=["asa", "fortigate", "all"], help="Firewall vendor")
    parser.add_argument("--config", dest="config_path", default="", help="Path to config file")
    parser.add_argument("--vdom", default="", help="FortiGate VDOM (if applicable)")

    args = parser.parse_args(argv)

    if args.vendor == "all":
        vendor_targets = [("asa", args.config_path), ("fortigate", args.config_path)]
    else:
        vendor_targets = [(args.vendor, args.config_path)]

    app = SingularityApp(
        vendor=args.vendor,
        config_path=args.config_path,
        vdom=args.vdom or "",
        vendor_targets=vendor_targets,
    )
    try:
        def _sigint_handler(_sig, _frame):
            try:
                print("\n\n", flush=True)
            except Exception:
                pass
            os._exit(0)

        signal.signal(signal.SIGINT, _sigint_handler)
    except Exception:
        pass
    try:
        app.run()
    except KeyboardInterrupt:
        # Ensure silent exit without Textual admonition
        os._exit(0)


if __name__ == "__main__":
    main()
