#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""
Minimal repository indexer to prebuild predictive-search indices.

- Scans a root directory for config files
- Detects vendor (ASA best-effort for now)
- Builds indices and writes cache files compatible with the web UI's cache loader

This is a thin layer around ASAConfig and the index-building logic used by the web UI.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional, Tuple

from parsers.cisco import asa as asa_parser


MAX_DETECTION_BYTES = 64 * 1024
DEFAULT_SUPPORTED_VENDORS = ('asa', 'fortigate', 'ios', 'ios-xr', 'ios-xe')


def _hash_path(path: str) -> str:
    return hashlib.sha1(os.path.realpath(path).encode('utf-8')).hexdigest()


def _utc_now_iso_z() -> str:
    stamp = datetime.now(timezone.utc).isoformat()
    return stamp[:-6] + 'Z' if stamp.endswith("+00:00") else stamp


def _detect_vendor(text: str, filename: str = '') -> Tuple[str, int, str]:
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

    Detection logic:
        - Filename patterns (score 20-30): Extensions and prefixes
        - Version banners (score 80-95): Cisco version strings
        - Syntax patterns (score 40-70): Vendor-specific keywords
        - High confidence requires score >= 80

    Examples:
        >>> _detect_vendor("ASA Version 9.8", "firewall.asa")
        ('asa', 90, 'asa_version_banner')

        >>> _detect_vendor("version 15.2\\nios-xe", "router.cfg")
        ('ios-xe', 95, 'ios_xe_version_banner')
    """
    sample = text[:MAX_DETECTION_BYTES].lower()
    reasons: Dict[str, Tuple[int, str]] = {}

    def note(vendor: str, score: int, reason: str) -> None:
        """Record vendor detection with score, keeping highest score per vendor."""
        current = reasons.get(vendor)
        if current is None or score > current[0]:
            reasons[vendor] = (score, reason)

    # Filename-based detection (lower confidence)
    lower_name = filename.lower()

    # Cisco ASA
    if lower_name.startswith('asa'):
        note('asa', 20, 'filename_prefix')
    if lower_name.endswith('.asa') or lower_name.endswith('.asa.conf'):
        note('asa', 30, 'extension')

    # FortiGate
    if lower_name.endswith('.fgd') or 'fortigate' in lower_name:
        note('fortigate', 20, 'filename_prefix')

    # Cisco IOS variants
    if 'ios' in lower_name or lower_name.endswith('.ios'):
        note('ios', 20, 'filename_hint')
    if 'xr' in lower_name or lower_name.endswith('.xr'):
        note('ios-xr', 50, 'filename_hint')  # Higher score to override generic IOS patterns
    if 'xe' in lower_name or lower_name.endswith('.xe'):
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

    # Cisco IOS-XE patterns (check before generic IOS)
    if 'cisco ios xe software' in sample or 'ios-xe' in sample or 'iosxe' in sample:
        note('ios-xe', 95, 'ios_xe_version_banner')
    if 'platform:' in sample and ('ios xe' in sample or 'iosxe' in sample):
        note('ios-xe', 85, 'ios_xe_platform_identifier')

    # Cisco IOS-XR patterns (check before generic IOS)
    if 'cisco ios xr software' in sample or 'ios-xr' in sample:
        note('ios-xr', 95, 'ios_xr_version_banner')
    if 'rp/0/rp' in sample or 'disk0:' in sample:
        note('ios-xr', 70, 'ios_xr_filesystem_hint')
    if 'router bgp' in sample and 'address-family' in sample:
        note('ios-xr', 40, 'ios_xr_bgp_syntax')

    # Generic Cisco IOS patterns (lowest priority for IOS variants)
    if 'cisco ios software' in sample:
        note('ios', 85, 'ios_version_banner')
    if 'version 1' in sample[:1000]:  # IOS version command near top
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


def _vendor_to_os(vendor: str) -> str:
    """Map vendor identifier to OS name for display."""
    vendor = vendor.lower()
    if vendor == 'asa':
        return 'ASA'
    if vendor == 'fortigate':
        return 'FortiOS'
    if vendor == 'ios':
        return 'IOS'
    if vendor == 'ios-xe':
        return 'IOS-XE'
    if vendor == 'ios-xr':
        return 'IOS-XR'
    return 'Unknown'


def _confidence_level(score: int) -> str:
    """Determine confidence level from detection score.

    Args:
        score: Detection score from _detect_vendor

    Returns:
        Confidence level: 'high' (>=80), 'medium' (>=50), or 'low' (<50)
    """
    if score >= 80:
        return 'high'
    if score >= 50:
        return 'medium'
    return 'low'


def _build_index(vendor: str, text: str) -> Dict:
    """Build search index for a vendor configuration.

    Args:
        vendor: Vendor identifier (asa, fortigate, ios, ios-xe, ios-xr)
        text: Configuration file text

    Returns:
        Dictionary with objects, groups, and literals for search

    Note:
        Currently only ASA configs are fully indexed. Other vendors
        return empty indices but are preserved in the manifest for
        future implementation.
    """
    vendor = vendor.lower()
    if vendor == 'asa':
        cfg = asa_parser.ASAConfig(text)
        objects = sorted(cfg.network_objects.keys())
        groups = sorted(cfg.network_object_groups.keys())
        literals = set()
        for nset in cfg.network_objects.values():
            for n in nset:
                literals.add(str(n))
        return {'objects': objects, 'groups': groups, 'literals': sorted(literals)}
    return {'objects': [], 'groups': [], 'literals': []}


def _should_skip(name: str) -> bool:
    lowered = name.lower()
    if lowered.startswith('.') or lowered.startswith('_'):
        return True
    if lowered in {'thumbs.db', 'desktop.ini'}:
        return True
    return False


def index_repo(root: str, cache_dir: str, *, vendors: Optional[Iterable[str]] = None, max_size: Optional[int] = None) -> Tuple[int, int, Dict[str, int]]:
    os.makedirs(cache_dir, exist_ok=True)
    count = 0
    errors = 0
    vendor_counts: Dict[str, int] = {}
    manifest = []
    supported = tuple(v.strip().lower() for v in vendors) if vendors else DEFAULT_SUPPORTED_VENDORS
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _should_skip(d)]
        for fname in filenames:
            if _should_skip(fname):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                st = os.stat(fpath)
                if max_size is not None and st.st_size > max_size:
                    continue
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            except Exception:
                errors += 1
                continue
            vendor, score, reason = _detect_vendor(text, filename=fname)
            if vendor not in supported:
                continue
            try:
                index = _build_index(vendor, text)
                os_name = _vendor_to_os(vendor)
                confidence = _confidence_level(score)
                payload = {
                    'vendor': vendor,
                    'os': os_name,
                    'version': 'unknown',
                    'built_at': st.st_mtime,
                    'src_mtime': st.st_mtime,
                    'src_size': st.st_size,
                    'index': index,
                }
                cache_key = f"{vendor}-{os_name}-{_hash_path(fpath)}"
                with open(os.path.join(cache_dir, cache_key + '.json'), 'w') as out:
                    json.dump(payload, out)
                manifest.append({
                    'path': os.path.realpath(fpath),
                    'vendor': vendor,
                    'os': os_name,
                    'score': score,
                    'reason': reason,
                    'confidence': confidence,
                    'size': st.st_size,
                    'mtime': st.st_mtime,
                })
                vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1
                count += 1
            except Exception:
                errors += 1
                continue

    # Calculate confidence level distribution
    confidence_counts: Dict[str, int] = {}
    for entry in manifest:
        conf = entry.get('confidence', 'unknown')
        confidence_counts[conf] = confidence_counts.get(conf, 0) + 1

    manifest_payload = {
        'root': os.path.realpath(root),
        'generated_at': _utc_now_iso_z(),
        'count': count,
        'errors': errors,
        'vendor_counts': vendor_counts,
        'confidence_counts': confidence_counts,
        'files': manifest,
        'max_size': max_size,
        'vendors': list(supported),
    }
    try:
        with open(os.path.join(cache_dir, 'manifest.json'), 'w') as mf:
            json.dump(manifest_payload, mf, indent=2)
    except Exception:
        pass
    return count, errors, vendor_counts


def main() -> None:
    ap = argparse.ArgumentParser(description='Index a repository of firewall configs for predictive search cache')
    ap.add_argument('--root', required=True, help='Root directory to scan')
    ap.add_argument('--cache-dir', required=True, help='Cache directory to write indices to')
    ap.add_argument('--vendors', default=','.join(DEFAULT_SUPPORTED_VENDORS), help='Comma-separated list of vendors to index (default: asa,fortigate)')
    ap.add_argument('--max-size', type=int, default=None, help='Skip files larger than this size in bytes (default: unlimited)')
    args = ap.parse_args()
    vendor_list = [v.strip() for v in args.vendors.split(',') if v.strip()]
    c, e, counts = index_repo(args.root, args.cache_dir, vendors=vendor_list, max_size=args.max_size)
    print(f"Indexed {c} files (errors={e}) into {args.cache_dir}; vendor counts={counts}")


if __name__ == '__main__':
    sys.exit(main())
