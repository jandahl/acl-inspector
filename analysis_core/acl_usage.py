"""ACL usage analysis: find where network objects are referenced.

This module provides vendor-agnostic analysis of object usage across ACLs and groups.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Set


@dataclass
class UsageResult:
    """Results from finding where an object is used."""

    object_name: str
    """The network object being analyzed."""

    direct_acl_references: List[Dict[str, Any]]
    """ACL entries that directly reference this object."""

    group_memberships: List[str]
    """Object groups that contain this object."""

    indirect_acl_references: List[Dict[str, Any]]
    """ACL entries that reference groups containing this object."""

    total_references: int
    """Total number of places where this object is used."""

    def __post_init__(self):
        """Calculate derived fields."""
        if self.total_references is None:
            self.total_references = (
                len(self.direct_acl_references) +
                len(self.group_memberships) +
                len(self.indirect_acl_references)
            )


def find_object_usage(
    config,
    object_name: str
) -> UsageResult:
    """Find all places where a network object is used.

    This function searches for:
    1. Direct references in ACL entries
    2. Membership in object groups
    3. Indirect references via group membership

    Args:
        config: Parsed configuration object (ASAConfig, FTGConfig, etc.)
        object_name: Name of the network object to search for

    Returns:
        UsageResult containing all usage locations

    Example:
        >>> config = ASAConfig(config_text)
        >>> result = find_object_usage(config, "WebServer01")
        >>> print(f"Object used in {len(result.group_memberships)} groups")
        >>> for acl_ref in result.direct_acl_references:
        ...     print(f"  ACL {acl_ref['acl']}: line {acl_ref.get('line', 'N/A')}")
    """
    direct_acls = []
    group_memberships = []
    indirect_acls = []

    # Find group memberships
    if hasattr(config, 'network_object_groups'):
        for group_name, members in config.network_object_groups.items():
            # Check if object is a member of this group
            for member in members:
                if isinstance(member, dict):
                    # ASA parser uses 'object' key for object references
                    member_name = member.get('object', member.get('name', ''))
                elif isinstance(member, str):
                    member_name = member
                else:
                    member_name = str(member)

                if member_name == object_name:
                    group_memberships.append(group_name)
                    break

    # Find direct ACL references
    if hasattr(config, 'acls'):
        for acl_name, acl_entries in config.acls.items():
            for entry in acl_entries:
                # Handle different formats
                if isinstance(entry, tuple) and len(entry) == 2:
                    # ASA parser format: (raw_line, line_number)
                    raw_line, line_num = entry
                    # Extract action from raw line
                    parts = raw_line.split()
                    action = 'unknown'
                    if 'permit' in parts:
                        action = 'permit'
                    elif 'deny' in parts:
                        action = 'deny'
                elif isinstance(entry, dict):
                    raw_line = entry.get('raw', '')
                    action = entry.get('action', 'unknown')
                    line_num = entry.get('line', 0)
                else:
                    raw_line = str(entry)
                    action = 'unknown'
                    line_num = 0

                # Check if object is referenced in the raw line
                if object_name in raw_line:
                    direct_acls.append({
                        'acl': acl_name,
                        'line': line_num,
                        'raw': raw_line,
                        'action': action
                    })

    # Find indirect ACL references (via group membership)
    if group_memberships and hasattr(config, 'acls'):
        for acl_name, acl_entries in config.acls.items():
            for entry in acl_entries:
                # Handle different formats
                if isinstance(entry, tuple) and len(entry) == 2:
                    # ASA parser format: (raw_line, line_number)
                    raw_line, line_num = entry
                    # Extract action from raw line
                    parts = raw_line.split()
                    action = 'unknown'
                    if 'permit' in parts:
                        action = 'permit'
                    elif 'deny' in parts:
                        action = 'deny'
                elif isinstance(entry, dict):
                    raw_line = entry.get('raw', '')
                    action = entry.get('action', 'unknown')
                    line_num = entry.get('line', 0)
                else:
                    raw_line = str(entry)
                    action = 'unknown'
                    line_num = 0

                # Check if any of the groups this object belongs to are referenced
                for group_name in group_memberships:
                    if group_name in raw_line:
                        indirect_acls.append({
                            'acl': acl_name,
                            'line': line_num,
                            'raw': raw_line,
                            'action': action,
                            'via_group': group_name
                        })
                        break

    return UsageResult(
        object_name=object_name,
        direct_acl_references=direct_acls,
        group_memberships=group_memberships,
        indirect_acl_references=indirect_acls,
        total_references=None  # Will be calculated in __post_init__
    )
