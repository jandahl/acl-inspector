# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Service-related helpers for Cisco ASA parsing."""

from __future__ import annotations

from typing import Optional, Set, Tuple, List, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .parser import ASAConfig


def entry_effective_protos(cfg: "ASAConfig", entry: dict) -> Set[str]:
    svc = entry.get("svc") or {}
    protos: Set[str] = set()
    if svc.get("proto") in {"ip", "tcp", "udp", "icmp"}:
        protos.add(svc["proto"])
    sg = svc.get("service_group_at_proto")
    if sg and sg.get("kind") == "object-group" and hasattr(cfg, "service_object_groups"):
        name = sg.get("name")
        for spec in cfg.resolve_service_group(name):
            if "proto" in spec:
                protos.add(spec["proto"])
    if entry.get("proto") in {"ip", "tcp", "udp", "icmp"}:
        protos.add(entry["proto"])
    return protos or {"ip"}


def spec_to_range_tuple(cfg: "ASAConfig", spec: dict) -> Optional[Tuple[Optional[int], Optional[int]]]:
    op = spec.get("op")
    if not op:
        return (None, None)
    v1 = spec.get("v1")
    v2 = spec.get("v2")
    p1 = cfg._port_from_token(v1, spec.get("proto")) if v1 else None
    p2 = cfg._port_from_token(v2, spec.get("proto")) if v2 else None
    if op == "range":
        return (p1, p2)
    if op == "eq":
        return (p1, p1)
    if op == "lt":
        return (0, (p1 - 1) if (p1 is not None and p1 > 0) else None)
    if op == "gt":
        return ((p1 + 1) if p1 is not None else None, 65535)
    if op == "neq":
        return (None, None)
    return None


def dst_ports_from_entry(
    cfg: "ASAConfig", entry: dict
) -> List[Tuple[str, str, Tuple[Optional[int], Optional[int]]]]:
    svc = entry.get("svc") or {}
    ports: List[Tuple[str, str, Tuple[Optional[int], Optional[int]]]] = []
    for op, rng in svc.get("dst_ports", []):
        for proto in entry_effective_protos(cfg, entry):
            ports.append((proto, op, rng))
    for group_name in svc.get("dst_service_groups", set()):
        for spec in cfg.resolve_service_group(group_name):
            rng = spec_to_range_tuple(cfg, spec)
            if rng is not None:
                ports.append((spec["proto"], spec.get("op") or "eq", rng))
    sg = svc.get("service_group_at_proto")
    if sg and sg.get("kind") == "object-group":
        for spec in cfg.resolve_service_group(sg.get("name")):
            rng = spec_to_range_tuple(cfg, spec)
            if rng is not None:
                ports.append((spec["proto"], spec.get("op") or "eq", rng))
    return ports


def service_matches(cfg: "ASAConfig", entry: dict, svc_filter: Optional[dict]) -> bool:
    if not svc_filter:
        return True
    want_proto = svc_filter.get("proto")
    want_ports = svc_filter.get("dports") or set()
    entry_protos = entry_effective_protos(cfg, entry)
    if want_proto and want_proto not in entry_protos and "ip" not in entry_protos:
        return False
    if not want_ports:
        return True
    port_specs = dst_ports_from_entry(cfg, entry)
    if not port_specs:
        return True
    for port in want_ports:
        for eproto, op, (start, end) in port_specs:
            if want_proto and eproto not in {want_proto, "ip"}:
                continue
            if start is None and end is None:
                return True
            if start is not None and end is not None and start <= port <= end:
                return True
            if start is None and end is not None and port <= end:
                return True
            if start is not None and end is None and port >= start:
                return True
    return False


__all__ = [
    "entry_effective_protos",
    "spec_to_range_tuple",
    "dst_ports_from_entry",
    "service_matches",
]
