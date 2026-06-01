# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Flattened ACL inspection helpers for Cisco ASA."""

from __future__ import annotations

import ipaddress
from typing import Dict, List, Optional, Set, Union

from .parser import (
    ASAConfig,
    nets_overlap,
    _service_matches,
    _has_any_endpoint,
)

__all__ = ["evaluate_acl", "compare_old_new", "inspect_host"]


def evaluate_acl(
    entries: List[dict],
    target_nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]],
    cfg: Optional[ASAConfig] = None,
    service_filter: Optional[dict] = None,
    ignore_any: bool = True,
) -> List[dict]:
    """Filter flattened ACL entries that affect ``target_nets``."""

    affected: List[dict] = []
    for entry in entries:
        if ignore_any and _has_any_endpoint(entry):
            continue
        if nets_overlap(entry["src"], target_nets) or nets_overlap(entry["dst"], target_nets):
            if service_filter:
                if cfg is None:
                    continue
                if not _service_matches(cfg, entry, service_filter):
                    continue
            affected.append(entry)
    return affected


def compare_old_new(
    cfg_text: str,
    old_target: str,
    new_target: str,
    service_filter: Optional[dict] = None,
    include_any: bool = False,
    use_external_engines: bool = False,
    cfg: Optional[Union[ASAConfig, Any]] = None,
) -> dict:
    """Compare ACL impact for two network targets within the same config."""
    if cfg is None:
        if use_external_engines:
            from .advanced_parser import AdvancedASAConfig
            cfg = AdvancedASAConfig(cfg_text)
        else:
            cfg = ASAConfig(cfg_text)

    old_nets = cfg.resolve_network(old_target)
    new_nets = cfg.resolve_network(new_target)
    entries = cfg.flatten_acl()
    old_hits = evaluate_acl(entries, old_nets, cfg, service_filter=service_filter, ignore_any=(not include_any))
    new_hits = evaluate_acl(entries, new_nets, cfg, service_filter=service_filter, ignore_any=(not include_any))

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
    include_any: bool = False,
    use_external_engines: bool = False,
    cfg: Optional[Union[ASAConfig, Any]] = None,
) -> dict:
    """Collect flattened ACL entries affecting ``target``."""
    if cfg is None:
        if use_external_engines:
            from .advanced_parser import AdvancedASAConfig
            cfg = AdvancedASAConfig(cfg_text)
        else:
            cfg = ASAConfig(cfg_text)

    target_nets = cfg.resolve_network(target)
    entries = cfg.flatten_acl()
    hits = evaluate_acl(entries, target_nets, cfg, service_filter=service_filter, ignore_any=(not include_any))
    aliases = cfg.find_alias_objects(target, target_nets)
    return {"hits": hits, "target_nets": target_nets, "aliases": aliases}
