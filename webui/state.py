"""Application state container for the modular web UI."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import settings as settings_mod
from .indexer import IndexEntry, IndexManager
from .themes import load_themes


class DiskCache:
    """Simple JSON-on-disk cache wrapper."""

    def __init__(self, root: Optional[str]):
        self.root = Path(root) if root else None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.root is not None

    def ensure_ready(self) -> None:
        if not self.root:
            return
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)

    def read(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.root:
            return None
        path = self.root / f"{key}.json"
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return None

    def write(self, key: str, data: Dict[str, Any]) -> None:
        if not self.root:
            return
        self.ensure_ready()
        temp_path = self.root / f".{key}.tmp"
        final_path = self.root / f"{key}.json"
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle)
            temp_path.replace(final_path)
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def list_files(self) -> List[str]:
        if not self.root:
            return []
        try:
            return sorted(
                f
                for f in os.listdir(self.root)
                if f.endswith(".json") and os.path.isfile(self.root / f)
            )
        except Exception:
            return []

    def read_manifest(self, manifest_name: str) -> Optional[Dict[str, Any]]:
        if not self.root:
            return None
        path = self.root / manifest_name
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return None

    def clear(self, keep: Optional[List[str]] = None) -> int:
        if not self.root:
            return 0
        keep_set = {name for name in (keep or [])}
        removed = 0
        try:
            for entry in self.root.iterdir():
                if not entry.is_file():
                    continue
                if entry.name in keep_set:
                    continue
                try:
                    entry.unlink()
                    removed += 1
                except Exception:
                    continue
        except Exception:
            return removed
        return removed

    @property
    def path(self) -> str:
        return str(self.root) if self.root else ""


@dataclass
class HistoryEntry:
    tab: str
    query: str
    timestamp: float = field(default_factory=time.time)


class HistoryTracker:
    """Track recent user actions for the history sidebar."""

    def __init__(self, enabled: bool, limit: int = 50):
        self.enabled = enabled
        self.limit = limit
        self._lock = threading.Lock()
        self._entries: List[HistoryEntry] = []
        self.visibility: Dict[str, bool] = {}

    def record(self, tab: str, query: str) -> None:
        if not self.enabled:
            return
        entry = HistoryEntry(tab=tab, query=query)
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self.limit:
                self._entries = self._entries[-self.limit :]

    def set_visibility(self, tab: str, visible: bool) -> None:
        with self._lock:
            self.visibility[tab] = visible

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "entries": [
                    {"tab": entry.tab, "query": entry.query, "timestamp": entry.timestamp}
                    for entry in reversed(self._entries)
                ],
                "visibility": dict(self.visibility),
            }

    def clear(self) -> int:
        with self._lock:
            removed = len(self._entries)
            self._entries.clear()
            self.visibility.clear()
            return removed


class SearchIndex:
    """In-memory search index cache."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache: Dict[str, IndexEntry] = {}

    def get(self, key: str) -> Optional[IndexEntry]:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: IndexEntry) -> None:
        with self._lock:
            self._cache[key] = value

    def status(self, limit: int = 20) -> Dict[str, Any]:
        with self._lock:
            keys = sorted(self._cache.keys())[:limit]
            return {"entries": len(self._cache), "keys": keys}

    def clear(self) -> int:
        with self._lock:
            removed = len(self._cache)
            self._cache.clear()
            return removed



@dataclass
class AppState:
    """Container for mutable server state shared across handlers."""

    settings: settings_mod.Settings
    disk_cache: DiskCache
    search_index: SearchIndex
    index_manager: IndexManager
    history: HistoryTracker
    themes: List[Dict[str, Any]]

    @classmethod
    def create(cls, settings: settings_mod.Settings) -> "AppState":
        disk_cache = DiskCache(settings.paths.cache_dir)
        if settings.features.disk_cache.enabled:
            disk_cache.ensure_ready()
        history = HistoryTracker(
            enabled=settings.features.history_tracking,
            limit=settings.features.predictive_search.limit,
        )
        search_index = SearchIndex()
        index_manager = IndexManager(
            disk_cache=disk_cache,
            search_cache=search_index,
            manifest_name=settings.features.disk_cache.manifest,
        )
        themes = load_themes(settings.paths.themes_dir)
        return cls(
            settings=settings,
            disk_cache=disk_cache,
            search_index=search_index,
            index_manager=index_manager,
            history=history,
            themes=themes,
        )

    def flush_caches(self, include_disk: bool = False) -> Dict[str, Any]:
        summary = {}
        summary["index"] = self.index_manager.flush(include_disk=include_disk)
        summary["history"] = {"cleared": self.history.clear()}
        return summary
