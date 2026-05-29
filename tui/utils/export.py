# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Export functionality for TUI tabs."""

from __future__ import annotations

import json
import csv
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime


class ExportManager:
    """Manages data export to various formats."""

    @staticmethod
    def export_to_json(data: Dict[str, Any], filepath: str) -> None:
        """Export data to JSON file.

        Args:
            data: Dictionary to export
            filepath: Path to output file
        """
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    @staticmethod
    def export_to_text(content: str, filepath: str) -> None:
        """Export plain text content to file.

        Args:
            content: Text content to export
            filepath: Path to output file
        """
        with open(filepath, 'w') as f:
            f.write(content)

    @staticmethod
    def export_to_csv(headers: List[str], rows: List[List[Any]], filepath: str) -> None:
        """Export data to CSV file.

        Args:
            headers: Column headers
            rows: Data rows
            filepath: Path to output file
        """
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

    @staticmethod
    def get_export_filename(tab_name: str, object_name: str, format: str) -> str:
        """Generate export filename with timestamp.

        Args:
            tab_name: Name of the tab being exported
            object_name: Name of the object
            format: Export format (json, csv, txt)

        Returns:
            Generated filename
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize object name for filename
        safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in object_name)
        return f"acl_export_{tab_name}_{safe_name}_{timestamp}.{format}"

    @staticmethod
    def format_details_for_export(obj: Dict[str, Any], config: Any) -> Dict[str, Any]:
        """Format object details for export.

        Args:
            obj: Object dictionary
            config: Parsed configuration

        Returns:
            Formatted data dictionary
        """
        export_data = {
            "name": obj.get("name", "Unknown"),
            "type": obj.get("type", "unknown"),
            "detail": obj.get("detail", ""),
            "source_file": obj.get("source_file", ""),
            "exported_at": datetime.now().isoformat(),
        }

        # Add type-specific details
        if config:
            obj_type = obj.get("type", "")
            name = obj.get("name", "")

            if obj_type == "object" and hasattr(config, 'network_objects'):
                if name in config.network_objects:
                    export_data["ip_addresses"] = [str(net) for net in config.network_objects[name]]
                    export_data["count"] = len(config.network_objects[name])

                    # Add group memberships
                    if hasattr(config, 'network_object_groups'):
                        containing_groups = []
                        for group_name, group_members in config.network_object_groups.items():
                            for member in group_members:
                                if isinstance(member, dict) and member.get('name') == name:
                                    containing_groups.append(group_name)
                                    break
                        if containing_groups:
                            export_data["member_of_groups"] = containing_groups

            elif obj_type == "group" and hasattr(config, 'network_object_groups'):
                if name in config.network_object_groups:
                    members = config.network_object_groups[name]
                    member_strs = []
                    for member in members:
                        if isinstance(member, dict):
                            member_strs.append(member.get('name', str(member)))
                        else:
                            member_strs.append(str(member))
                    export_data["members"] = member_strs
                    export_data["member_count"] = len(members)

        return export_data

    @staticmethod
    def format_inspect_for_csv(result: Any) -> tuple[List[str], List[List[Any]]]:
        """Format inspect results for CSV export.

        Args:
            result: InspectResult object

        Returns:
            Tuple of (headers, rows)
        """
        headers = ["ACL", "Action", "Protocol", "Source", "Destination", "Port", "Raw Line"]
        rows = []

        for rule in result.matching_rules:
            row = [
                rule.get("acl", ""),
                rule.get("action", ""),
                rule.get("protocol", ""),
                rule.get("src", ""),
                rule.get("dst", ""),
                rule.get("port", ""),
                rule.get("raw", "")[:200],  # Truncate long lines
            ]
            rows.append(row)

        return headers, rows

    @staticmethod
    def format_compare_for_csv(result: Any) -> tuple[List[str], List[List[Any]]]:
        """Format compare results for CSV export.

        Args:
            result: CompareResult object

        Returns:
            Tuple of (headers, rows)
        """
        headers = ["Status", "ACL", "Action", "Protocol", "Source", "Destination", "Port", "Raw Line"]
        rows = []

        # Old-only rules (removed)
        for rule in result.old_only_rules:
            row = [
                "REMOVED",
                rule.get("acl", ""),
                rule.get("action", ""),
                rule.get("protocol", ""),
                rule.get("src", ""),
                rule.get("dst", ""),
                rule.get("port", ""),
                rule.get("raw", "")[:200],
            ]
            rows.append(row)

        # New-only rules (added)
        for rule in result.new_only_rules:
            row = [
                "ADDED",
                rule.get("acl", ""),
                rule.get("action", ""),
                rule.get("protocol", ""),
                rule.get("src", ""),
                rule.get("dst", ""),
                rule.get("port", ""),
                rule.get("raw", "")[:200],
            ]
            rows.append(row)

        # Common rules
        for rule in result.common_rules:
            row = [
                "UNCHANGED",
                rule.get("acl", ""),
                rule.get("action", ""),
                rule.get("protocol", ""),
                rule.get("src", ""),
                rule.get("dst", ""),
                rule.get("port", ""),
                rule.get("raw", "")[:200],
            ]
            rows.append(row)

        return headers, rows

    @staticmethod
    def format_usage_for_csv(result: Any) -> tuple[List[str], List[List[Any]]]:
        """Format ACL usage results for CSV export.

        Args:
            result: UsageResult object

        Returns:
            Tuple of (headers, rows)
        """
        headers = ["Reference Type", "ACL Name", "Action", "Line", "Raw"]
        rows = []

        # Add direct ACL references
        for ref in result.direct_acl_references:
            row = [
                "Direct",
                ref.get("acl", ""),
                ref.get("action", ""),
                ref.get("line", ""),
                ref.get("raw", "")[:200],
            ]
            rows.append(row)

        # Add group memberships
        for group in result.group_memberships:
            row = [
                "Group",
                group,
                "",
                "",
                f"Member of object-group {group}",
            ]
            rows.append(row)

        # Add indirect ACL references
        for ref in result.indirect_acl_references:
            row = [
                f"Indirect (via {ref.get('via_group', 'group')})",
                ref.get("acl", ""),
                ref.get("action", ""),
                ref.get("line", ""),
                ref.get("raw", "")[:200],
            ]
            rows.append(row)

        return headers, rows
