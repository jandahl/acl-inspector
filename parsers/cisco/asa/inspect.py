# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Flattened ACL inspection helpers for Cisco ASA."""

from __future__ import annotations

import ipaddress
from typing import List, Optional, Set, Union

from .parser import (
    ASAConfig,
    nets_overlap,
    _service_matches,
    _has_any_endpoint,
)

__all__ = ["evaluate_acl", "compare_old_new", "inspect_host"]


def _device_query(cfg_text, cfg, device, use_external_engines):
    """Build a DeviceQuery (IR spine) from whichever input is provided.

    Precedence: an explicit ``device`` (IR) > a parsed ``cfg`` > raw ``cfg_text``.
    The web layer passes a cached IR ``device``; the CLI passes ``cfg_text``.
    """
    from parsers.query import DeviceQuery
    if device is None:
        if cfg is None:
            from parsers.loader import get_engine
            cfg = get_engine('asa', cfg_text, use_external_engines=use_external_engines)
        device = cfg.to_ir()
    return DeviceQuery(device)


def evaluate_acl(
    entries: List[dict],
    target_nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]],
    cfg: ASAConfig,
    service_filter: Optional[dict] = None,
    ignore_any: bool = True,
) -> List[dict]:
    """Filter flattened ASA ACL entries affecting the target."""

    out: List[dict] = []
    for entry in entries:
        if ignore_any and _has_any_endpoint(entry):
            continue
        if nets_overlap(entry["src"], target_nets) or nets_overlap(entry["dst"], target_nets):
            if service_filter and not _service_matches(cfg, entry, service_filter):
                continue
            out.append(entry)
    return out


def compare_old_new(
    cfg_text: str,
    old_target: str,
    new_target: str,
    service_filter: Optional[dict] = None,
    include_any: bool = False,
    use_external_engines: bool = False,
    cfg: Optional[ASAConfig] = None,
    device=None,
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

        Resolution and matching go through the IR spine (:class:`DeviceQuery`).
        ``device`` (an IR ``Device``) or a pre-parsed ``cfg`` may be supplied to
        avoid re-parsing ``cfg_text``.
    """
    q = _device_query(cfg_text, cfg, device, use_external_engines)

    old_nets = q.resolve(old_target)
    new_nets = q.resolve(new_target)
    old_hits = q.rules_affecting(old_nets, service_filter=service_filter, ignore_any=(not include_any))
    new_hits = q.rules_affecting(new_nets, service_filter=service_filter, ignore_any=(not include_any))

    def rule_id(e):
        return (e.get("acl"), e["raw"], tuple(sorted([str(s) for s in e["src"]])), tuple(sorted([str(d) for d in e["dst"]])))

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
    cfg: Optional[ASAConfig] = None,
    device=None,
) -> dict:
    """Collect flattened ACL entries affecting ``target``.
    
    Args:
        cfg_text: Raw ASA configuration text.
        target: Network object or IP address to inspect.
        service_filter: Optional dict to constrain matches.
        include_any: When True, do not drop rules with ``any`` in src/dst.
        use_external_engines: If True, use parallel advanced parsing engines.

    Returns:
        dict containing ``hits`` (list of flattened rules), ``target_nets``, ``aliases``,
        and ``parent_groups`` (sorted list of object-group names that directly contain
        ``target``; empty list when ``target`` is a raw IP or not a group member).

        Resolution and matching go through the IR spine (:class:`DeviceQuery`).
        ``device`` (an IR ``Device``) or a pre-parsed ``cfg`` may be supplied to
        avoid re-parsing ``cfg_text``.
    """
    q = _device_query(cfg_text, cfg, device, use_external_engines)

    target_nets = q.resolve(target)
    hits = q.rules_affecting(target_nets, service_filter=service_filter, ignore_any=(not include_any))
    aliases = q.alias_objects(target, target_nets)
    parent_groups = q.group_membership().get(target, [])
    return {"hits": hits, "target_nets": target_nets, "aliases": aliases, "parent_groups": parent_groups}
