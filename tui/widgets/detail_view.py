"""Detail view widget showing full object information."""

from __future__ import annotations

from typing import Any, Dict, Optional, Union, List

from textual.widgets import Static, Input
from textual.containers import VerticalScroll, Vertical
from textual.message import Message
from textual import events
from textual._context import NoActiveAppError
from rich.text import Text
from rich.table import Table
from rich.console import Group, RenderableType
from rich.panel import Panel


class DetailView(VerticalScroll):
    """Panel showing detailed information about a selected object."""

    class CompareRequested(Message):
        """Posted when user wants to compare two objects."""

        def __init__(self, old_obj: Dict[str, Any], new_obj: Dict[str, Any]) -> None:
            self.old_obj = old_obj
            self.new_obj = new_obj
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_object: Optional[Dict[str, Any]] = None
        self.compare_mode: bool = False
        self.compare_input: Optional[Input] = None
        self.compare_suggestions: List[Dict[str, Any]] = []
        self.compare_suggestions_widget: Optional[Static] = None
        self.compare_filtered_suggestions: List[Dict[str, Any]] = []
        self.compare_selected_index: int = 0

    def _safe_remove_children(self) -> None:
        """Remove child widgets without requiring an active app context."""
        try:
            super().remove_children()
        except NoActiveAppError:
            pass

    def compose(self):
        """Compose child widgets."""
        yield Static("Select an item to view details", classes="detail-placeholder")

    def show_content(self, content: RenderableType) -> None:
        """Show arbitrary Rich renderable content.

        Args:
            content: Any Rich renderable (Table, Panel, Group, etc.)
        """
        self._safe_remove_children()
        self.mount(Static(content, classes="detail-content"))

    def update_object(self, obj: Dict[str, Any], config=None) -> None:
        """Update the displayed object details.

        Args:
            obj: Dictionary with 'name', 'type', 'detail' keys
            config: Optional ASAConfig object for additional lookups
        """
        self.current_object = obj

        # Clear existing content
        self._safe_remove_children()

        # Create rich content
        content = self._format_detail(obj, config)
        self.mount(Static(content, classes="detail-content"))

    def _format_detail(self, obj: Dict[str, Any], config=None) -> RenderableType:
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

        # Add source file if available
        source_file = obj.get("source_file", "")
        if source_file:
            table.add_row("Source", source_file)
        vendor = obj.get("vendor")
        if vendor:
            table.add_row("Vendor", vendor.upper())
        vdom = obj.get("vdom")
        if vdom:
            table.add_row("VDOM", vdom)

        if detail:
            table.add_row("Summary", detail)

        # If we have config, get more details
        extra_renderables: List[RenderableType] = []

        if config:
            if obj_type == "object":
                # Network object - show ALL IPs (no limit)
                if hasattr(config, 'network_objects') and name in config.network_objects:
                    networks = config.network_objects[name]
                    network_list = "\n".join(str(net) for net in networks)
                    table.add_row("IP Addresses", network_list if network_list else "None")
                    table.add_row("Total Count", str(len(networks)))

                    # Show if this object is used in any groups
                    if hasattr(config, 'network_object_groups'):
                        containing_groups = []
                        for group_name, group_members in config.network_object_groups.items():
                            for member in group_members:
                                if isinstance(member, dict) and member.get('name') == name:
                                    containing_groups.append(group_name)
                                    break

                        if containing_groups:
                            table.add_row("Member of Groups", "\n".join(containing_groups[:10]))
                            if len(containing_groups) > 10:
                                table.add_row("", f"... and {len(containing_groups) - 10} more")

            elif obj_type == "group":
                # Object group - show ALL members (no limit)
                if hasattr(config, 'network_object_groups') and name in config.network_object_groups:
                    members = config.network_object_groups[name]
                    # Members can be dicts, addresses, or networks
                    member_strs = []
                    for member in members:
                        if isinstance(member, dict):
                            member_strs.append(member.get('name', str(member)))
                        else:
                            member_strs.append(str(member))

                    member_list = "\n".join(member_strs)
                    table.add_row("Members", member_list if member_list else "None")
                    table.add_row("Total Members", str(len(members)))

                    # Show nested groups if any
                    nested_groups = [m.get('name') for m in members if isinstance(m, dict) and m.get('type') == 'group-object']
                    if nested_groups:
                        table.add_row("Nested Groups", str(len(nested_groups)))
            elif obj_type == "config":
                if hasattr(config, 'network_objects'):
                    table.add_row("Objects", str(len(getattr(config, 'network_objects', {}))))
                if hasattr(config, 'network_object_groups'):
                    table.add_row("Groups", str(len(getattr(config, 'network_object_groups', {}))))
                if hasattr(config, 'addresses'):
                    table.add_row("Addresses", str(len(getattr(config, 'addresses', {}))))
                if hasattr(config, 'addrgrps'):
                    table.add_row("Addr Groups", str(len(getattr(config, 'addrgrps', {}))))
                if hasattr(config, 'acls'):
                    table.add_row("ACLs", str(len(getattr(config, 'acls', {}))))
                raw_text = getattr(config, "raw_text", "")
                if raw_text:
                    config_panel = Panel(Text(raw_text), title="Raw configuration", border_style="blue")
                    extra_renderables.append(config_panel)

        # Add help text
        table.add_row("", "")
        table.add_row("Actions", "[ESC] Close detail view")

        if extra_renderables:
            return Group(table, *extra_renderables)
        return table

    def clear(self) -> None:
        """Clear the detail view."""
        self.current_object = None
        self.compare_mode = False
        self._safe_remove_children()
        self.mount(Static("Select an item to view details", classes="detail-placeholder"))

    def show_compare_prompt(self, base_obj: Dict[str, Any], all_objects: Optional[List[Dict[str, Any]]] = None) -> None:
        """Show UI for entering second object to compare with.

        Args:
            base_obj: The first object (already selected)
            all_objects: Optional list of all available objects for suggestions
        """
        self.current_object = base_obj
        self.compare_mode = True
        self.compare_suggestions = all_objects if all_objects else []

        # Create help text and input field
        help_text = Text()
        help_text.append("Compare Mode\n\n", style="bold cyan")
        help_text.append("First object: ", style="yellow")
        help_text.append(f"{base_obj['name']}\n\n", style="bold white")
        help_text.append("Enter name or IP of second object to compare with:\n", style="white")
        help_text.append("(Type to filter, Up/Down to select, Enter to compare)\n", style="dim")
        help_text.append("(ESC once: navigate tabs | ESC twice: back to search)\n", style="dim italic")

        # Clear and show compare prompt
        self._safe_remove_children()

        # Mount widgets directly (no container needed since DetailView is VerticalScroll)
        help_static = Static(help_text, classes="detail-content")
        self.mount(help_static)

        # Add input field
        self.compare_input = Input(placeholder="Type object name or IP address...")
        self.mount(self.compare_input)

        # Add suggestions area (initially empty)
        self.compare_suggestions_widget = Static("", classes="detail-content")
        self.mount(self.compare_suggestions_widget)

        self.compare_input.focus()

    def on_input_changed(self, event) -> None:
        """Handle input changes to update compare suggestions."""
        if self.compare_mode and hasattr(event, 'input') and event.input == self.compare_input:
            query = event.value.strip().lower()

            if query and self.compare_suggestions and self.compare_suggestions_widget:
                # Filter suggestions
                matching = [
                    obj for obj in self.compare_suggestions
                    if query in obj.get('name', '').lower()
                ][:10]  # Limit to 10 suggestions

                # Store filtered suggestions and reset selection
                self.compare_filtered_suggestions = matching
                self.compare_selected_index = 0

                if matching:
                    # Create suggestions text
                    self._render_compare_suggestions()
                else:
                    self.compare_suggestions_widget.update(Text("No matching objects", style="dim"))
            else:
                self.compare_filtered_suggestions = []
                self.compare_selected_index = 0
                if self.compare_suggestions_widget:
                    self.compare_suggestions_widget.update("")

    def _render_compare_suggestions(self) -> None:
        """Render the compare suggestions with current selection."""
        if not self.compare_suggestions_widget or not self.compare_filtered_suggestions:
            return

        suggestions_text = Text()
        suggestions_text.append("\nSuggestions:\n", style="bold yellow")
        for i, obj in enumerate(self.compare_filtered_suggestions):
            is_selected = (i == self.compare_selected_index)
            prefix = "▶ " if is_selected else "  "
            style = "bold cyan" if is_selected else "cyan"

            suggestions_text.append(f"{prefix}{obj['name']}", style=style)
            suggestions_text.append(f"  [{obj.get('type', 'unknown')}]", style="dim")
            if 'detail' in obj:
                suggestions_text.append(f"  {obj['detail']}", style="dim")
            suggestions_text.append("\n")

        self.compare_suggestions_widget.update(suggestions_text)

    def on_key(self, event: events.Key) -> None:
        """Handle keyboard navigation in compare mode."""
        if not self.compare_mode or not self.compare_input or not self.compare_input.has_focus:
            return

        # Handle up/down navigation in suggestions
        if event.key in ("down", "j"):
            if self.compare_filtered_suggestions:
                self.compare_selected_index = min(
                    len(self.compare_filtered_suggestions) - 1,
                    self.compare_selected_index + 1
                )
                self._render_compare_suggestions()
                event.prevent_default()
        elif event.key in ("up", "k"):
            if self.compare_filtered_suggestions:
                self.compare_selected_index = max(0, self.compare_selected_index - 1)
                self._render_compare_suggestions()
                event.prevent_default()
        # FIX #2: Left/Right arrows switch tabs directly from Compare input
        elif event.key in ("left", "right"):
            try:
                from .action_tabs import ActionTabs
                action_tabs = self.app.query_one(ActionTabs)
                # Blur input first
                self.compare_input.blur()
                # Focus tabs
                action_tabs.focus()
                # Manually trigger tab navigation
                if event.key == "left":
                    action_tabs.action_previous_tab()
                elif event.key == "right":
                    action_tabs.action_next_tab()
                event.stop()
            except:
                pass
        # FIX #3: ESC immediately focuses tabs (no need for second arrow key)
        elif event.key == "escape":
            if self.compare_input.has_focus:
                self.compare_input.blur()
                # Immediately focus the action tabs
                try:
                    from .action_tabs import ActionTabs
                    action_tabs = self.app.query_one(ActionTabs)
                    action_tabs.focus()
                except:
                    pass
                event.stop()  # Stop ESC from exiting drill-down
            # If already blurred, don't stop - let parent handle it

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle comparison input submission."""
        if self.compare_mode and event.input == self.compare_input:
            # If we have filtered suggestions, use the selected one
            if self.compare_filtered_suggestions and 0 <= self.compare_selected_index < len(self.compare_filtered_suggestions):
                selected_obj = self.compare_filtered_suggestions[self.compare_selected_index]
                compare_target = selected_obj['name']
            else:
                # Otherwise use typed value
                compare_target = event.value.strip()

            if compare_target and self.current_object:
                # Post comparison request message
                self.post_message(
                    self.CompareRequested(
                        old_obj=self.current_object,
                        new_obj={"name": compare_target}  # Simple dict with just name
                    )
                )

    def show_compare_results(self, base_obj: Dict[str, Any], compare_obj: Dict[str, Any], config) -> None:
        """Show comparison results between two objects.

        Args:
            base_obj: First object
            compare_obj: Second object to compare with
            config: Parsed configuration object
        """
        from analysis_core import compare_objects
        from rich.console import Group
        from rich.panel import Panel

        try:
            # Perform comparison
            result = compare_objects(
                config,
                old_target=base_obj['name'],
                new_target=compare_obj['name'],
                include_any=False
            )

            # Create enhanced diff view
            content_parts = []

            # Header with object names
            header = Text()
            header.append("Comparing: ", style="bold cyan")
            header.append(f"{result.old_name}", style="bold red")
            header.append(" ← → ", style="dim")
            header.append(f"{result.new_name}\n", style="bold green")
            content_parts.append(header)

            # Summary stats table
            summary_table = Table(show_header=False, box=None, padding=(0, 2))
            summary_table.add_column("Label", style="yellow")
            summary_table.add_column("Count", justify="right", style="bold")

            summary_table.add_row("Rules only in OLD (removed)", f"{len(result.old_only_rules)}", style="red")
            summary_table.add_row("Rules only in NEW (added)", f"{len(result.new_only_rules)}", style="green")
            summary_table.add_row("Common rules (unchanged)", f"{len(result.common_rules)}", style="blue")

            content_parts.append(Panel(summary_table, title="[bold]Summary[/bold]", border_style="cyan"))

            # Removed rules (compact format)
            if result.old_only_rules:
                removed_text = Text()
                removed_text.append(f"\n{len(result.old_only_rules)} Rules Being Removed:\n\n", style="bold red")
                for i, rule in enumerate(result.old_only_rules[:15]):
                    action = rule.get("action", "unknown")
                    acl = rule.get("acl", "unknown")
                    raw = rule.get("raw", str(rule))[:80]
                    removed_text.append(f"  - ", style="red")
                    removed_text.append(f"[{action}] ", style="bold red")
                    removed_text.append(f"{raw}", style="dim")
                    removed_text.append(f" ({acl})\n", style="dim italic")

                if len(result.old_only_rules) > 15:
                    removed_text.append(f"  ... and {len(result.old_only_rules) - 15} more\n", style="dim")

                content_parts.append(removed_text)

            # Added rules (compact format)
            if result.new_only_rules:
                added_text = Text()
                added_text.append(f"\n{len(result.new_only_rules)} Rules Being Added:\n\n", style="bold green")
                for i, rule in enumerate(result.new_only_rules[:15]):
                    action = rule.get("action", "unknown")
                    acl = rule.get("acl", "unknown")
                    raw = rule.get("raw", str(rule))[:80]
                    added_text.append(f"  + ", style="green")
                    added_text.append(f"[{action}] ", style="bold green")
                    added_text.append(f"{raw}", style="dim")
                    added_text.append(f" ({acl})\n", style="dim italic")

                if len(result.new_only_rules) > 15:
                    added_text.append(f"  ... and {len(result.new_only_rules) - 15} more\n", style="dim")

                content_parts.append(added_text)

            # Common rules (collapsed by default, just count)
            if result.common_rules:
                common_text = Text()
                common_text.append(f"\n{len(result.common_rules)} Common Rules:\n", style="bold blue")
                common_text.append(f"  (same in both configurations)\n", style="dim italic")
                content_parts.append(common_text)

            # Action hints
            hints = Text()
            hints.append("\nPress ESC to exit comparison", style="dim italic")
            content_parts.append(hints)

            # Display all parts
            self._safe_remove_children()
            self.mount(Static(Group(*content_parts), classes="detail-content"))

        except Exception as e:
            # Show error
            error_text = Text()
            error_text.append("Comparison Error\n\n", style="bold red")
            error_text.append(f"{str(e)}", style="white")
            self._safe_remove_children()
            self.mount(Static(error_text, classes="detail-content"))
