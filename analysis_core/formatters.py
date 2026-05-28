# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
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
    from .acl_usage import UsageResult


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

    if isinstance(endpoint_list, set):
        endpoints = sorted(endpoint_list, key=lambda value: str(value))
    elif isinstance(endpoint_list, (list, tuple)):
        endpoints = list(endpoint_list)
    else:
        try:
            endpoints = list(endpoint_list)  # type: ignore[arg-type]
        except TypeError:
            endpoints = [endpoint_list]

    if not endpoints:
        return "any"
    if len(endpoints) == 1:
        return str(endpoints[0])
    return f"{endpoints[0]} (+{len(endpoints)-1})"


def _format_service(rule: dict) -> str:
    """Format service/protocol info from rule."""
    svc = rule.get("svc") or {}
    proto = svc.get("proto") or rule.get("proto") or "any"

    service_parts = []
    if proto and proto != "any":
        service_parts.append(proto)

    port_chunks: List[str] = []

    for op, (p1, p2) in svc.get("dst_ports", []):
        if op == "range" and p1 is not None and p2 is not None and p1 != p2:
            port_chunks.append(f"{p1}-{p2}")
        elif p1 is not None:
            port_chunks.append(f"{op} {p1}")
    for name in svc.get("dst_service_groups", []) or []:
        port_chunks.append(f"group:{name}")
    for name in svc.get("dst_service_objects", []) or []:
        port_chunks.append(f"object:{name}")

    if port_chunks:
        service_parts.append("ports=" + ",".join(port_chunks))
    elif "service" in rule and rule["service"]:
        service_parts.append(str(rule["service"]))

    if not service_parts:
        return "any"
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


def format_usage_rich(result: UsageResult) -> Group:
    """Format UsageResult as Rich renderable for TUI.

    Args:
        result: UsageResult to format

    Returns:
        Rich Group containing formatted usage information
    """
    # Summary panel
    summary_text = Text()
    summary_text.append(f"Object: ", style="bold cyan")
    summary_text.append(f"{result.object_name}\n", style="bold white")

    summary_text.append(f"Total references: ", style="bold cyan")
    summary_text.append(f"{result.total_references}\n", style="yellow")

    summary_text.append(f"Direct ACL references: ", style="bold cyan")
    summary_text.append(f"{len(result.direct_acl_references)}\n")

    summary_text.append(f"Group memberships: ", style="bold cyan")
    summary_text.append(f"{len(result.group_memberships)}\n")

    summary_text.append(f"Indirect ACL references: ", style="bold cyan")
    summary_text.append(f"{len(result.indirect_acl_references)}\n")

    summary_panel = Panel(summary_text, title="[bold]Object Usage Summary[/bold]", border_style="cyan")

    renderables = [summary_panel]

    # Group memberships
    if result.group_memberships:
        groups_table = Table(title="Group Memberships", show_header=True, header_style="bold magenta")
        groups_table.add_column("Group Name", style="cyan")

        for group_name in result.group_memberships:
            groups_table.add_row(group_name)

        renderables.append(groups_table)

    # Direct ACL references
    if result.direct_acl_references:
        direct_table = Table(title="Direct ACL References", show_header=True, header_style="bold green")
        direct_table.add_column("ACL", style="cyan", width=25)
        direct_table.add_column("Line", style="dim", width=6)
        direct_table.add_column("Action", style="bold", width=8)
        direct_table.add_column("Rule", style="white", width=50)

        for ref in result.direct_acl_references[:20]:  # Limit to 20
            action_style = "green" if ref.get("action") == "permit" else "red"
            direct_table.add_row(
                ref.get("acl", "unknown"),
                str(ref.get("line", "")),
                Text(ref.get("action", ""), style=action_style),
                ref.get("raw", "")[:50]  # Truncate long rules
            )

        renderables.append(direct_table)

    # Indirect ACL references (via groups)
    if result.indirect_acl_references:
        indirect_table = Table(title="Indirect ACL References (via groups)", show_header=True, header_style="bold blue")
        indirect_table.add_column("ACL", style="cyan", width=25)
        indirect_table.add_column("Via Group", style="magenta", width=25)
        indirect_table.add_column("Action", style="bold", width=8)

        for ref in result.indirect_acl_references[:20]:  # Limit to 20
            action_style = "green" if ref.get("action") == "permit" else "red"
            indirect_table.add_row(
                ref.get("acl", "unknown"),
                ref.get("via_group", ""),
                Text(ref.get("action", ""), style=action_style)
            )

        renderables.append(indirect_table)

    return Group(*renderables)


def format_usage_json(result: UsageResult) -> dict:
    """Format UsageResult as JSON dict for API.

    Args:
        result: UsageResult to format

    Returns:
        Dictionary ready for JSON serialization
    """
    return {
        "object_name": result.object_name,
        "total_references": result.total_references,
        "direct_acl_references": result.direct_acl_references,
        "group_memberships": result.group_memberships,
        "indirect_acl_references": result.indirect_acl_references,
        "summary": {
            "direct": len(result.direct_acl_references),
            "groups": len(result.group_memberships),
            "indirect": len(result.indirect_acl_references),
        }
    }
