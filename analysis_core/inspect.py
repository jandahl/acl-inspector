"""Inspect analysis: find ACL rules affecting a target object.

This module provides vendor-agnostic object inspection across ACLs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Set
import ipaddress


@dataclass
class InspectResult:
    """Results from inspecting an object in ACLs."""

    object_name: str
    """The target object/network that was inspected."""

    resolved_addresses: List[str]
    """List of IP addresses/networks the object resolves to."""

    matching_rules: List[Dict[str, Any]]
    """Flattened ACL entries that affect this object."""

    duplicates: List[str]
    """Other object names that resolve to the same IP addresses (aliases)."""

    total_rules: int
    """Total number of matching ACL rules."""

    def __post_init__(self):
        """Calculate derived fields."""
        if self.total_rules is None:
            self.total_rules = len(self.matching_rules)


def inspect_object(
    config,
    target: str,
    protocol: Optional[str] = None,
    dport: Optional[int] = None,
    include_any: bool = False,
) -> InspectResult:
    """Inspect a network object to find ACL rules affecting it.

    This function works with any parsed config object that has the required methods
    (ASAConfig, FTGConfig, etc.) using duck typing.

    Args:
        config: Parsed configuration object (must have resolve_network, flatten_acl methods)
        target: Object name, IP address, or CIDR to inspect
        protocol: Optional protocol filter (tcp, udp, icmp, etc.)
        dport: Optional destination port filter
        include_any: If True, include rules with 'any' in src/dst

    Returns:
        InspectResult with matching rules and metadata

    Example:
        >>> config = ASAConfig(config_text)
        >>> result = inspect_object(config, "webserver-dmz")
        >>> print(f"Found {result.total_rules} rules affecting {result.object_name}")
        >>> for rule in result.matching_rules:
        ...     print(f"  {rule['acl']}: {rule['raw']}")
    """
    # Import here to avoid circular dependencies
    from parsers.cisco.asa.inspect import inspect_host

    # Build service filter if protocol/port specified
    service_filter = None
    if protocol:
        service_filter = {"proto": protocol}
        if dport:
            service_filter["dports"] = {dport}

    # Get raw config text - handle both string and ASAConfig object
    if hasattr(config, 'raw_text'):
        cfg_text = config.raw_text
    elif isinstance(config, str):
        cfg_text = config
        # Need to parse it
        from parsers.cisco.asa.parser import ASAConfig
        config = ASAConfig(cfg_text)
    else:
        # Assume it's already a parsed config, try to get raw text
        cfg_text = str(config)  # Fallback

    # Call existing inspect_host logic
    result_dict = inspect_host(
        cfg_text,
        target,
        service_filter=service_filter,
        include_any=include_any
    )

    # Convert to InspectResult
    return InspectResult(
        object_name=target,
        resolved_addresses=[str(net) for net in result_dict["target_nets"]],
        matching_rules=result_dict["hits"],
        duplicates=result_dict.get("aliases", []),
        total_rules=len(result_dict["hits"])
    )
