"""Thin compatibility layer so existing imports still work."""

from common.vendor_caps import VendorCaps, all_caps, get_caps, supports_feature, _CAPS as _ROOT_CAPS  # noqa: F401

__all__ = ["VendorCaps", "all_caps", "get_caps", "supports_feature", "_CAPS"]

_CAPS = _ROOT_CAPS
