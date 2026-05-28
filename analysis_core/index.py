# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Search index management."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils.config import clean_config_text, load_config_text

from .adapters import build_asa_index, build_fortigate_index

logger = logging.getLogger(__name__)


@dataclass
class IndexEntry:
    key: str
    vendor: str
    os_tag: str
    version: str
    built_at: float
    src_mtime: float
    src_size: int
    index: Dict[str, Any]

    def to_payload(self) -> Dict[str, Any]:
        return {
            "vendor": self.vendor,
            "os": self.os_tag,
            "version": self.version,
            "built_at": self.built_at,
            "src_mtime": self.src_mtime,
            "src_size": self.src_size,
            "index": self.index,
        }

    @classmethod
    def from_payload(cls, key: str, payload: Dict[str, Any]) -> "IndexEntry":
        return cls(
            key=key,
            vendor=str(payload.get("vendor", "")),
            os_tag=str(payload.get("os", "")),
            version=str(payload.get("version", "")),
            built_at=float(payload.get("built_at", 0.0)),
            src_mtime=float(payload.get("src_mtime", 0.0)),
            src_size=int(payload.get("src_size", 0)),
            index=dict(payload.get("index", {})),
        )


class IndexManager:
    """Builds and caches predictive-search indexes."""

    def __init__(self, disk_cache, search_cache, manifest_name: str = "manifest.json"):
        self.disk_cache = disk_cache
        self.search_cache = search_cache
        self.manifest_name = manifest_name
        self._lock = threading.Lock()

    # ------------------------- index retrieval -------------------------
    def get_index(self, vendor: str, os_tag: str, version: str, path: str) -> IndexEntry:
        key = self._cache_key(vendor, path)
        stat = os.stat(path)

        def _load_cached() -> Optional[IndexEntry]:
            entry = self.search_cache.get(key)
            if entry and self._is_fresh(entry, stat.st_mtime, stat.st_size):
                return entry
            if self.disk_cache.enabled:
                payload = self.disk_cache.read(key)
                if payload and self._matches_stat(payload, stat.st_mtime, stat.st_size):
                    entry = IndexEntry.from_payload(key, payload)
                    self.search_cache.set(key, entry)
                    return entry
            return None

        with self._lock:
            cached = _load_cached()
        if cached:
            return cached

        logger.info("Building index for %s (%s)", vendor, path)
        start = time.time()
        try:
            text = clean_config_text(load_config_text(path))
            index = self._build_index(vendor, text)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed building index for %s (%s)", vendor, path)
            raise
        duration = time.time() - start
        logger.info(
            "Finished index for %s (%s) in %.2fs (objects=%d groups=%d)",
            vendor,
            path,
            duration,
            len(index.get("objects") or []),
            len(index.get("groups") or []),
        )
        fresh_entry = IndexEntry(
            key=key,
            vendor=vendor,
            os_tag=os_tag,
            version=version,
            built_at=time.time(),
            src_mtime=stat.st_mtime,
            src_size=stat.st_size,
            index=index,
        )

        with self._lock:
            cached = _load_cached()
            if cached:
                return cached
            self.search_cache.set(key, fresh_entry)
            if self.disk_cache.enabled:
                self.disk_cache.write(key, fresh_entry.to_payload())
        return fresh_entry

    def status(self) -> Dict[str, Any]:
        with self._lock:
            in_memory = self.search_cache.status()
            disk = {
                "enabled": self.disk_cache.enabled,
                "path": self.disk_cache.path,
                "files": len(self.disk_cache.list_files()) if self.disk_cache.enabled else 0,
                "manifest": None,
            }
            if self.disk_cache.enabled and self.manifest_name:
                disk["manifest"] = self.disk_cache.read_manifest(self.manifest_name)
            return {"in_memory": in_memory, "disk": disk}

    def flush(self, include_disk: bool = False) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}
        with self._lock:
            summary["in_memory"] = {"cleared": self.search_cache.clear()}
            if include_disk and self.disk_cache.enabled:
                keep = [self.manifest_name] if self.manifest_name else []
                summary["disk"] = {"cleared": self.disk_cache.clear(keep=keep)}
            else:
                summary["disk"] = {"cleared": 0}
        return summary

    # ------------------------- suggestions -------------------------
    def suggest(self, index: Dict[str, Any], query: str, mode: str, limit: int) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        mode = (mode or "fuzzy").lower()
        if mode == "prefix":
            matches = self._match_prefix(index, q, limit)
        elif mode == "substring":
            matches = self._match_substring(index, q, limit)
        else:
            matches = self._match_fuzzy(index, q, limit)
        return self._enrich_matches(index, matches, limit)

    # ------------------------- internals -------------------------
    @staticmethod
    def _cache_key(vendor: str, path: str) -> str:
        digest = hashlib.sha1(os.path.realpath(path).encode("utf-8")).hexdigest()
        return f"{vendor}-{digest}"

    @staticmethod
    def _matches_stat(payload: Dict[str, Any], mtime: float, size: int) -> bool:
        return (
            math.isclose(float(payload.get("src_mtime", 0.0)), mtime)
            and int(payload.get("src_size", -1)) == size
        )

    @staticmethod
    def _is_fresh(entry: IndexEntry, mtime: float, size: int) -> bool:
        return math.isclose(entry.src_mtime, mtime) and entry.src_size == size

    def _build_index(self, vendor: str, text: str) -> Dict[str, Any]:
        vendor = (vendor or "").lower()
        if vendor == "asa":
            return build_asa_index(text)
        if vendor == "fortigate":
            return build_fortigate_index(text)
        return {"objects": [], "groups": [], "literals": []}

    # ------------------------- matching helpers -------------------------
    @staticmethod
    def _match_prefix(index: Dict[str, Any], query: str, limit: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        ql = query.lower()

        def add_many(values: Sequence[str], typ: str) -> bool:
            for value in values:
                if value.lower().startswith(ql):
                    label = f"{value} (group)" if typ == "group" else value
                    out.append({"value": value, "label": label, "type": typ})
                    if len(out) >= limit:
                        return True
            return False

        if add_many(index.get("objects", []), "object"):
            return out
        if add_many(index.get("groups", []), "group"):
            return out
        add_many(index.get("literals", []), "literal")
        return out[:limit]

    @staticmethod
    def _match_substring(index: Dict[str, Any], query: str, limit: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        ql = query.lower()

        def add_many(values: Sequence[str], typ: str) -> bool:
            for value in values:
                if ql in value.lower():
                    label = f"{value} (group)" if typ == "group" else value
                    out.append({"value": value, "label": label, "type": typ})
                    if len(out) >= limit:
                        return True
            return False

        if add_many(index.get("objects", []), "object"):
            return out
        if add_many(index.get("groups", []), "group"):
            return out
        add_many(index.get("literals", []), "literal")
        return out[:limit]

    @classmethod
    def _match_fuzzy(cls, index: Dict[str, Any], query: str, limit: int) -> List[Dict[str, Any]]:
        candidates: List[Tuple[Tuple[int, int, int], Dict[str, Any]]] = []

        def consider(values: Sequence[str], typ: str) -> None:
            for value in values:
                score = cls._fuzzy_score(value, query)
                if score is None:
                    continue
                label = f"{value} (group)" if typ == "group" else value
                candidates.append((score, {"value": value, "label": label, "type": typ}))

        consider(index.get("objects", []), "object")
        consider(index.get("groups", []), "group")
        consider(index.get("literals", []), "literal")
        candidates.sort(
            key=lambda item: (
                item[0][0],
                item[0][1],
                item[0][2],
                item[1]["type"] != "object",
                item[1]["type"] != "group",
                item[1]["value"],
            )
        )
        return [candidate[1] for candidate in candidates[:limit]]

    def _enrich_matches(
        self, index: Dict[str, Any], matches: List[Dict[str, Any]], limit: int
    ) -> List[Dict[str, Any]]:
        popularity_map: Dict[str, Dict[str, float]] = {}
        if isinstance(index, dict):
            raw_popularity = index.get("popularity")
            if isinstance(raw_popularity, dict):
                popularity_map = {
                    key: dict(value) if isinstance(value, dict) else {}
                    for key, value in raw_popularity.items()
                }
        type_priority = {"object": 0, "group": 1, "literal": 2}
        default_popularity_weight = 0.6
        enriched: List[Dict[str, Any]] = []
        for position, item in enumerate(matches):
            entry = dict(item)
            kind = (entry.get("type") or "object").lower()
            value = entry.get("value")
            popularity = 0.0
            if popularity_map and isinstance(value, str):
                popularity = float(popularity_map.get(kind, {}).get(value, 0.0) or 0.0)
            score = position - (popularity * default_popularity_weight)
            entry["rank"] = position
            entry["score"] = score
            entry.setdefault("label", str(value) if value is not None else "")
            entry["signals"] = {
                "popularity": popularity,
                "typePriority": type_priority.get(kind, 99),
            }
            enriched.append(entry)
        enriched.sort(
            key=lambda item: (
                item.get("score", 0.0),
                item.get("signals", {}).get("typePriority", 99),
                str(item.get("value") or ""),
            )
        )
        return enriched[:limit]

    @staticmethod
    def _fuzzy_score(text: str, pattern: str) -> Optional[Tuple[int, int, int]]:
        t = text.lower()
        p = pattern.lower()
        ti = 0
        pi = 0
        start = -1
        gaps = 0
        last_match = -1
        while ti < len(t) and pi < len(p):
            if t[ti] == p[pi]:
                if start == -1:
                    start = ti
                if last_match != -1 and ti - last_match > 1:
                    gaps += ti - last_match - 1
                last_match = ti
                pi += 1
            ti += 1
        if pi != len(p):
            return None
        length = (last_match - start + 1) if start != -1 else len(t)
        return (gaps, start if start != -1 else 0, length)
