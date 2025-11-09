"""Output formatters for analysis results.

Provides formatting functions for different output targets:
- Rich (for TUI)
- HTML (for Web UI)
- JSON (for API)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich.console import Group

if TYPE_CHECKING:
    from .inspect import InspectResult
    from .compare import CompareResult


def format_inspect_rich(result: InspectResult) -> Group:
    """Format InspectResult as Rich renderable for TUI.

    Args:
        result: InspectResult to format

    Returns:
        Rich Group containing formatted tables and panels
    """
    # Summary panel
    summary_text = Text()
    summary_text.append(f"Object: ", style="bold cyan")
    summary_text.append(f"{result.object_name}\n", style="bold white")

    summary_text.append(f"Resolved to: ", style="bold cyan")
    if result.resolved_addresses:
        summary_text.append(", ".join(result.resolved_addresses[:5]), style="green")
        if len(result.resolved_addresses) > 5:
            summary_text.append(f" (+{len(result.resolved_addresses) - 5} more)", style="dim")
    else:
        summary_text.append("(not found)", style="red")
    summary_text.append("\n")

    summary_text.append(f"Matching rules: ", style="bold cyan")
    summary_text.append(f"{result.total_rules}\n", style="yellow")

    if result.duplicates:
        summary_text.append(f"Aliases: ", style="bold cyan")
        summary_text.append(", ".join(result.duplicates[:3]), style="magenta")
        if len(result.duplicates) > 3:
            summary_text.append(f" (+{len(result.duplicates) - 3} more)", style="dim")
        summary_text.append("\n")

    summary_panel = Panel(summary_text, title="[bold]Inspection Summary[/bold]", border_style="cyan")

    # Rules table
    if result.matching_rules:
        rules_table = Table(title="Matching ACL Rules", show_header=True, header_style="bold magenta")
        rules_table.add_column("ACL", style="cyan", width=20)
        rules_table.add_column("Action", style="bold", width=8)
        rules_table.add_column("Source", style="green", width=25)
        rules_table.add_column("Destination", style="blue", width=25)
        rules_table.add_column("Service", style="yellow", width=15)

        for rule in result.matching_rules[:50]:  # Limit to 50 for display
            # Parse rule fields
            acl_name = rule.get("acl", "unknown")
            action = rule.get("action", "unknown")
            action_style = "green" if action == "permit" else "red"

            # Format source/dest
            src = _format_endpoint(rule.get("src", []))
            dst = _format_endpoint(rule.get("dst", []))

            # Format service
            service = _format_service(rule)

            rules_table.add_row(
                acl_name,
                Text(action, style=action_style),
                src,
                dst,
                service
            )

        if len(result.matching_rules) > 50:
            footer = Text(f"\n... and {len(result.matching_rules) - 50} more rules", style="dim italic")
            return Group(summary_panel, rules_table, footer)
        else:
            return Group(summary_panel, rules_table)
    else:
        no_rules = Text("No matching ACL rules found.", style="dim italic")
        return Group(summary_panel, no_rules)


def format_compare_rich(result: CompareResult) -> Group:
    """Format CompareResult as Rich renderable for TUI.

    Args:
        result: CompareResult to format

    Returns:
        Rich Group containing comparison tables
    """
    # Summary panel
    summary_text = Text()
    summary_text.append(f"Comparing: ", style="bold cyan")
    summary_text.append(f"{result.old_name}", style="red")
    summary_text.append(" → ", style="dim")
    summary_text.append(f"{result.new_name}\n", style="green")

    summary_text.append(f"Removed rules: ", style="bold red")
    summary_text.append(f"{len(result.old_only_rules)}\n")

    summary_text.append(f"Added rules: ", style="bold green")
    summary_text.append(f"{len(result.new_only_rules)}\n")

    summary_text.append(f"Common rules: ", style="bold blue")
    summary_text.append(f"{len(result.common_rules)}\n")

    summary_panel = Panel(summary_text, title="[bold]Comparison Summary[/bold]", border_style="cyan")

    tables = [summary_panel]

    # Rules being removed (old only)
    if result.old_only_rules:
        removed_table = Table(title="Rules Being Removed", show_header=True, header_style="bold red")
        removed_table.add_column("ACL", style="cyan", width=20)
        removed_table.add_column("Action", style="bold", width=8)
        removed_table.add_column("Rule", style="white", width=60)

        for rule in result.old_only_rules[:20]:
            acl_name = rule.get("acl", "unknown")
            action = rule.get("action", "unknown")
            raw = rule.get("raw", str(rule))
            removed_table.add_row(acl_name, action, raw)

        tables.append(removed_table)

    # Rules being added (new only)
    if result.new_only_rules:
        added_table = Table(title="Rules Being Added", show_header=True, header_style="bold green")
        added_table.add_column("ACL", style="cyan", width=20)
        added_table.add_column("Action", style="bold", width=8)
        added_table.add_column("Rule", style="white", width=60)

        for rule in result.new_only_rules[:20]:
            acl_name = rule.get("acl", "unknown")
            action = rule.get("action", "unknown")
            raw = rule.get("raw", str(rule))
            added_table.add_row(acl_name, action, raw)

        tables.append(added_table)

    return Group(*tables)


def _format_endpoint(endpoint_list) -> str:
    """Format endpoint (src/dst) for display."""
    if not endpoint_list:
        return "any"
    if len(endpoint_list) == 1:
        return str(endpoint_list[0])
    else:
        return f"{endpoint_list[0]} (+{len(endpoint_list)-1})"


def _format_service(rule: dict) -> str:
    """Format service/protocol info from rule."""
    proto = rule.get("proto", "any")
    if proto == "any":
        return "any"

    service_parts = [proto]

    # Add ports if present
    if "service" in rule:
        service_parts.append(str(rule["service"]))

    return " ".join(service_parts)


def format_inspect_json(result: InspectResult) -> dict:
    """Format InspectResult as JSON dict for API.

    Args:
        result: InspectResult to format

    Returns:
        Dictionary ready for JSON serialization
    """
    return {
        "object_name": result.object_name,
        "resolved_addresses": result.resolved_addresses,
        "total_rules": result.total_rules,
        "duplicates": result.duplicates,
        "matching_rules": result.matching_rules,
    }


def format_compare_json(result: CompareResult) -> dict:
    """Format CompareResult as JSON dict for API.

    Args:
        result: CompareResult to format

    Returns:
        Dictionary ready for JSON serialization
    """
    return {
        "old_name": result.old_name,
        "new_name": result.new_name,
        "old_only_rules": result.old_only_rules,
        "new_only_rules": result.new_only_rules,
        "common_rules": result.common_rules,
        "summary": {
            "removed": len(result.old_only_rules),
            "added": len(result.new_only_rules),
            "common": len(result.common_rules),
        }
    }
