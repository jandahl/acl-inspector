# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Firewall vendor detection logic."""

import re
from typing import Dict, Tuple

MAX_DETECTION_BYTES = 64 * 1024
DEFAULT_SUPPORTED_VENDORS = ('asa', 'fortigate', 'ios', 'ios-xr', 'ios-xe')

__all__ = [
    "MAX_DETECTION_BYTES",
    "DEFAULT_SUPPORTED_VENDORS",
    "detect_vendor",
    "vendor_to_os",
    "confidence_level",
]


def detect_vendor(text: str, filename: str = '') -> Tuple[str, int, str]:
    """Detect firewall vendor from config text and filename.

    Uses heuristic scoring based on filename patterns and content keywords to
    identify the vendor. Higher scores indicate stronger confidence. Supports
    Cisco ASA, FortiGate, IOS, IOS-XR, and IOS-XE.

    Args:
        text: Configuration file content (first 64KB sampled)
        filename: Original filename for extension/prefix hints

    Returns:
        Tuple of (vendor_name, confidence_score, detection_reason)
        vendor_name is 'unknown' if no match found
    """
    if not text:
        return 'unknown', 0, 'no_match'

    sample = text[:MAX_DETECTION_BYTES].lower()
    reasons: Dict[str, Tuple[int, str]] = {}

    def note(vendor: str, score: int, reason: str) -> None:
        """Record vendor detection with score, keeping highest score per vendor."""
        current = reasons.get(vendor)
        if current is None or score > current[0]:
            reasons[vendor] = (score, reason)

    # Filename-based detection (lower confidence)
    lower_name = (filename or '').lower()

    # Cisco ASA
    if lower_name.startswith('asa'):
        note('asa', 20, 'filename_prefix')
    if lower_name.endswith('.asa') or lower_name.endswith('.asa.conf'):
        note('asa', 30, 'extension')

    # FortiGate
    if lower_name.endswith('.fgd') or 'fortigate' in lower_name:
        note('fortigate', 20, 'filename_hint')

    # Cisco IOS variants
    has_ios = any(p in lower_name for p in ('-ios', '_ios', 'ios-', 'ios_')) or lower_name.startswith('ios') or lower_name.endswith('.ios')
    has_xr = any(p in lower_name for p in ('-xr', '_xr', 'xr-', 'xr_')) or lower_name.startswith('xr') or lower_name.endswith('.xr')
    has_xe = any(p in lower_name for p in ('-xe', '_xe', 'xe-', 'xe_')) or lower_name.startswith('xe') or lower_name.endswith('.xe')

    if has_ios:
        note('ios', 20, 'filename_hint')
    if has_xr:
        note('ios-xr', 50, 'filename_hint')  # Higher score to override generic IOS patterns
    if has_xe:
        note('ios-xe', 50, 'filename_hint')  # Higher score to override generic IOS patterns

    # Content-based detection (higher confidence)

    # Cisco ASA patterns
    if 'asa version' in sample or 'adaptive security appliance software' in sample:
        note('asa', 90, 'asa_version_banner')
    if 'access-list ' in sample and 'extended permit' in sample:
        note('asa', 65, 'asa_acl_syntax')
    if 'object network ' in sample or 'object-group network' in sample:
        note('asa', 40, 'object_network_token')
    if 'nameif ' in sample and 'security-level' in sample:
        note('asa', 50, 'asa_interface_tokens')

    # FortiGate patterns
    if 'config-version=' in sample:
        note('fortigate', 80, 'config_version_kv')
    if 'config firewall policy' in sample or 'set uuid' in sample:
        note('fortigate', 60, 'firewall_policy_block')
    if 'config router static' in sample:
        note('fortigate', 30, 'router_static_block')
    if 'config system global' in sample:
        note('fortigate', 70, 'system_global_block')

    # Cisco IOS-XE patterns
    if 'cisco ios xe software' in sample or 'ios-xe' in sample or 'iosxe' in sample:
        note('ios-xe', 95, 'ios_xe_version_banner')
    if 'platform:' in sample and ('ios xe' in sample or 'iosxe' in sample):
        note('ios-xe', 85, 'ios_xe_platform_identifier')

    # Cisco IOS-XR patterns
    if 'cisco ios xr software' in sample or 'ios-xr' in sample:
        note('ios-xr', 95, 'ios_xr_version_banner')
    if 'rp/0/rp' in sample:
        note('ios-xr', 70, 'ios_xr_filesystem_hint')
    # Note: 'disk0:' check intentionally omitted as it causes false positives with generic IOS/ASA
    if 'router bgp' in sample and 'address-family' in sample:
        note('ios-xr', 40, 'ios_xr_bgp_syntax')
    if 'route-policy' in sample:
        note('ios-xr', 65, 'ios_xr_policy_syntax')

    # Generic Cisco IOS patterns
    if 'cisco ios software' in sample:
        note('ios', 85, 'ios_version_banner')
    if re.search(r'^version 1[1-9]\.', sample[:1000], re.MULTILINE):
        note('ios', 60, 'ios_version_command')
    if 'interface gigabitethernet' in sample or 'interface fastethernet' in sample:
        note('ios', 45, 'ios_interface_naming')
    if 'ip access-list' in sample:
        note('ios', 50, 'ios_acl_syntax')
    if 'boot system' in sample or 'boot-start-marker' in sample:
        note('ios', 40, 'ios_boot_config')

    if not reasons:
        return 'unknown', 0, 'no_match'

    vendor, (score, reason) = max(reasons.items(), key=lambda item: item[1][0])
    return vendor, score, reason


def vendor_to_os(vendor: str) -> str:
    """Map vendor identifier to OS name for display."""
    if not vendor:
        return 'Unknown'
    mapping = {
        'asa': 'ASA',
        'fortigate': 'FortiOS',
        'ios': 'IOS',
        'ios-xe': 'IOS-XE',
        'ios-xr': 'IOS-XR',
    }
    return mapping.get(vendor.lower(), 'Unknown')


def confidence_level(score: int) -> str:
    """Determine confidence level from detection score."""
    if score >= 80:
        return 'high'
    if score >= 50:
        return 'medium'
    return 'low'
