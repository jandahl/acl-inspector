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
from typing import Dict, Tuple

from parsers.cisco import asa as asa_parser


def _hash_path(path: str) -> str:
    return hashlib.sha1(os.path.realpath(path).encode('utf-8')).hexdigest()


def _detect_vendor(text: str) -> str:
    # Very simple heuristic for now
    if 'access-list ' in text or 'ASA Version' in text or 'Adaptive Security Appliance' in text:
        return 'asa'
    if 'config-version=' in text or 'config-version' in text:
        return 'fortigate'
    return 'unknown'


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


def index_repo(root: str, cache_dir: str) -> Tuple[int, int]:
    os.makedirs(cache_dir, exist_ok=True)
    count = 0
    errors = 0
    manifest = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            except Exception:
                errors += 1
                continue
            vendor = _detect_vendor(text)
            if vendor not in ('asa', 'fortigate'):
                continue
            try:
                st = os.stat(fpath)
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
                manifest.append({'path': os.path.realpath(fpath), 'vendor': vendor, 'size': st.st_size, 'mtime': st.st_mtime})
                count += 1
            except Exception:
                errors += 1
                continue
    # Write a small manifest
    try:
        with open(os.path.join(cache_dir, 'manifest.json'), 'w') as mf:
            json.dump({'root': os.path.realpath(root), 'count': count, 'errors': errors, 'files': manifest}, mf)
    except Exception:
        pass
    return count, errors


def main() -> None:
    ap = argparse.ArgumentParser(description='Index a repository of firewall configs for predictive search cache')
    ap.add_argument('--root', required=True, help='Root directory to scan')
    ap.add_argument('--cache-dir', required=True, help='Cache directory to write indices to')
    args = ap.parse_args()
    c, e = index_repo(args.root, args.cache_dir)
    print(f"Indexed {c} files (errors={e}) into {args.cache_dir}")


if __name__ == '__main__':
    sys.exit(main())

