# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""NAT evaluation helpers for Cisco ASA parsing."""

from __future__ import annotations

import ipaddress
from typing import Optional, Tuple, TYPE_CHECKING, Dict

if TYPE_CHECKING:  # pragma: no cover
    from .parser import ASAConfig


def nat_result_template(src_ip: ipaddress.IPv4Address, dst_ip: ipaddress.IPv4Address) -> dict:
    return {
        "matched": False,
        "src_eval": src_ip,
        "dst_eval": dst_ip,
        "src_display": str(src_ip),
        "dst_display": str(dst_ip),
        "src_note": None,
        "dst_note": None,
    }


def value_matches_ip(value: str, ip: ipaddress.IPv4Address) -> bool:
    lower = (value or "").lower()
    if lower in {"any", "any4", "any-ipv4"}:
        return True
    try:
        addr = ipaddress.ip_address(value)
        return addr == ip
    except Exception:
        pass
    try:
        net = ipaddress.ip_network(value, strict=False)
        if isinstance(net, ipaddress.IPv4Network):
            return ip in net
    except Exception:
        pass
    return False


def map_value_to_ip(
    value: str,
    default: ipaddress.IPv4Address,
    interface_hint: Optional[str] = None,
) -> Tuple[ipaddress.IPv4Address, str, Optional[str]]:
    val = (value or "").strip()
    if not val:
        return default, str(default), None
    lower = val.lower()
    if lower == "interface":
        note = f"PAT to interface {interface_hint}" if interface_hint else "PAT to interface"
        return default, f"{default} ({note})", note
    try:
        addr = ipaddress.ip_address(val)
        return addr, str(addr), None
    except Exception:
        pass
    try:
        net = ipaddress.ip_network(val, strict=False)
        if isinstance(net, ipaddress.IPv4Network):
            display = str(net)
            return net.network_address, display, None
    except Exception:
        pass
    note = f"mapped to {val}"
    return default, f"{default} ({note})", note


def apply_nat_rule_outbound(
    rule: dict,
    src_ip: ipaddress.IPv4Address,
    dst_ip: ipaddress.IPv4Address,
    src_iface: Optional[str],
    dst_iface: Optional[str],
) -> dict:
    result = nat_result_template(src_ip, dst_ip)
    rule_src_if = (rule.get("src_if") or "").lower() or None
    if rule_src_if and src_iface and rule_src_if != src_iface:
        return result
    if rule.get("type") == "auto":
        real_vals = rule.get("real_values") or []
        if not any(value_matches_ip(val, src_ip) for val in real_vals):
            return result
        mapped_vals = rule.get("mapped_values") or []
        if mapped_vals:
            mapped_ip, display, note = map_value_to_ip(mapped_vals[0], src_ip, rule.get("dst_if"))
            result.update(
                {
                    "matched": True,
                    "src_eval": mapped_ip if isinstance(mapped_ip, ipaddress.IPv4Address) else src_ip,
                    "src_display": display,
                    "src_note": note,
                }
            )
        else:
            result["matched"] = True
        return result
    if rule.get("type") == "manual":
        real_vals = rule.get("src_real_values") or []
        if not any(value_matches_ip(val, src_ip) for val in real_vals):
            return result
        mapped_vals = rule.get("src_mapped_values") or []
        if mapped_vals:
            mapped_ip, display, note = map_value_to_ip(mapped_vals[0], src_ip, rule.get("dst_if"))
            result.update(
                {
                    "matched": True,
                    "src_eval": mapped_ip if isinstance(mapped_ip, ipaddress.IPv4Address) else src_ip,
                    "src_display": display,
                    "src_note": note,
                }
            )
        else:
            result["matched"] = True
        return result
    return result


def apply_nat_rule_inbound(
    rule: dict,
    src_ip: ipaddress.IPv4Address,
    dst_ip: ipaddress.IPv4Address,
    src_iface: Optional[str],
    dst_iface: Optional[str],
) -> dict:
    result = nat_result_template(src_ip, dst_ip)
    rule_src_if = (rule.get("src_if") or "").lower() or None
    rule_dst_if = (rule.get("dst_if") or "").lower() or None
    if rule_dst_if and src_iface and rule_dst_if != src_iface:
        return result
    if rule_src_if and dst_iface and rule_src_if != dst_iface:
        return result
    if rule.get("type") == "auto":
        mapped_vals = rule.get("mapped_values") or []
        if not any(value_matches_ip(val, dst_ip) for val in mapped_vals):
            return result
        real_vals = rule.get("real_values") or []
        if real_vals:
            real_ip, display, note = map_value_to_ip(real_vals[0], dst_ip, rule.get("src_if"))
            if isinstance(real_ip, ipaddress.IPv4Address):
                result["dst_eval"] = real_ip
            result["dst_display"] = display
            result["dst_note"] = note
        result["matched"] = True
        return result
    if rule.get("type") == "manual":
        mapped_vals = rule.get("src_mapped_values") or []
        if not any(value_matches_ip(val, dst_ip) for val in mapped_vals):
            return result
        real_vals = rule.get("src_real_values") or []
        if real_vals:
            real_ip, display, note = map_value_to_ip(real_vals[0], dst_ip, rule.get("src_if"))
            if isinstance(real_ip, ipaddress.IPv4Address):
                result["dst_eval"] = real_ip
            result["dst_display"] = display
            result["dst_note"] = note
        result["matched"] = True
        return result
    return result


def resolve_nat_interface(rule: dict, direction: str) -> Optional[str]:
    if direction == "outbound":
        return (rule.get("src_if") or "").lower() or None
    return (rule.get("dst_if") or "").lower() or None


def match_nat_interface(interface: Optional[str], actual: Optional[str]) -> bool:
    if interface is None:
        return True
    if actual is None:
        return False
    return interface == actual.lower()


def evaluate_nat(
    cfg: "ASAConfig",
    src_ip: ipaddress.IPv4Address,
    dst_ip: ipaddress.IPv4Address,
    src_iface_name: Optional[str],
    dst_iface_name: Optional[str],
    preferred_direction: Optional[str] = None,
) -> Tuple[dict, ipaddress.IPv4Address, ipaddress.IPv4Address]:
    rules = cfg.normalized_nat_rules()
    logs = []
    src_iface = src_iface_name.lower() if src_iface_name else None
    dst_iface = dst_iface_name.lower() if dst_iface_name else None
    for rule in rules:
        attempts = ["outbound", "inbound"]
        if preferred_direction == "inbound":
            attempts = ["inbound", "outbound"]
        for direction in attempts:
            if direction == "outbound":
                applied = apply_nat_rule_outbound(rule, src_ip, dst_ip, src_iface, dst_iface)
            else:
                applied = apply_nat_rule_inbound(rule, src_ip, dst_ip, src_iface, dst_iface)
            logs.append({"raw": rule.get("raw"), "direction": direction, "matched": applied["matched"]})
            if applied["matched"]:
                src_eval = (
                    applied["src_eval"]
                    if isinstance(applied["src_eval"], ipaddress.IPv4Address)
                    else src_ip
                )
                dst_eval = (
                    applied["dst_eval"]
                    if isinstance(applied["dst_eval"], ipaddress.IPv4Address)
                    else dst_ip
                )
                info = {
                    "applied": True,
                    "direction": direction,
                    "rule": {k: rule.get(k) for k in ("raw", "type", "section", "sequence", "src_if", "dst_if")},
                    "translations": {
                        "src": {
                            "before": str(src_ip),
                            "after": applied["src_display"],
                            "note": applied.get("src_note"),
                        },
                        "dst": {
                            "before": str(dst_ip),
                            "after": applied.get("dst_display", str(dst_ip)),
                            "note": applied.get("dst_note"),
                        },
                    },
                    "logs": logs,
                }
                return info, src_eval, dst_eval
    info: Dict[str, object] = {
        "applied": False,
        "direction": None,
        "rule": None,
        "translations": {
            "src": {"before": str(src_ip), "after": str(src_ip), "note": None},
            "dst": {"before": str(dst_ip), "after": str(dst_ip), "note": None},
        },
        "logs": logs,
    }
    return info, src_ip, dst_ip


__all__ = [
    "nat_result_template",
    "value_matches_ip",
    "map_value_to_ip",
    "apply_nat_rule_outbound",
    "apply_nat_rule_inbound",
    "resolve_nat_interface",
    "match_nat_interface",
    "evaluate_nat",
]
