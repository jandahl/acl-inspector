"""API handlers for the modular web UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from parsers.cisco import asa as asa_parser

from .. import settings as settings_mod
from ..state import AppState


class APIError(Exception):
    """Raised when API handling fails."""


def _resolve_config(state: AppState, vendor: str, filename: str) -> Optional[Path]:
    vendor = (vendor or "").lower()
    root = state.settings.paths.configs.get(vendor)
    if not root or not filename:
        return None
    path = Path(root) / filename
    if not path.is_file():
        return None
    return path


def _extract_meta(vendor: str, text: str) -> Dict[str, str]:
    vendor = (vendor or "").lower()
    if vendor == "asa":
        import re

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


def objects(
    state: AppState,
    *,
    vendor: str,
    os_tag: str,
    version: str,
    filename: str,
    query: str,
    mode: str,
    limit: int,
) -> Tuple[int, Dict[str, Any]]:
    path = _resolve_config(state, vendor, filename)
    if not path:
        return 400, {"items": [], "error": "invalid_config"}

    entry = state.index_manager.get_index(vendor, os_tag, version, str(path))
    items = state.index_manager.suggest(entry.index, query, mode, limit)
    return 200, {"items": items}


def meta(state: AppState, *, vendor: str, filename: str) -> Tuple[int, Dict[str, Any]]:
    path = _resolve_config(state, vendor, filename)
    if not path:
        return 400, {"error": "invalid_config"}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - filesystem errors
        return 500, {"error": f"read_failed: {exc}"}
    return 200, _extract_meta(vendor, text)


def config_text(state: AppState, *, vendor: str, filename: str) -> Tuple[int, Dict[str, Any]]:
    path = _resolve_config(state, vendor, filename)
    if not path:
        return 400, {"error": "invalid_config"}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - filesystem errors
        return 500, {"error": f"read_failed: {exc}"}
    return 200, {"vendor": vendor, "config": filename, "text": text}


def aliases(
    state: AppState,
    *,
    vendor: str,
    filename: str,
    target: str,
) -> Tuple[int, Dict[str, Any]]:
    path = _resolve_config(state, vendor, filename)
    if not path or not target:
        return 200, {"aliases": {}}
    if vendor.lower() != "asa":
        return 200, {"aliases": {}}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - filesystem errors
        return 500, {"error": f"read_failed: {exc}"}
    cfg = asa_parser.ASAConfig(text)
    nets = cfg.resolve_network(target)
    aliases_map = cfg.find_alias_objects(target, nets)
    serialized = {str(net): sorted(list(names)) for net, names in aliases_map.items()}
    return 200, {"aliases": serialized}


def index_status(state: AppState) -> Tuple[int, Dict[str, Any]]:
    payload = state.index_manager.status()
    payload["history"] = state.history.snapshot()
    return 200, payload


def history(state: AppState) -> Tuple[int, Dict[str, Any]]:
    return 200, state.history.snapshot()


def config_listing(state: AppState, *, vendor: str) -> Dict[str, str]:
    vendor = (vendor or "").lower()
    root = state.settings.paths.configs.get(vendor)
    if not root:
        return {}
    try:
        return {
            name: os.path.join(root, name)
            for name in sorted(
                entry
                for entry in os.listdir(root)
                if not entry.startswith(".") and os.path.isfile(os.path.join(root, entry))
            )
        }
    except Exception:
        return {}
