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
from parsers.detector import (
    DEFAULT_SUPPORTED_VENDORS,
    confidence_level,
    detect_vendor,
    vendor_to_os,
)


def _hash_path(path: str) -> str:
    return hashlib.sha1(os.path.realpath(path).encode('utf-8')).hexdigest()


def _utc_now_iso_z() -> str:
    stamp = datetime.now(timezone.utc).isoformat()
    return stamp[:-6] + 'Z' if stamp.endswith("+00:00") else stamp


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
            vendor, score, reason = detect_vendor(text, filename=fname)
            if vendor not in supported:
                continue
            try:
                index = _build_index(vendor, text)
                os_name = vendor_to_os(vendor)
                confidence = confidence_level(score)
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
