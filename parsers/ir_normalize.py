# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Shared IR normalization helpers.

Both the ASA and FortiGate ``ir_export`` modules used to carry their own copies
of the same boundary-normalization logic (resolve address sets to sorted string
lists, turn ``(op, (start, end))`` port tuples into ``{op, start, end}`` dicts).
That duplication is centralised here so the parser-internal flattened shape maps
to the IR through exactly one path. ``dst_ports_from_ir`` is the inverse, used by
the IR query layer to rebuild matchable port structures.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

__all__ = [
    "addrs_to_strs",
    "dst_ports_to_ir",
    "dst_ports_from_ir",
    "svc_to_ir",
]


def addrs_to_strs(addrs: Optional[Iterable[Any]]) -> List[str]:
    """Stringify a set/list of resolved addresses to a sorted list of strings."""
    return sorted([str(a) for a in (addrs or [])])


def dst_ports_to_ir(dst_ports: Optional[Iterable[Tuple[str, Tuple[Any, Any]]]]) -> List[Dict[str, Any]]:
    """Convert internal ``(op, (start, end))`` port tuples to IR ``{op,start,end}`` dicts."""
    out: List[Dict[str, Any]] = []
    for op, rng in (dst_ports or []):
        start, end = (rng[0], rng[1]) if rng else (None, None)
        out.append({"op": op, "start": start, "end": end})
    return out


def dst_ports_from_ir(ir_ports: Optional[Iterable[Dict[str, Any]]]) -> List[Tuple[str, Tuple[Any, Any]]]:
    """Inverse of :func:`dst_ports_to_ir` — rebuild ``(op, (start, end))`` tuples from IR."""
    out: List[Tuple[str, Tuple[Any, Any]]] = []
    for p in (ir_ports or []):
        out.append((p.get("op"), (p.get("start"), p.get("end"))))
    return out


def svc_to_ir(svc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize a parser-internal ``svc`` dict to the IR service shape.

    Works for both vendors: ASA populates ``service_group_at_proto`` and
    ``dst_service_objects``; FortiGate omits those keys, so ``.get`` yields the
    same ``None`` / ``[]`` the FortiGate exporter previously hardcoded.
    """
    svc = svc or {}
    return {
        "proto": svc.get("proto"),
        "service_group_at_proto": svc.get("service_group_at_proto"),
        "dst_ports": dst_ports_to_ir(svc.get("dst_ports", [])),
        "dst_service_groups": sorted(list(svc.get("dst_service_groups") or [])),
        "dst_service_objects": sorted(list(svc.get("dst_service_objects") or [])),
    }
