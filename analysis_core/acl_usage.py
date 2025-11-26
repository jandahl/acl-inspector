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


def _fortigate_member_name(member: Any) -> str:
    """Return a FortiGate addrgrp member name."""
    if isinstance(member, dict):
        return member.get("object", member.get("name", ""))
    return str(member)


def _format_policy_ref(policy: Dict[str, Any]) -> str:
    """Generate a compact policy reference string for usage reporting."""
    pid = policy.get("name") or policy.get("id") or policy.get("uuid") or "policy"
    action = policy.get("action", "unknown")
    src = ", ".join(policy.get("srcaddr", []) or ["any"])
    dst = ", ".join(policy.get("dstaddr", []) or ["any"])
    svc = ", ".join(policy.get("service", []) or ["ALL"])
    return f"policy {pid}: {action} src:{src} dst:{dst} svc:{svc}"


def _find_fortigate_usage(config, object_name: str) -> UsageResult:
    """FortiGate-aware usage finder using parsed policy structures."""
    group_memberships: List[str] = []
    direct_acls: List[Dict[str, Any]] = []
    indirect_acls: List[Dict[str, Any]] = []

    def _collect_group_hits() -> List[str]:
        """Collect all addrgrp/vipgrp memberships including nested groups."""
        memberships: Set[str] = set()

        def _scan_addrgrp(name: str, visited: Set[str]) -> bool:
            """Return True if object_name found under this group."""
            if name in visited:
                return False
            visited.add(name)
            found = False
            members = getattr(config, "addrgrps", {}).get(name, [])
            for member in members:
                mname = _fortigate_member_name(member)
                if mname == object_name:
                    found = True
                if mname in getattr(config, "addrgrps", {}):
                    if _scan_addrgrp(mname, visited):
                        found = True
            if found:
                memberships.add(name)
            return found

        for grp in getattr(config, "addrgrps", {}):
            _scan_addrgrp(grp, set())

        for vipgrp_name, members in getattr(config, "vipgrps", {}).items():
            for member in members:
                if _fortigate_member_name(member) == object_name or member == object_name:
                    memberships.add(vipgrp_name)
                    break
        return list(memberships)

    group_memberships = _collect_group_hits()

    # Inspect policies for direct and indirect references
    for policy in getattr(config, "policies", []):
        srcaddrs = policy.get("srcaddr", []) or []
        dstaddrs = policy.get("dstaddr", []) or []
        services = policy.get("service", []) or []
        action = policy.get("action", "unknown")
        label = policy.get("name") or f"policy {policy.get('id', '')}".strip() or "policy"

        binding = {
            "policy_id": policy.get("id"),
            "name": policy.get("name"),
            "uuid": policy.get("uuid"),
            "srcaddr": srcaddrs,
            "dstaddr": dstaddrs,
            "service": services,
            "srcintf": policy.get("srcintf", []),
            "dstintf": policy.get("dstintf", []),
            "vdom": getattr(config, "vdom", None),
        }

        ref = {
            "acl": label,
            "line": 0,
            "raw": _format_policy_ref(policy),
            "action": action,
            "binding": binding,
        }

        direct_hit = (
            object_name in srcaddrs
            or object_name in dstaddrs
            or object_name in binding.get("vip_refs", [])
        )
        via_group = next(
            (grp for grp in group_memberships if grp in srcaddrs or grp in dstaddrs),
            None,
        )

        if direct_hit:
            direct_acls.append(ref)
        elif via_group:
            ref["via_group"] = via_group
            indirect_acls.append(ref)

    return UsageResult(
        object_name=object_name,
        direct_acl_references=direct_acls,
        group_memberships=group_memberships,
        indirect_acl_references=indirect_acls,
        total_references=None,
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

    # FortiGate path: policies/addrgrps instead of ASA ACLs
    if hasattr(config, "policies"):
        return _find_fortigate_usage(config, object_name)

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
