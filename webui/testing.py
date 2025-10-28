"""Testing helpers for web UI components."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from html import escape
from parsers.cisco import asa as asa_parser

from .indexer import IndexManager


def extract_meta_for_tests(vendor: str, text: str) -> Dict[str, str]:
    vendor = vendor.lower()
    if vendor == "asa":
        for pattern in [
            r"ASA\s+Version\s+([^\s]+)",
            r"Adaptive Security Appliance Software\s+Version\s+([^\s]+)",
        ]:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return {"vendor": "asa", "os": "ASA", "version": match.group(1)}
        return {"vendor": "asa", "os": "ASA", "version": "unknown"}
    if vendor == "fortigate":
        return {"vendor": "fortigate", "os": "FortiOS", "version": "unknown"}
    return {"vendor": vendor, "os": vendor.upper(), "version": "unknown"}


def build_index_for_tests(vendor: str, text: str) -> Dict[str, List[str]]:
    vendor = vendor.lower()
    if vendor == "asa":
        cfg = asa_parser.ASAConfig(text)
        objects = sorted(cfg.network_objects.keys())
        groups = sorted(cfg.network_object_groups.keys())
        literals = set()
        for members in cfg.network_objects.values():
            for value in members:
                literals.add(str(value))
        return {"objects": objects, "groups": groups, "literals": sorted(literals)}
    return {"objects": [], "groups": [], "literals": []}


def match_candidates_for_tests(index: Dict[str, Any], query: str, limit: int = 50, mode: str = "fuzzy") -> List[Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    mode = mode.lower()
    if mode == "prefix":
        return IndexManager._match_prefix(index, q, limit)
    if mode == "substring":
        return IndexManager._match_substring(index, q, limit)
    return IndexManager._match_fuzzy(index, q, limit)


def highlight_asa_for_tests(line: str) -> str:
    s = escape(line)
    s = re.sub(r"\b(permit|deny)\b", r"<span class='act'>\1</span>", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(tcp|udp|icmp|ip)\b", r"<span class='proto'>\1</span>", s, flags=re.IGNORECASE)
    s = re.sub(
        r"\b(access-list|extended|object-group|object|host|subnet|eq|lt|gt|neq|range|any|any4|any6)\b",
        r"<span class='kw'>\1</span>",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\b(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?\b",
        lambda m: f"<span class='addr'>{m.group(1)}{('/'+m.group(2)) if m.group(2) else ''}</span>",
        s,
    )
    s = re.sub(r"\b(\d{2,5})\b", r"<span class='num'>\1</span>", s)
    return s


def index_status_for_tests(cache_dir: Optional[str], index_cache: Dict[str, Any]) -> Dict[str, Any]:
    mem_keys = sorted(list(index_cache.keys()))[:20]
    mem = {"entries": len(index_cache), "keys": mem_keys}
    disk = {"enabled": bool(cache_dir), "path": cache_dir or "", "files": 0, "manifest": None}
    if cache_dir:
        try:
            files = [
                name
                for name in os.listdir(cache_dir)
                if os.path.isfile(os.path.join(cache_dir, name)) and name.endswith(".json")
            ]
            disk["files"] = len(files)
        except Exception:
            disk["files"] = 0
        try:
            mf_path = os.path.join(cache_dir, "manifest.json")
            if os.path.isfile(mf_path):
                with open(mf_path, "r", encoding="utf-8") as handle:
                    disk["manifest"] = json.load(handle)
        except Exception:
            disk["manifest"] = None
    return {"in_memory": mem, "disk": disk}
