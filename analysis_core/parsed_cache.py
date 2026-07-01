# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""In-memory cache of parsed firewall configs (and their derived IR).

Parsing a config is the single most expensive operation in the web layer, and
today it happens redundantly: several handlers build an ``ASAConfig``/``FTGConfig``
per request, and some consumers re-parse the same text a second time internally.

Parsed engine objects are NOT JSON round-trippable (they hold ``ipaddress``
objects and compiled regex caches), so unlike the predictive-search index there
is no disk tier here — this is a bounded in-memory cache only. Freshness mirrors
:class:`analysis_core.index.IndexManager`: path-keyed entries validate on
(mtime, size); text-keyed entries use the content hash as the freshness guarantee.
"""

from __future__ import annotations

import hashlib
import math
import os
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

from utils.config import clean_config_text, load_config_text

__all__ = ["ParsedConfigCache"]

# Default bound. Parsed ASA configs can be large; cap entries so a long-lived
# server scanning many configs cannot grow the cache without limit.
DEFAULT_MAX_ENTRIES = 32


class ParsedConfigCache:
    """Bounded, thread-safe LRU cache of parsed configs and derived IR Devices.

    Two key spaces share one eviction order:
      * path keys  ``f"{vendor}-{sha1(realpath)}"`` — validated against the
        source file's (mtime, size) on every lookup.
      * text keys  ``f"{vendor}-text-{sha1(text)}"`` — the hash is the identity,
        so a hit is always fresh.
    """

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES):
        self._lock = threading.Lock()
        self._max = max(1, int(max_entries))
        # key -> (cfg, mtime, size); mtime/size are None for text-keyed entries.
        self._cfgs: "OrderedDict[str, Tuple[Any, Optional[float], Optional[int]]]" = OrderedDict()
        # key -> (device, mtime, size); built lazily on get_device().
        self._devices: "OrderedDict[str, Tuple[Any, Optional[float], Optional[int]]]" = OrderedDict()

    # ------------------------- keys / freshness -------------------------
    @staticmethod
    def _path_key(vendor: str, path: str, vdom: str = "") -> str:
        digest = hashlib.sha1(os.path.realpath(path).encode("utf-8")).hexdigest()
        return f"{vendor}-{digest}-{vdom}"

    @staticmethod
    def _text_key(vendor: str, text: str, vdom: str = "") -> str:
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
        return f"{vendor}-text-{digest}-{vdom}"

    @staticmethod
    def _is_fresh(stored_mtime: Optional[float], stored_size: Optional[int],
                  mtime: float, size: int) -> bool:
        if stored_mtime is None or stored_size is None:
            return True  # text-keyed entry: hash identity already guarantees it
        return math.isclose(stored_mtime, mtime) and stored_size == size

    def _store(self, store: "OrderedDict[str, Tuple[Any, Optional[float], Optional[int]]]",
               key: str, value: Tuple[Any, Optional[float], Optional[int]]) -> None:
        store[key] = value
        store.move_to_end(key)
        while len(store) > self._max:
            store.popitem(last=False)

    # ------------------------- public API -------------------------
    def get(self, vendor: str, path: str, *, vdom: str = "",
            use_external_engines: bool = False) -> Any:
        """Return a parsed config for ``path``, rebuilding if the file changed.

        ``vdom`` participates in the cache key so FortiGate configs parsed for
        different VDOMs do not collide.
        """
        vendor = (vendor or "").lower()
        vdom = vdom or ""
        key = self._path_key(vendor, path, vdom)
        stat = os.stat(path)
        with self._lock:
            hit = self._cfgs.get(key)
            if hit and self._is_fresh(hit[1], hit[2], stat.st_mtime, stat.st_size):
                self._cfgs.move_to_end(key)
                return hit[0]

        # Build outside the lock (parsing can be slow); store under the lock.
        text = clean_config_text(load_config_text(path))
        cfg = self._parse(vendor, text, vdom, use_external_engines)
        with self._lock:
            self._store(self._cfgs, key, (cfg, stat.st_mtime, stat.st_size))
        return cfg

    def get_from_text(self, vendor: str, text: str, *, vdom: str = "",
                      use_external_engines: bool = False) -> Any:
        """Return a parsed config for already-read ``text`` (content-hash keyed)."""
        vendor = (vendor or "").lower()
        vdom = vdom or ""
        key = self._text_key(vendor, text, vdom)
        with self._lock:
            hit = self._cfgs.get(key)
            if hit:
                self._cfgs.move_to_end(key)
                return hit[0]
        cfg = self._parse(vendor, text, vdom, use_external_engines)
        with self._lock:
            self._store(self._cfgs, key, (cfg, None, None))
        return cfg

    def get_device(self, vendor: str, path: str, *, vdom: str = "",
                   use_external_engines: bool = False) -> Any:
        """Return the IR ``Device`` for ``path``, cached alongside the parsed config."""
        vendor = (vendor or "").lower()
        vdom = vdom or ""
        key = self._path_key(vendor, path, vdom)
        stat = os.stat(path)
        with self._lock:
            hit = self._devices.get(key)
            if hit and self._is_fresh(hit[1], hit[2], stat.st_mtime, stat.st_size):
                self._devices.move_to_end(key)
                return hit[0]

        cfg = self.get(vendor, path, vdom=vdom, use_external_engines=use_external_engines)
        device = self._to_ir(vendor, cfg, device_name=os.path.splitext(os.path.basename(path))[0])
        with self._lock:
            self._store(self._devices, key, (device, stat.st_mtime, stat.st_size))
        return device

    def clear(self) -> int:
        """Drop all cached configs and devices. Returns the number of cfg entries cleared."""
        with self._lock:
            removed = len(self._cfgs)
            self._cfgs.clear()
            self._devices.clear()
            return removed

    def status(self, limit: int = 20) -> Dict[str, Any]:
        with self._lock:
            return {
                "configs": len(self._cfgs),
                "devices": len(self._devices),
                "max_entries": self._max,
                "keys": sorted(self._cfgs.keys())[:limit],
            }

    # ------------------------- internals -------------------------
    @staticmethod
    def _parse(vendor: str, text: str, vdom: str, use_external_engines: bool) -> Any:
        # Imported lazily to avoid a hard import cycle at module load time.
        from parsers.loader import get_engine_from_text
        cfg, _vendor, _conf = get_engine_from_text(
            text, vendor=vendor, vdom=vdom, use_external_engines=use_external_engines
        )
        return cfg

    @staticmethod
    def _to_ir(vendor: str, cfg: Any, device_name: str) -> Any:
        if vendor == "asa":
            from parsers.cisco.asa import ir_export
            return ir_export.to_ir(cfg, device_name=device_name)
        if vendor == "fortigate":
            from parsers.fortigate import ir_export
            return ir_export.to_ir(cfg, device_name=device_name)
        from parsers.loader import ConfigLoadError
        raise ConfigLoadError(f"IR export not implemented for {vendor}")
