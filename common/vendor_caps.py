"""Shared vendor capability registry used by CLI, TUI, and Web surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class VendorCaps:
    """Describes the capabilities of a supported firewall vendor."""

    name: str
    label: str
    config_field: str
    requires_vdom: bool
    supports_inspect: bool
    supports_compare: bool
    supports_find: bool
    supports_packet: bool


_CAPS: Dict[str, VendorCaps] = {
    "asa": VendorCaps(
        name="asa",
        label="ASA",
        config_field="config",
        requires_vdom=False,
        supports_inspect=True,
        supports_compare=True,
        supports_find=True,
        supports_packet=True,
    ),
    "fortigate": VendorCaps(
        name="fortigate",
        label="FortiGate",
        config_field="config_ftg",
        requires_vdom=True,
        supports_inspect=True,
        supports_compare=True,
        supports_find=True,
        supports_packet=True,
    ),
}


def get_caps(vendor: str) -> Optional[VendorCaps]:
    """Return the capability descriptor for a vendor name."""
    if not vendor:
        return None
    return _CAPS.get(vendor.lower())


def all_caps() -> Dict[str, VendorCaps]:
    """Return a copy of every supported vendor capability entry."""
    return dict(_CAPS)


def supports_feature(vendor: str, feature: str) -> bool:
    """Return True if the vendor explicitly supports a named feature."""
    caps = get_caps(vendor)
    if not caps:
        return False
    mapping = {
        "inspect": caps.supports_inspect,
        "compare": caps.supports_compare,
        "find": caps.supports_find,
        "packet": caps.supports_packet,
    }
    return mapping.get(feature, False)
