# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Packet path evaluation (NAT + policy) for FortiGate."""

from __future__ import annotations

import ipaddress
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

from .config import FTGConfig, nets_overlap, _service_matches

__all__ = ["path_check"]


def path_check(
    cfg_text: str,
    src: str,
    dst: str,
    proto: Optional[str] = None,
    dports: Optional[Set[int]] = None,
    include_any: bool = True,
    vdom: Optional[str] = None,
) -> dict:
    """Evaluate FortiGate policy/NAT outcome for a single flow."""
    cfg = FTGConfig(cfg_text, vdom=vdom)
    src_ip, src_set = _resolve_endpoint(cfg, src)
    dst_ip, dst_set = _resolve_endpoint(cfg, dst)
    if src_ip is None or dst_ip is None:
        raise ValueError("unable to resolve source/destination to concrete IPv4 addresses")

    dports = dports or set()
    svc_filter = {"proto": proto, "dports": dports} if (proto or dports) else None

    flattened = cfg.flatten_policies()
    matches: List[dict] = []
    winner: Optional[dict] = None

    for entry in flattened:
        if not include_any and _has_any_endpoint(entry):
            continue
        if not nets_overlap(entry.get("src", set()), src_set):
            continue
        if not nets_overlap(entry.get("dst", set()), dst_set):
            continue
        if svc_filter and not _service_matches(entry, svc_filter):
            continue
        match = _format_match(entry)
        matches.append(match)
        winner = entry
        break  # FortiGate policies stop at first match

    if winner is None:
        decision = "implicit-deny"
    else:
        decision = winner.get("action", "deny")

    nat_result = _evaluate_nat(cfg, src_ip, dst_ip, winner)
    acl_info = {
        "decision": decision,
        "matches": matches,
        "warnings": [],
    }
    context = _build_context(flattened, winner, nat_result)

    return {
        "input": {
            "src": src,
            "dst": dst,
            "proto": proto,
            "dports": sorted(list(dports)),
        },
        "resolved": {
            "src": str(src_ip),
            "dst": str(dst_ip),
            "post_nat_src": nat_result["translations"]["src"]["after"],
            "post_nat_dst": nat_result["translations"]["dst"]["after"],
        },
        "nat": nat_result,
        "acl": acl_info,
        "allowed": decision == "permit",
        "context": context,
        "packet_tracer": [],  # FortiGate does not expose ASA-style packet-tracer
    }


def _resolve_endpoint(cfg: FTGConfig, token: str) -> Tuple[Optional[ipaddress.IPv4Address], Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]]:
    token = (token or "").strip()
    if not token:
        return None, set()
    try:
        ip = ipaddress.ip_address(token)
        return ip, {ip}
    except ValueError:
        pass
    try:
        net = ipaddress.ip_network(token, strict=False)
        return net.network_address, {net}
    except ValueError:
        pass
    resolved = cfg.resolve_addr_token(token)
    normalized: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]] = set()
    for item in resolved:
        if isinstance(item, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
            normalized.add(item)
        elif isinstance(item, str):
            try:
                normalized.add(ipaddress.ip_address(item))
            except ValueError:
                try:
                    normalized.add(ipaddress.ip_network(item, strict=False))
                except ValueError:
                    continue
    picked = _pick_preferred_address(normalized)
    return picked, normalized


def _pick_preferred_address(values: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]) -> Optional[ipaddress.IPv4Address]:
    for item in values:
        if isinstance(item, ipaddress.IPv4Address):
            return item
    for item in values:
        if isinstance(item, ipaddress.IPv4Network):
            return item.network_address
    return None


def _has_any_endpoint(entry: dict) -> bool:
    def _set_is_any(items: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]]) -> bool:
        for value in items:
            if isinstance(value, str) and value.lower() in {"all", "any"}:
                return True
            if isinstance(value, ipaddress.IPv4Network) and value.prefixlen == 0:
                return True
        return False

    return _set_is_any(entry.get("src", set())) or _set_is_any(entry.get("dst", set()))


def _format_match(entry: dict) -> dict:
    binding = entry.get("binding") or {}
    name = binding.get("name") or f"policy {entry.get('policy_id')}"
    srcintf = ", ".join(binding.get("srcintf") or ["any"])
    dstintf = ", ".join(binding.get("dstintf") or ["any"])
    summary = f"{entry.get('action', 'deny')} {entry.get('proto', 'ip')} {srcintf}->{dstintf}"
    return {
        "raw": entry.get("raw"),
        "summary": summary,
        "acl": name,
        "action": entry.get("action"),
        "binding": binding,
    }


def _evaluate_nat(cfg: FTGConfig, src_ip: ipaddress.IPv4Address, dst_ip: ipaddress.IPv4Address, winner: Optional[dict]) -> dict:
    src_after = src_ip
    dst_after = dst_ip
    steps: List[dict] = []

    if winner:
        binding = winner.get("binding") or {}
        vip_refs = binding.get("vip_refs") or []
        for vip_name in vip_refs:
            vip = cfg.vips.get(vip_name)
            if not vip:
                continue
            mapped_ip = _first_ip(vip.get("mappedip"))
            if mapped_ip:
                dst_after = ipaddress.ip_address(mapped_ip)
                steps.append(
                    {
                        "type": "vip",
                        "direction": "inbound",
                        "rule": {"name": vip_name, "extip": vip.get("extip"), "mappedip": vip.get("mappedip")},
                    }
                )
                break

        if winner.get("nat"):
            pool_ip = None
            if winner.get("ippool") and winner.get("poolname"):
                pool_name = winner["poolname"][0] if isinstance(winner["poolname"], list) else winner["poolname"]
                pool = cfg.ippools.get(pool_name, {})
                pool_ip = pool.get("startip")
            if pool_ip:
                src_after = ipaddress.ip_address(pool_ip)
            steps.append(
                {
                    "type": "policy-snat",
                    "direction": "outbound",
                    "rule": {
                        "policy_id": winner.get("policy_id"),
                        "policy_name": binding.get("name"),
                        "pool": winner.get("poolname"),
                    },
                }
            )

    if not any(step["type"] == "policy-snat" for step in steps):
        central_rule = _match_central_snat(cfg, src_ip, dst_ip)
        if central_rule:
            trans_ip = _resolve_pool_ip(cfg, central_rule.get("nat-ippool"))
            if trans_ip:
                src_after = ipaddress.ip_address(trans_ip)
            steps.append(
                {
                    "type": "central-snat",
                    "direction": "outbound",
                    "rule": central_rule,
                }
            )

    translations = {
        "src": {"before": str(src_ip), "after": str(src_after)},
        "dst": {"before": str(dst_ip), "after": str(dst_after)},
    }
    nat_info = {
        "applied": bool(steps),
        "direction": steps[-1]["direction"] if steps else None,
        "type": steps[-1]["type"] if steps else None,
        "rule": steps[-1]["rule"] if steps else None,
        "steps": steps,
        "translations": translations,
    }
    return nat_info


def _match_central_snat(cfg: FTGConfig, src_ip: ipaddress.IPv4Address, dst_ip: ipaddress.IPv4Address) -> Optional[dict]:
    for entry in cfg.central_snat_map:
        if _tokens_match_ip(cfg, entry.get("orig-addr"), src_ip) and _tokens_match_ip(cfg, entry.get("dst-addr"), dst_ip):
            return entry
    return None


def _tokens_match_ip(cfg: FTGConfig, tokens: Optional[Union[str, Sequence[str]]], ip: ipaddress.IPv4Address) -> bool:
    if tokens is None:
        return True
    seq = tokens if isinstance(tokens, (list, tuple, set)) else [tokens]
    for token in seq:
        nets = cfg.resolve_addr_token(token)
        if nets_overlap(nets, {ip}):
            return True
    return False


def _resolve_pool_ip(cfg: FTGConfig, pool_tokens: Optional[Union[str, Sequence[str]]]) -> Optional[str]:
    if not pool_tokens:
        return None
    seq = pool_tokens if isinstance(pool_tokens, (list, tuple, set)) else [pool_tokens]
    for name in seq:
        pool = cfg.ippools.get(name)
        if pool and pool.get("startip"):
            return pool["startip"]
    return None


def _first_ip(values: Optional[Union[str, Sequence[str]]]) -> Optional[str]:
    if values is None:
        return None
    if isinstance(values, str):
        return values
    return values[0] if values else None


def _build_context(policies: List[dict], winner: Optional[dict], nat_result: dict) -> dict:
    candidates = []
    for entry in policies[:25]:
        binding = entry.get("binding") or {}
        candidates.append(
            {
                "interface": ", ".join(binding.get("srcintf") or ["any"]),
                "direction": "->".join(
                    [
                        ", ".join(binding.get("srczone") or ["any"]),
                        ", ".join(binding.get("dstzone") or ["any"]),
                    ]
                ),
                "acls": [binding.get("name") or f"policy {entry.get('policy_id')}"],
            }
        )

    walks = []
    if winner:
        walks.append(
            {
                "interface": ", ".join((winner.get("binding") or {}).get("srcintf") or ["any"]),
                "direction": "policy",
                "acls": [(winner.get("binding") or {}).get("name") or f"policy {winner.get('policy_id')}"],
                "decision": winner.get("action"),
                "matches": [_format_match(winner)],
            }
        )

    return {
        "nat_direction": nat_result.get("direction"),
        "acl_candidates": candidates,
        "global_acls": [],
        "walks": walks,
    }
