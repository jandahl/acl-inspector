"""API handlers for the modular web UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from parsers.cisco import asa as asa_parser
from ..state import AppState
from utils.config import clean_config_text, load_config_text

TYPE_PRIORITY = {"context": -1, "object": 0, "group": 1, "literal": 2}
CONTEXT_EXACT_MATCH_SCORE = -10.0
CONTEXT_SUBSTRING_MATCH_SCORE = -5.0


def _vendor_os_tag(vendor: str) -> str:
    vendor = (vendor or "").lower()
    if vendor == "asa":
        return "ASA"
    if vendor == "fortigate":
        return "FortiOS"
    return vendor.upper() or "UNKNOWN"


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


def _vendor_os_tag(vendor: str) -> str:
    vendor_lower = (vendor or "").lower()
    if vendor_lower == "asa":
        return "ASA"
    if vendor_lower == "fortigate":
        return "FortiOS"
    return vendor.upper()


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


def _resolve_vendors(state: AppState, requested: str) -> List[str]:
    requested = (requested or "").lower()
    configs = state.settings.paths.configs
    if requested in {"", "all", "any", "auto"}:
        return [vendor for vendor, root in configs.items() if root]
    if requested in configs and configs[requested]:
        return [requested]
    return []


def _decorate_item(
    item: Dict[str, Any],
    index_payload: Dict[str, Any],
    vendor: str,
    filename: str,
    *,
    os_tag: Optional[str] = None,
    version: str = "auto",
) -> Dict[str, Any]:
    details = index_payload.get("object_details", {}) or {}
    addresses: List[str] = []
    if item.get("type") == "object":
        meta = details.get(item.get("value"))
        if isinstance(meta, dict):
            addresses = list(meta.get("addresses") or [])
    popularity_payload = index_payload.get("popularity") or {}
    popularity = 0.0
    if isinstance(popularity_payload, dict):
        type_key = (item.get("type") or "object").lower()
        by_type = popularity_payload.get(type_key)
        if isinstance(by_type, dict):
            popularity = float(by_type.get(item.get("value"), 0.0) or 0.0)
    enriched = dict(item)
    enriched.setdefault("label", str(item.get("label") or item.get("value") or ""))
    enriched["vendor"] = vendor
    enriched["config"] = filename
    enriched["context"] = filename
    enriched["addresses"] = addresses
    enriched["os"] = os_tag or _vendor_os_tag(vendor)
    enriched["version"] = version
    enriched["popularity"] = popularity
    enriched["rank"] = item.get("rank", 0)
    enriched["score"] = item.get("score", float(enriched["rank"]))
    signals = {}
    if isinstance(item.get("signals"), dict):
        signals.update(item["signals"])  # type: ignore[index]
    signals.setdefault("popularity", popularity)
    enriched["signals"] = signals
    if item.get("type") == "context":
        enriched["home"] = "context"
    elif addresses:
        enriched["home"] = "home"
    else:
        enriched["home"] = "probable"
    return enriched


def _aggregate_suggestions(
    state: AppState,
    vendors: Sequence[str],
    query: str,
    mode: str,
    limit: int,
) -> List[Dict[str, Any]]:
    trimmed_query = (query or "").strip()
    if not trimmed_query:
        return []
    results: List[Dict[str, Any]] = []
    q_lower = trimmed_query.lower()
    for vendor in vendors:
        os_tag = _vendor_os_tag(vendor)
        listing = config_listing(state, vendor=vendor)
        for name, path in listing.items():
            entry = state.index_manager.get_index(vendor, os_tag, "auto", str(path))
            suggestions = state.index_manager.suggest(entry.index, trimmed_query, mode, limit)
            for rank, suggestion in enumerate(suggestions):
                enriched = _decorate_item(
                    suggestion, entry.index, vendor, name, os_tag=os_tag, version="auto"
                )
                enriched.setdefault("rank", rank)
                enriched.setdefault("score", suggestion.get("score", float(rank)))
                results.append(enriched)
            if q_lower in name.lower():
                score_value = CONTEXT_EXACT_MATCH_SCORE if name.lower() == q_lower else CONTEXT_SUBSTRING_MATCH_SCORE
                results.append(
                    {
                        "value": name,
                        "label": name,
                        "type": "context",
                        "vendor": vendor,
                        "config": name,
                        "context": name,
                        "addresses": [],
                        "os": os_tag,
                        "version": "auto",
                        "home": "context",
                        "rank": -1,
                        "score": score_value,
                        "signals": {
                            "popularity": 0.0,
                            "typePriority": TYPE_PRIORITY["context"],
                        },
                    }
                )
    if not results:
        return []
    # Stable ordering: better rank first, then type priority, then context/value.
    results.sort(
        key=lambda item: (
            item.get("score", float(item.get("rank", 0))),
            item.get("signals", {}).get("typePriority", TYPE_PRIORITY.get(item.get("type"), 99)),
            item.get("context", ""),
            item.get("value", ""),
        )
    )
    seen: Set[Tuple[str, str, str, str]] = set()
    output: List[Dict[str, Any]] = []
    for item in results:
        key = (
            str(item.get("type")),
            str(item.get("value")),
            str(item.get("context")),
            str(item.get("vendor")),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    return output


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
    vendor_norm = (vendor or "").lower()
    if filename:
        path = _resolve_config(state, vendor_norm, filename)
        if not path:
            return 400, {"items": [], "error": "invalid_config"}
        entry = state.index_manager.get_index(vendor_norm, os_tag, version, str(path))
        suggestions = state.index_manager.suggest(entry.index, query, mode, limit)
        items = [
            _decorate_item(
                suggestion,
                entry.index,
                vendor_norm,
                filename,
                os_tag=os_tag,
                version=version,
            )
            for suggestion in suggestions
        ]
        return 200, {"items": items}

    vendors = _resolve_vendors(state, vendor_norm)
    if not vendors:
        return 200, {"items": []}
    items = _aggregate_suggestions(state, vendors, query, mode, limit)
    return 200, {"items": items}


def singularity_suggestions(
    state: AppState,
    *,
    query: str,
    mode: str,
    limit: int,
) -> Tuple[int, Dict[str, Any]]:
    needle = (query or "").strip()
    if not needle:
        return 200, {"items": []}

    search_limit = state.settings.features.predictive_search.limit
    limit = max(1, min(int(limit or search_limit), search_limit))
    aggregated: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str, str]] = set()

    vendors = sorted(state.settings.paths.configs.keys())
    for vendor in vendors:
        listing = config_listing(state, vendor=vendor)
        if not listing:
            continue
        os_tag = _vendor_os_tag(vendor)
        for name in sorted(listing.keys()):
            path = listing[name]
            try:
                entry = state.index_manager.get_index(vendor, os_tag, "auto", path)
            except Exception:
                continue
            suggestions = state.index_manager.suggest(entry.index, needle, mode, limit)
            for suggestion in suggestions:
                key = (
                    vendor,
                    name,
                    str(suggestion.get("value", "")),
                    str(suggestion.get("type", "")),
                )
                if key in seen:
                    continue
                seen.add(key)
                aggregated.append(
                    {
                        "value": suggestion.get("value"),
                        "label": suggestion.get("label") or suggestion.get("value"),
                        "type": suggestion.get("type") or "object",
                        "vendor": vendor,
                        "config": name,
                        "context": name,
                        "primary": suggestion.get("primary", ""),
                        "literals": suggestion.get("literals", []),
                        "score": suggestion.get("score"),
                    }
                )

    def _score_key(item: Dict[str, Any]) -> Tuple[Any, ...]:
        score = item.get("score")
        if isinstance(score, tuple):
            return (*score, item.get("label"), item.get("config"))
        return (9, item.get("label"), item.get("config"))

    aggregated.sort(key=_score_key)
    return 200, {"items": aggregated[:limit]}


def meta(state: AppState, *, vendor: str, filename: str) -> Tuple[int, Dict[str, Any]]:
    path = _resolve_config(state, vendor, filename)
    if not path:
        return 400, {"error": "invalid_config"}
    try:
        text = clean_config_text(load_config_text(path))
    except Exception as exc:  # pragma: no cover - filesystem errors
        return 500, {"error": f"read_failed: {exc}"}
    return 200, _extract_meta(vendor, text)


def config_text(state: AppState, *, vendor: str, filename: str) -> Tuple[int, Dict[str, Any]]:
    path = _resolve_config(state, vendor, filename)
    if not path:
        return 400, {"error": "invalid_config"}
    try:
        text = clean_config_text(load_config_text(path))
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
        text = clean_config_text(load_config_text(path))
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


def flush_caches(state: AppState, include_disk: bool = False) -> Tuple[int, Dict[str, Any]]:
    summary = state.flush_caches(include_disk=include_disk)
    return 200, {"status": "ok", **summary}


def _parse_ports(values: Sequence[Any]) -> Set[int]:
    ports: Set[int] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, int):
            ports.add(value)
            continue
        text = str(value).strip()
        if not text:
            continue
        for part in text.split(","):
            item = part.strip()
            if not item:
                continue
            try:
                ports.add(int(item))
            except Exception:
                continue
    return ports


def packet_probe(
    state: AppState,
    *,
    vendor: str,
    filename: str,
    src: str,
    dst: str,
    proto: Optional[str],
    dports: Sequence[Any],
    include_any: bool,
) -> Tuple[int, Dict[str, Any]]:
    vendor_lower = (vendor or "").lower()
    path = _resolve_config(state, vendor_lower, filename)
    if not path:
        return 400, {"error": "invalid_config"}
    if vendor_lower != "asa":
        return 400, {"error": "vendor_not_supported"}
    src = (src or "").strip()
    dst = (dst or "").strip()
    if not src or not dst:
        return 400, {"error": "missing_endpoints"}
    try:
        text = clean_config_text(load_config_text(path))
    except Exception as exc:  # pragma: no cover - filesystem errors
        return 500, {"error": f"read_failed: {exc}"}
    ports = _parse_ports(dports)
    try:
        result = asa_parser.path_check(
            text,
            src,
            dst,
            proto=proto if proto else None,
            dports=ports,
            include_any=include_any,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return 500, {"error": str(exc)}
    state.history.record("packet-probe", f"{src}->{dst}")
    return 200, {"vendor": vendor_lower, "config": filename, "result": result}
