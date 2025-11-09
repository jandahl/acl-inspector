"""API handlers for the modular web UI."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from parsers.cisco import asa as asa_parser
from ..state import AppState
from utils.config import clean_config_text, load_config_text

TYPE_PRIORITY = {"context": -1, "object": 0, "group": 1, "literal": 2}
CONTEXT_EXACT_MATCH_SCORE = -10.0
CONTEXT_SUBSTRING_MATCH_SCORE = -5.0

logger = logging.getLogger(__name__)


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
    max_candidates = max(limit * 4, limit + 5)
    stop_scanning = False
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
            if len(results) >= max_candidates:
                stop_scanning = True
                break
        if stop_scanning:
            logger.info(
                "Stopping global scan early for query '%s' after %d candidates (vendor=%s).",
                trimmed_query,
                len(results),
                vendor,
            )
            break
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
    trimmed_query = (query or "").strip()
    if filename:
        path = _resolve_config(state, vendor_norm, filename)
        if not path:
            return 400, {"items": [], "error": "invalid_config"}
        entry = state.index_manager.get_index(vendor_norm, os_tag, version, str(path))
        suggestions = state.index_manager.suggest(entry.index, trimmed_query, mode, limit)
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
    start = time.perf_counter()
    items = _aggregate_suggestions(state, vendors, trimmed_query, mode, limit)
    duration = time.perf_counter() - start
    logger.info(
        "Global search q='%s' mode=%s vendors=%d -> %d item(s) in %.2fs",
        trimmed_query,
        mode,
        len(vendors),
        len(items),
        duration,
    )
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
    """Get index status including manifest summary.

    Returns index cache statistics and manifest metadata including:
    - In-memory cache status
    - Disk cache status with manifest if available
    - Manifest summary with vendor distribution and confidence levels
    - History snapshot

    Returns:
        Tuple of (status_code, payload_dict)
    """
    payload = state.index_manager.status()
    payload["history"] = state.history.snapshot()

    # Enhance manifest data if present
    manifest = payload.get("disk", {}).get("manifest")
    if manifest and isinstance(manifest, dict):
        payload["manifest_summary"] = {
            "count": manifest.get("count", 0),
            "errors": manifest.get("errors", 0),
            "vendor_counts": manifest.get("vendor_counts", {}),
            "confidence_counts": manifest.get("confidence_counts", {}),
            "generated_at": manifest.get("generated_at"),
            "root": manifest.get("root"),
            "vendors": manifest.get("vendors", []),
        }

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


def detect_vendor(
    state: AppState,
    *,
    vendor: Optional[str],
    filename: str,
) -> Tuple[int, Dict[str, Any]]:
    """Auto-detect vendor from config file content.

    Returns vendor identification with confidence score and detection reason.
    If vendor is provided, validates the guess against detected vendor.
    """
    # Import vendor detection from scripts
    import sys
    script_path = Path(__file__).parent.parent.parent / "scripts"
    if str(script_path) not in sys.path:
        sys.path.insert(0, str(script_path))

    from index_repo import _detect_vendor

    # Try all vendor config roots to find the file
    config_path = None
    for v in ['asa', 'fortigate', 'ios', 'ios-xe', 'ios-xr']:
        path = _resolve_config(state, v, filename)
        if path and path.is_file():
            config_path = path
            break

    if not config_path:
        # If vendor specified, try that root
        if vendor:
            config_path = _resolve_config(state, vendor.lower(), filename)

    if not config_path or not config_path.is_file():
        return 400, {"error": "file_not_found", "filename": filename}

    try:
        text = load_config_text(config_path)
    except Exception as exc:
        return 500, {"error": f"read_failed: {exc}"}

    detected_vendor, confidence, reason = _detect_vendor(text, filename)

    result = {
        "filename": filename,
        "detected_vendor": detected_vendor,
        "confidence": confidence,
        "reason": reason,
        "os_tag": _vendor_os_tag(detected_vendor),
    }

    # If vendor was provided, check if it matches
    if vendor:
        vendor_lower = vendor.lower()
        result["provided_vendor"] = vendor_lower
        result["match"] = (vendor_lower == detected_vendor)

    return 200, result


def compare_cross_vendor(
    state: AppState,
    *,
    vendor_a: str,
    filename_a: str,
    vendor_b: str,
    filename_b: str,
) -> Tuple[int, Dict[str, Any]]:
    """Compare ACLs across two different vendor firewalls via IR.

    Converts both configs to IR format and compares ACL entries to identify:
    - Semantically equivalent rules
    - Rules unique to each vendor
    - Coverage differences

    Returns comparison results with match statistics.
    """
    # Import IR modules
    from parsers.cisco.asa import parser as asa_parser_module
    from parsers.cisco.asa import ir_export as asa_export
    from parsers.fortigate.config import FTGConfig
    from parsers.fortigate import ir_export as ftg_export

    # Resolve config paths
    path_a = _resolve_config(state, vendor_a.lower(), filename_a)
    path_b = _resolve_config(state, vendor_b.lower(), filename_b)

    if not path_a or not path_a.is_file():
        return 400, {"error": "config_a_not_found", "vendor": vendor_a, "filename": filename_a}
    if not path_b or not path_b.is_file():
        return 400, {"error": "config_b_not_found", "vendor": vendor_b, "filename": filename_b}

    try:
        # Parse vendor A
        text_a = clean_config_text(load_config_text(path_a))
        if vendor_a.lower() == 'asa':
            cfg_a = asa_parser_module.ASAConfig(text_a)
            device_a = asa_export.to_ir(cfg_a, device_name=filename_a)
        elif vendor_a.lower() == 'fortigate':
            cfg_a = FTGConfig(text_a)
            device_a = ftg_export.to_ir(cfg_a, device_name=filename_a)
        else:
            return 400, {"error": "vendor_a_not_supported", "vendor": vendor_a}

        # Parse vendor B
        text_b = clean_config_text(load_config_text(path_b))
        if vendor_b.lower() == 'asa':
            cfg_b = asa_parser_module.ASAConfig(text_b)
            device_b = asa_export.to_ir(cfg_b, device_name=filename_b)
        elif vendor_b.lower() == 'fortigate':
            cfg_b = FTGConfig(text_b)
            device_b = ftg_export.to_ir(cfg_b, device_name=filename_b)
        else:
            return 400, {"error": "vendor_b_not_supported", "vendor": vendor_b}

    except Exception as exc:
        return 500, {"error": f"parse_failed: {exc}"}

    # Compare ACLs by extracting and normalizing entries
    entries_a = []
    for acl in device_a.acls:
        for entry in acl.entries:
            entries_a.append({
                "action": entry.action,
                "proto": entry.proto,
                "src": sorted(entry.src),
                "dst": sorted(entry.dst),
                "acl": acl.name,
            })

    entries_b = []
    for acl in device_b.acls:
        for entry in acl.entries:
            entries_b.append({
                "action": entry.action,
                "proto": entry.proto,
                "src": sorted(entry.src),
                "dst": sorted(entry.dst),
                "acl": acl.name,
            })

    # Find semantic matches (ignoring ACL name)
    def rule_key(entry: Dict[str, Any]) -> tuple:
        return (
            entry["action"],
            entry["proto"],
            tuple(entry["src"]),
            tuple(entry["dst"]),
        )

    keys_a = {rule_key(e): e for e in entries_a}
    keys_b = {rule_key(e): e for e in entries_b}

    common_keys = set(keys_a.keys()) & set(keys_b.keys())
    only_a_keys = set(keys_a.keys()) - set(keys_b.keys())
    only_b_keys = set(keys_b.keys()) - set(keys_a.keys())

    result = {
        "vendor_a": {
            "vendor": vendor_a,
            "filename": filename_a,
            "os": device_a.os,
            "version": device_a.version,
            "acl_count": len(device_a.acls),
            "entry_count": len(entries_a),
        },
        "vendor_b": {
            "vendor": vendor_b,
            "filename": filename_b,
            "os": device_b.os,
            "version": device_b.version,
            "acl_count": len(device_b.acls),
            "entry_count": len(entries_b),
        },
        "comparison": {
            "common_rules": len(common_keys),
            "unique_to_a": len(only_a_keys),
            "unique_to_b": len(only_b_keys),
            "match_percentage": round(100 * len(common_keys) / max(len(keys_a), len(keys_b), 1), 1),
        },
        "common_examples": [keys_a[k] for k in list(common_keys)[:5]],
        "unique_to_a_examples": [keys_a[k] for k in list(only_a_keys)[:5]],
        "unique_to_b_examples": [keys_b[k] for k in list(only_b_keys)[:5]],
    }

    return 200, result


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
