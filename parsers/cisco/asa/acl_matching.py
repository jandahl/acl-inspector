# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""ACL matching and evaluation helpers for ASA parser.

Functions for evaluating ACL entries against packet flows and formatting
ACL entry summaries.
"""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Union

from .utils import nets_overlap
from .services import service_matches as _service_matches

if TYPE_CHECKING:
    from .parser import ASAConfig

__all__ = [
    "_has_any_endpoint",
    "_pick_preferred_address",
    "_entry_summary",
    "_binding_applicable",
    "_evaluate_acl_flow",
]


def _has_any_endpoint(e: dict) -> bool:
    """Check if ACL entry has 'any' as source or destination.

    Args:
        e: ACL entry dict with 'src' and 'dst' sets

    Returns:
        True if entry contains 0.0.0.0/0 or ::/0 in src or dst
    """
    any4 = ipaddress.ip_network('0.0.0.0/0')
    try:
        any6 = ipaddress.ip_network('::/0')
    except Exception:
        any6 = None
    for side in ('src', 'dst'):
        for n in e.get(side, set()):
            if isinstance(n, ipaddress.IPv4Network) and n == any4:
                return True
            if any6 is not None and isinstance(n, type(any6)) and n == any6:  # type: ignore
                return True
    return False


def _pick_preferred_address(
    nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]]
) -> Optional[ipaddress.IPv4Address]:
    """Pick a representative IPv4 address from a set of addresses/networks.

    Prefers individual addresses over network addresses. For networks,
    returns the network address of the most specific (longest prefix) network.

    Args:
        nets: Set of IPv4Address, IPv4Network, or string values

    Returns:
        IPv4Address or None if no valid address found
    """
    addresses = sorted([n for n in nets if isinstance(n, ipaddress.IPv4Address)])
    if addresses:
        return addresses[0]
    networks = sorted(
        [n for n in nets if isinstance(n, ipaddress.IPv4Network)],
        key=lambda n: (-n.prefixlen, str(n))
    )
    if networks:
        return networks[0].network_address
    return None


def _entry_summary(entry: dict) -> str:
    """Format ACL entry as human-readable summary string.

    Args:
        entry: Flattened ACL entry dict

    Returns:
        String like "permit tcp src=[1.1.1.1] dst=[2.2.2.2] ports=eq 443 bind=outside(in)"
    """
    src_str = ', '.join(sorted(str(s) for s in entry.get('src', [])))
    dst_str = ', '.join(sorted(str(s) for s in entry.get('dst', [])))
    svc = entry.get('svc') or {}
    parts = []
    proto = svc.get('proto') or entry.get('proto')
    if proto:
        parts.append(str(proto))
    sg = svc.get('service_group_at_proto')
    if sg and sg.get('name'):
        parts.append(f"{sg.get('kind')}:{sg.get('name')}")
    port_parts = []
    for op, (p1, p2) in svc.get('dst_ports', []):
        if op == 'range':
            port_parts.append(f"{p1}-{p2}")
        else:
            port_parts.append(f"{op} {p1}")
    for g in sorted(list(svc.get('dst_service_groups', []))):
        port_parts.append(f"group:{g}")
    for o in sorted(list(svc.get('dst_service_objects', []))):
        port_parts.append(f"object:{o}")
    svc_str = ''
    if parts or port_parts:
        head = ' '.join(parts) if parts else ''
        tail = (' ports=' + ','.join(port_parts)) if port_parts else ''
        svc_str = f" {head}{tail}".rstrip()
    binding = entry.get('binding') or {}
    bind_str = ''
    if binding:
        scope = (binding.get('scope') or '').lower()
        direction = binding.get('direction')
        interface = binding.get('interface')
        if scope == 'global':
            bind_str = ' bind=global'
        elif interface:
            bind_str = f" bind={interface}{f'({direction})' if direction else ''}"
        elif scope:
            bind_str = f" bind={scope}"
    return f"{entry['action']}{(' ' + entry['proto']) if entry.get('proto') else ''}{svc_str} src=[{src_str}] dst=[{dst_str}]{bind_str}"


def _binding_applicable(
    binding: Optional[dict],
    context: Optional[dict],
    acl_name: Optional[str] = None
) -> bool:
    """Check if ACL binding matches the interface/direction context.

    Args:
        binding: ACL binding dict with scope, interface, direction
        context: Context dict with candidate interface/direction pairs
        acl_name: Optional ACL name for additional filtering

    Returns:
        True if binding matches context (or no context provided)
    """
    if not context:
        return True
    if not binding:
        return True
    scope = (binding.get('scope') or '').lower()
    if scope in ('global', 'control-plane'):
        return True
    candidates = context.get('candidates') or []
    if not candidates:
        return True
    interface = (binding.get('interface') or '').lower() or None
    direction = (binding.get('direction') or '').lower() or None
    acl_lower = acl_name.lower() if acl_name else None
    for cand in candidates:
        cand_iface = (cand.get('interface') or '').lower() or None
        cand_dir = (cand.get('direction') or '').lower() or None
        if interface is not None:
            if cand_iface is None or cand_iface != interface:
                continue
        else:
            if cand_iface is not None:
                continue
        if direction is not None:
            if cand_dir is None or cand_dir != direction:
                continue
        if acl_lower:
            cand_acls = [name.lower() for name in cand.get('acls', [])]
            if cand_acls and acl_lower not in cand_acls:
                continue
        return True
    return False if candidates else True


def _evaluate_acl_flow(
    cfg: ASAConfig,
    src_ip: ipaddress.IPv4Address,
    dst_ip: ipaddress.IPv4Address,
    svc_filter: Optional[dict],
    include_any: bool,
    iface_context: Optional[dict] = None
) -> dict:
    """Evaluate ACL flow for a packet across all applicable ACL entries.

    Args:
        cfg: ASAConfig instance
        src_ip: Source IP address
        dst_ip: Destination IP address
        svc_filter: Optional service filter dict with 'proto' and 'dports'
        include_any: Whether to include rules with 'any' endpoints
        iface_context: Optional interface/direction context for filtering

    Returns:
        Dict with 'decision' (permit/deny/no-match), 'matches' (list of up to 10
        matching entries), and 'inspected' (count of entries evaluated)
    """
    entries = cfg.flatten_acl()
    src_set = {src_ip}
    dst_set = {dst_ip}
    matches: List[dict] = []
    inspected = 0
    for entry in entries:
        inspected += 1
        if not include_any and _has_any_endpoint(entry):
            continue
        if iface_context and not _binding_applicable(entry.get('binding'), iface_context, entry.get('acl')):
            continue
        if not nets_overlap(entry['src'], src_set):
            continue
        if not nets_overlap(entry['dst'], dst_set):
            continue
        if svc_filter and not _service_matches(cfg, entry, svc_filter):
            continue
        matches.append({
            'raw': entry['raw'],
            'summary': _entry_summary(entry),
            'acl': entry.get('acl'),
            'action': entry.get('action'),
            'binding': entry.get('binding'),
        })
        if len(matches) >= 10:
            break
    if matches:
        decision = matches[0]['action']
    else:
        decision = 'no-match'
    return {'decision': decision, 'matches': matches, 'inspected': inspected}
