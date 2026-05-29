# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Flattened policy inspection helpers for FortiGate."""

from __future__ import annotations

import ipaddress
from typing import Dict, List, Optional, Set, Union

from .config import FTGConfig, nets_overlap, _service_matches

__all__ = ["evaluate", "compare_old_new", "inspect_host"]


def evaluate(
    entries: List[dict],
    target_nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]],
    service_filter: Optional[dict] = None,
) -> List[dict]:
    """Filter flattened FortiGate policy entries."""

    out: List[dict] = []
    for entry in entries:
        if nets_overlap(entry["src"], target_nets) or nets_overlap(entry["dst"], target_nets):
            if not _service_matches(entry, service_filter):
                continue
            out.append(entry)
    return out


def compare_old_new(
    cfg_text: str,
    old_target: str,
    new_target: str,
    service_filter: Optional[dict] = None,
    vdom: Optional[str] = None,
) -> dict:
    """Compare policy impact for two targets within the same FortiGate config."""

    cfg = FTGConfig(cfg_text, vdom=vdom)
    old_nets = cfg.resolve_addr_token(old_target)
    new_nets = cfg.resolve_addr_token(new_target)
    entries = cfg.flatten_policies()
    old_hits = evaluate(entries, old_nets, service_filter)
    new_hits = evaluate(entries, new_nets, service_filter)

    def rule_id(entry: dict) -> str:
        return entry["raw"]

    old_ids = {rule_id(e) for e in old_hits}
    new_ids = {rule_id(e) for e in new_hits}
    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids
    added_to_new = [e for e in new_hits if rule_id(e) in added_ids]
    removed_from_old = [e for e in old_hits if rule_id(e) in removed_ids]
    return {
        "old_hits": old_hits,
        "new_hits": new_hits,
        "added_to_new": added_to_new,
        "removed_from_old": removed_from_old,
    }


def inspect_host(
    cfg_text: str,
    target: str,
    service_filter: Optional[dict] = None,
    vdom: Optional[str] = None,
) -> dict:
    """Resolve policies impacting ``target`` within an optional VDOM."""

    cfg = FTGConfig(cfg_text, vdom=vdom)
    target_nets = cfg.resolve_addr_token(target)
    entries = cfg.flatten_policies()
    hits = evaluate(entries, target_nets, service_filter)
    aliases: Dict[Union[ipaddress.IPv4Address, ipaddress.IPv4Network], Set[str]] = {}
    for net in target_nets:
        if not isinstance(net, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
            continue
        names = cfg.ip_to_objects.get(net, set())
        if names:
            aliases[net] = names
    return {"hits": hits, "target_nets": target_nets, "aliases": aliases}
