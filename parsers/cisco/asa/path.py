"""Packet path evaluation (NAT + ACL) for Cisco ASA."""

from __future__ import annotations

import ipaddress
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple, Union

from .parser import (
    ASAConfig,
    _pick_preferred_address,
    _evaluate_nat,
    _evaluate_acl_flow,
    _entry_summary,
    _has_any_endpoint,
    _service_matches,
    nets_overlap,
)

__all__ = ["path_check"]


def path_check(
    cfg_text: str,
    src: str,
    dst: str,
    proto: Optional[str] = None,
    dports: Optional[Set[int]] = None,
    include_any: bool = True,
    guess_interface_pairs: bool = True,
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
            _add_candidate(rule_dst_if, "out")
        if rule_src_if:
            _add_candidate(rule_src_if, "out")
            _add_candidate(rule_src_if, "in")
        if nat_direction == "inbound" and rule_src_if and rule_dst_if is None:
            _add_candidate(rule_src_if, "in")
    else:
        if dst_iface:
            _add_candidate(dst_iface, "in")
            _add_candidate(dst_iface, "out")
        if src_iface:
            _add_candidate(src_iface, "out")
            _add_candidate(src_iface, "in")

    acl_context = (
        {"candidates": [{"interface": c["interface"], "direction": c["direction"]} for c in candidates]}
        if candidates
        else None
    )
    acl_info = _evaluate_acl_flow(cfg, src_after, dst_after, svc_filter, include_any, acl_context)
    matches = acl_info.get("matches") or []
    warnings: List[str] = []
    if guess_interface_pairs and matches:
        extras, inferred_warnings = _augment_acl_matches(
            cfg, matches, src_after, dst_after, svc_filter, include_any
        )
        if extras:
            matches.extend(extras)
            acl_info["matches"] = matches
        if inferred_warnings:
            warnings.extend(inferred_warnings)
            acl_info["warnings"] = warnings
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


def _augment_acl_matches(
    cfg: ASAConfig,
    matches: List[dict],
    src_ip: ipaddress.IPv4Address,
    dst_ip: ipaddress.IPv4Address,
    svc_filter: Optional[dict],
    include_any: bool,
) -> Tuple[List[dict], List[str]]:
    """Infer counterpart ACL matches and emit warnings for imbalances."""

    if not matches:
        return [], []

    def _extract_pair_key(name: Optional[str]) -> Optional[Tuple[str, str]]:
        if not name:
            return None
        lower = name.lower()
        if lower.endswith("_in"):
            return (lower[:-3], "in")
        if lower.endswith("_out"):
            return (lower[:-4], "out")
        return None

    entries = cfg.flatten_acl()
    entries_by_pair: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for entry in entries:
        pair = _extract_pair_key(entry.get("acl"))
        if not pair:
            continue
        entries_by_pair[pair].append(entry)

    matched_by_pair: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    existing_raw = {match.get("raw") for match in matches if match.get("raw")}
    for match in matches:
        pair = _extract_pair_key(match.get("acl"))
        if pair:
            matched_by_pair[pair].append(match)

    new_matches: List[dict] = []
    warnings: List[str] = []
    processed_bases: Set[str] = set()
    src_set = {src_ip}
    dst_set = {dst_ip}

    def _format_acl_names(items: List[dict]) -> str:
        names = {item.get("acl") for item in items if item.get("acl")}
        return ", ".join(sorted(names)) if names else "(unnamed)"

    def _find_counterpart(base: str, direction: str) -> Optional[dict]:
        for entry in entries_by_pair.get((base, direction), []):
            if entry.get("raw") in existing_raw:
                continue
            if not include_any and _has_any_endpoint(entry):
                continue
            if not nets_overlap(entry.get("src", set()), src_set):
                continue
            if not nets_overlap(entry.get("dst", set()), dst_set):
                continue
            if svc_filter and not _service_matches(cfg, entry, svc_filter):
                continue
            new_match = {
                "raw": entry.get("raw"),
                "summary": _entry_summary(entry),
                "acl": entry.get("acl"),
                "action": entry.get("action"),
                "binding": entry.get("binding"),
                "inferred": True,
            }
            existing_raw.add(entry.get("raw"))
            matched_by_pair[(base, direction)].append(new_match)
            return new_match
        return None

    for (base, direction), current_matches in list(matched_by_pair.items()):
        if base in processed_bases:
            continue
        processed_bases.add(base)
        inbound = matched_by_pair.get((base, "in"), [])
        outbound = matched_by_pair.get((base, "out"), [])

        if inbound and not outbound:
            counterpart = _find_counterpart(base, "out")
            if counterpart:
                new_matches.append(counterpart)
                outbound = matched_by_pair.get((base, "out"), [])
            else:
                names = _format_acl_names(inbound)
                warnings.append(
                    f"ACL set '{names}' matched (inbound) but no corresponding outbound rule was found."
                )
        if outbound and not inbound:
            counterpart = _find_counterpart(base, "in")
            if counterpart:
                new_matches.append(counterpart)
                inbound = matched_by_pair.get((base, "in"), [])
            else:
                names = _format_acl_names(outbound)
                warnings.append(
                    f"ACL set '{names}' matched (outbound) but no corresponding inbound rule was found."
                )

        if len(inbound) > 1:
            names = _format_acl_names(inbound)
            warnings.append(
                f"Multiple inbound ACL rules matched for '{names}'."
            )
        if len(outbound) > 1:
            names = _format_acl_names(outbound)
            warnings.append(
                f"Multiple outbound ACL rules matched for '{names}'."
            )

    return new_matches, warnings
