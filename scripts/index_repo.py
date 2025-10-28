#!/usr/bin/env python3
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
from datetime import datetime
from typing import Dict, Iterable, Optional, Tuple

from parsers.cisco import asa as asa_parser


MAX_DETECTION_BYTES = 64 * 1024
DEFAULT_SUPPORTED_VENDORS = ('asa', 'fortigate')


def _hash_path(path: str) -> str:
    return hashlib.sha1(os.path.realpath(path).encode('utf-8')).hexdigest()


def _detect_vendor(text: str, filename: str = '') -> Tuple[str, int, str]:
    sample = text[:MAX_DETECTION_BYTES].lower()
    reasons: Dict[str, Tuple[int, str]] = {}

    def note(vendor: str, score: int, reason: str) -> None:
        current = reasons.get(vendor)
        if current is None or score > current[0]:
            reasons[vendor] = (score, reason)

    lower_name = filename.lower()
    if lower_name.startswith('asa'):
        note('asa', 20, 'filename_prefix')
    if lower_name.endswith('.asa') or lower_name.endswith('.asa.conf'):
        note('asa', 30, 'extension')
    if lower_name.endswith('.fgd') or 'fortigate' in lower_name:
        note('fortigate', 20, 'filename_prefix')

    if 'asa version' in sample or 'adaptive security appliance software' in sample:
        note('asa', 90, 'asa_version_banner')
    if 'access-list ' in sample:
        note('asa', 60, 'access_list_token')
    if 'object network ' in sample or 'object-group network' in sample:
        note('asa', 40, 'object_network_token')

    if 'config-version=' in sample:
        note('fortigate', 80, 'config_version_kv')
    if 'config firewall policy' in sample or 'set uuid' in sample:
        note('fortigate', 60, 'firewall_policy_block')
    if 'config router static' in sample:
        note('fortigate', 30, 'router_static_block')

    if not reasons:
        return 'unknown', 0, 'no_match'
    vendor, (score, reason) = max(reasons.items(), key=lambda item: item[1][0])
    return vendor, score, reason


def _build_index(vendor: str, text: str) -> Dict:
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
                payload = {
                    'vendor': vendor,
                    'os': 'ASA' if vendor == 'asa' else 'FortiOS',
                    'version': 'unknown',
                    'built_at': st.st_mtime,
                    'src_mtime': st.st_mtime,
                    'src_size': st.st_size,
                    'index': index,
                }
                cache_key = f"{vendor}-{'ASA' if vendor=='asa' else 'FortiOS'}-{_hash_path(fpath)}"
                with open(os.path.join(cache_dir, cache_key + '.json'), 'w') as out:
                    json.dump(payload, out)
                manifest.append({
                    'path': os.path.realpath(fpath),
                    'vendor': vendor,
                    'score': score,
                    'reason': reason,
                    'size': st.st_size,
                    'mtime': st.st_mtime,
                })
                vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1
                count += 1
            except Exception:
                errors += 1
                continue
    manifest_payload = {
        'root': os.path.realpath(root),
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'count': count,
        'errors': errors,
        'vendor_counts': vendor_counts,
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
