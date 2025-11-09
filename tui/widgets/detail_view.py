"""Detail view widget showing full object information."""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from textual.widgets import Static
from textual.containers import VerticalScroll
from rich.text import Text
from rich.table import Table
from rich.console import Group, RenderableType


class DetailView(VerticalScroll):
    """Panel showing detailed information about a selected object."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_object: Optional[Dict[str, Any]] = None

    def compose(self):
        """Compose child widgets."""
        yield Static("Select an item to view details", classes="detail-placeholder")

    def show_content(self, content: RenderableType) -> None:
        """Show arbitrary Rich renderable content.

        Args:
            content: Any Rich renderable (Table, Panel, Group, etc.)
        """
        self.remove_children()
        self.mount(Static(content, classes="detail-content"))

    def update_object(self, obj: Dict[str, Any], config=None) -> None:
        """Update the displayed object details.

        Args:
            obj: Dictionary with 'name', 'type', 'detail' keys
            config: Optional ASAConfig object for additional lookups
        """
        self.current_object = obj

        # Clear existing content
        self.remove_children()

        # Create rich content
        content = self._format_detail(obj, config)
        self.mount(Static(content, classes="detail-content"))

    def _format_detail(self, obj: Dict[str, Any], config=None) -> Table:
        """Format object details as a Rich table.

        Args:
            obj: Object dictionary
            config: Optional ASAConfig for lookups

        Returns:
            Rich Table with formatted details
        """
        name = obj.get("name", "Unknown")
        obj_type = obj.get("type", "unknown")
        detail = obj.get("detail", "")

        table = Table(title=f"Details: {name}", title_style="bold cyan", show_header=False)
        table.add_column("Property", style="bold yellow", width=20)
        table.add_column("Value", style="white")

        table.add_row("Name", name)
        table.add_row("Type", obj_type.upper())

        if detail:
            table.add_row("Summary", detail)

        # If we have config, get more details
        if config:
            if obj_type == "object":
                # Network object - show all IPs
                if hasattr(config, 'network_objects') and name in config.network_objects:
                    networks = config.network_objects[name]
                    network_list = "\n".join(str(net) for net in networks)
                    table.add_row("IP Addresses", network_list if network_list else "None")
                    table.add_row("Count", str(len(networks)))

            elif obj_type == "group":
                # Object group - show members
                if hasattr(config, 'network_object_groups') and name in config.network_object_groups:
                    members = config.network_object_groups[name]
                    # Members can be dicts, addresses, or networks
                    member_strs = []
                    for member in members[:10]:  # Limit to first 10
                        if isinstance(member, dict):
                            member_strs.append(member.get('name', str(member)))
                        else:
                            member_strs.append(str(member))

                    member_list = "\n".join(member_strs)
                    if len(members) > 10:
                        member_list += f"\n... and {len(members) - 10} more"

                    table.add_row("Members", member_list if member_list else "None")
                    table.add_row("Total Members", str(len(members)))

        # Add usage info (placeholder for now)
        table.add_row("Used In", "ACL analysis coming soon")

        # Add help text
        table.add_row("", "")
        table.add_row("Actions", "[ESC] Close detail view")

        return table

    def clear(self) -> None:
        """Clear the detail view."""
        self.current_object = None
        self.remove_children()
        self.mount(Static("Select an item to view details", classes="detail-placeholder"))
