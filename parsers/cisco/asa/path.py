"""Packet path evaluation (NAT + ACL) for Cisco ASA."""

from __future__ import annotations

import ipaddress
from typing import Dict, List, Optional, Set, Tuple, Union

from .parser import (
    ASAConfig,
    _pick_preferred_address,
    _evaluate_nat,
    _evaluate_acl_flow,
)

__all__ = ["path_check"]


def path_check(
    cfg_text: str,
    src: str,
    dst: str,
    proto: Optional[str] = None,
    dports: Optional[Set[int]] = None,
    include_any: bool = True,
) -> dict:
    """Evaluate NAT + ACL outcome for a single flow.

    Args:
        cfg_text: ASA configuration text.
        src: Source object/IP/CIDR.
        dst: Destination object/IP/CIDR.
        proto: Optional protocol token (``tcp``, ``udp``, ``icmp``, ``ip``).
        dports: Optional set of destination port integers.
        include_any: Whether to include ``any`` endpoints when walking ACLs.

    Returns:
        dict containing:
            ``input``: Normalised input parameters.
            ``resolved``: Pre- and post-NAT resolved addresses.
            ``nat``: Information on the first matching NAT rule (if any).
            ``acl``: Decision and up to 10 flattened ACL matches (each carries
                ``raw`` + summary data).
            ``allowed``: Boolean permit/deny verdict.
            ``context``: Interface/direction hints used for matching.
        The result is JSON-serialisable so the web UI/CLI can render it directly.
    """

    cfg = ASAConfig(cfg_text)
    if not src or not dst:
        raise ValueError("source and destination are required for path evaluation")

    src_nets = cfg.resolve_network(src)
    dst_nets = cfg.resolve_network(dst)
    src_ip = _pick_preferred_address(src_nets)
    dst_ip = _pick_preferred_address(dst_nets)
    if src_ip is None or dst_ip is None:
        raise ValueError("unable to resolve source/destination to concrete IPv4 addresses")

    dports = dports or set()
    svc_filter = {"proto": proto, "dports": dports} if (proto or dports) else None
    src_iface = cfg.interface_for_ip(src_ip)
    dst_iface = cfg.interface_for_ip(dst_ip)
    preferred_direction: Optional[str] = None
    src_sec = cfg.security_level_for_interface(src_iface)
    dst_sec = cfg.security_level_for_interface(dst_iface)
    if src_sec is not None and dst_sec is not None:
        preferred_direction = "outbound" if src_sec >= dst_sec else "inbound"
    elif src_sec is not None and dst_sec is None:
        preferred_direction = "outbound"

    nat_info, src_after, dst_after = _evaluate_nat(
        cfg, src_ip, dst_ip, src_iface, dst_iface, preferred_direction
    )

    candidates: List[Dict[str, Union[str, None]]] = []
    seen: Set[Tuple[Optional[str], Optional[str]]] = set()

    def _add_candidate(interface: Optional[str], direction: Optional[str]) -> None:
        if not interface:
            return
        key = (interface.lower(), direction.lower() if direction else None)
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            {
                "interface": interface.lower(),
                "direction": direction.lower() if direction else None,
                "display_interface": interface,
                "display_direction": direction,
            }
        )

    if nat_info.get("applied"):
        rule = nat_info.get("rule") or {}
        nat_direction = nat_info.get("direction")
        rule_dst_if = rule.get("dst_if")
        rule_src_if = rule.get("src_if")
        if rule_dst_if:
            _add_candidate(rule_dst_if, "in")
        if rule_src_if:
            _add_candidate(rule_src_if, "out")
        if nat_direction == "inbound" and rule_src_if and rule_dst_if is None:
            _add_candidate(rule_src_if, "in")
    else:
        if dst_iface:
            _add_candidate(dst_iface, "in")
        if src_iface:
            _add_candidate(src_iface, "out")

    acl_context = (
        {"candidates": [{"interface": c["interface"], "direction": c["direction"]} for c in candidates]}
        if candidates
        else None
    )
    acl_info = _evaluate_acl_flow(cfg, src_after, dst_after, svc_filter, include_any, acl_context)
    allowed = acl_info.get("decision") == "permit"
    context = {
        "src_interface": src_iface,
        "dst_interface": dst_iface,
        "nat_direction": nat_info.get("direction"),
        "acl_candidates": [
            {"interface": c["display_interface"], "direction": c["display_direction"]} for c in candidates
        ],
    }
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
            "post_nat_src": str(src_after),
            "post_nat_dst": str(dst_after),
        },
        "nat": nat_info,
        "acl": acl_info,
        "allowed": allowed,
        "context": context,
    }
