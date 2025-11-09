"""Compare analysis: compare ACL impact between two targets.

This module provides vendor-agnostic comparison of two network objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class CompareResult:
    """Results from comparing two objects."""

    old_name: str
    """The original target object."""

    new_name: str
    """The replacement target object."""

    old_only_rules: List[Dict[str, Any]]
    """Rules that affect old but not new (will be removed)."""

    new_only_rules: List[Dict[str, Any]]
    """Rules that affect new but not old (will be added)."""

    common_rules: List[Dict[str, Any]]
    """Rules that affect both old and new."""

    def __post_init__(self):
        """Calculate summary stats."""
        self.total_old = len(self.old_only_rules) + len(self.common_rules)
        self.total_new = len(self.new_only_rules) + len(self.common_rules)
        self.total_common = len(self.common_rules)


def compare_objects(
    config,
    old_target: str,
    new_target: str,
    protocol: Optional[str] = None,
    dport: Optional[int] = None,
    include_any: bool = False,
) -> CompareResult:
    """Compare ACL impact between two network objects.

    Args:
        config: Parsed configuration object
        old_target: Original object name/IP
        new_target: Replacement object name/IP
        protocol: Optional protocol filter
        dport: Optional destination port filter
        include_any: If True, include rules with 'any'

    Returns:
        CompareResult showing rule differences

    Example:
        >>> config = ASAConfig(config_text)
        >>> result = compare_objects(config, "old-server", "new-server")
        >>> print(f"Removing {len(result.old_only_rules)} rules")
        >>> print(f"Adding {len(result.new_only_rules)} rules")
    """
    # Import here to avoid circular dependencies
    from parsers.cisco.asa.inspect import compare_old_new

    # Build service filter
    service_filter = None
    if protocol:
        service_filter = {"proto": protocol}
        if dport:
            service_filter["dports"] = {dport}

    # Get raw config text
    if hasattr(config, 'raw_text'):
        cfg_text = config.raw_text
    elif isinstance(config, str):
        cfg_text = config
    else:
        cfg_text = str(config)

    # Call existing compare logic
    result_dict = compare_old_new(
        cfg_text,
        old_target,
        new_target,
        service_filter=service_filter,
        include_any=include_any
    )

    # Convert to CompareResult
    return CompareResult(
        old_name=old_target,
        new_name=new_target,
        old_only_rules=result_dict["removed_from_old"],
        new_only_rules=result_dict["added_to_new"],
        common_rules=[
            r for r in result_dict["old_hits"]
            if r in result_dict["new_hits"]
        ]
    )
