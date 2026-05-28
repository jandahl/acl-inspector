# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Helpers for path-check capability detection across vendors."""

from __future__ import annotations

from typing import Any

from common.vendor_caps import get_caps


def path_check_supported(config: Any) -> bool:
    """Return True if the given parsed config supports path-check.

    This is a lightweight capability gate used by all frontends to decide
    whether to surface the Path/Packet Check tab or command. Vendors that
    set ``supports_packet`` in ``common.vendor_caps`` will pass; unknown
    configs default to False to avoid presenting a broken UI affordance.
    """
    if config is None:
        return False

    # Raw text is allowed (caller knows vendor); don't block.
    if isinstance(config, str):
        return True

    # Prefer explicit vendor attribute
    vendor = getattr(config, "vendor", None)
    if vendor:
        caps = get_caps(vendor)
        return bool(caps and caps.supports_packet)

    # Heuristic: recognize known parser classes by module path
    module = getattr(config, "__module__", "") or ""
    if "parsers.cisco.asa" in module:
        caps = get_caps("asa")
        return bool(caps and caps.supports_packet)
    if "parsers.fortigate" in module:
        caps = get_caps("fortigate")
        return bool(caps and caps.supports_packet)

    return False
