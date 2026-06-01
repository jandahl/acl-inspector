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
) -> dict:
    """Compare ACL impact for two network targets within the same config.

    Args:
        cfg_text: Raw ASA configuration text.
        old_target: Network object/IP to treat as the “original” reference.
        new_target: Network object/IP replacing the original reference.
        service_filter: Optional dict with keys ``proto`` and ``dports`` (set[int])
            to constrain matches to a protocol/port set.
        include_any: When True, do not drop rules with ``any`` in src/dst.
        use_external_engines: If True, use parallel advanced parsing engines.

    Returns:
        dict with keys:
            ``old_hits``: flattened entries affecting ``old_target``.
            ``new_hits``: flattened entries affecting ``new_target``.
            ``added_to_new``: entries unique to the new target.
            ``removed_from_old``: entries unique to the old target.
        Each flattened entry retains the original ACL line under ``raw`` so UIs
        can reference back to the source configuration.
    """
    if use_external_engines:
        from .advanced_parser import AdvancedASAConfig
        try:
            cfg = AdvancedASAConfig(cfg_text)
        except NotImplementedError:
            import sys
            print("Warning: Advanced ASA engine not yet implemented. Falling back to legacy.", file=sys.stderr)
            cfg = ASAConfig(cfg_text)
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
) -> dict:
    """Collect flattened ACL entries affecting ``target``.
    
    Args:
        cfg_text: Raw ASA configuration text.
        target: Network object or IP address to inspect.
        service_filter: Optional dict to constrain matches.
        include_any: When True, do not drop rules with ``any`` in src/dst.
        use_external_engines: If True, use parallel advanced parsing engines.

    Returns:
        dict containing ``hits`` (list of flattened rules), ``target_nets``, and ``aliases``.
    """
    if use_external_engines:
        from .advanced_parser import AdvancedASAConfig
        try:
            cfg = AdvancedASAConfig(cfg_text)
        except NotImplementedError:
            import sys
            print("Warning: Advanced ASA engine not yet implemented. Falling back to legacy.", file=sys.stderr)
            cfg = ASAConfig(cfg_text)
    else:
        cfg = ASAConfig(cfg_text)

    target_nets = cfg.resolve_network(target)
    entries = cfg.flatten_acl()
    hits = evaluate_acl(entries, target_nets, cfg, service_filter=service_filter, ignore_any=(not include_any))
    aliases = cfg.find_alias_objects(target, target_nets)
    return {"hits": hits, "target_nets": target_nets, "aliases": aliases}
