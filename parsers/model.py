"""Versioned Intermediate Representation (IR) for firewall configs.

This module defines stable, JSON‑friendly dataclasses that vendors map to.
Keep shapes conservative and additive to ease cross‑vendor comparison and
remapping (e.g., ASA -> FortiOS 7.4).

Guidelines:
- Use only built‑in types at the boundaries (str/int/bool/float/list/dict).
- Prefer names over direct object references to keep the IR portable.
- Provide a canonical to_dict() that normalizes sets and non‑JSON types.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, is_dataclass
from typing import Any, Dict, List, Optional

IR_VERSION = "1.0"


def _jsonable(obj: Any):
    """Recursively convert dataclasses and non‑JSON types to JSON‑friendly values."""
    if is_dataclass(obj):
        return _jsonable(asdict(obj))
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            out[str(k)] = _jsonable(v)
        return out
    if isinstance(obj, (list, tuple, set)):
        # Sort sets by string form for determinism
        if isinstance(obj, set):
            return [_jsonable(x) for x in sorted(list(obj), key=lambda x: str(x))]
        return [_jsonable(x) for x in obj]
    # ipaddress and others stringify cleanly
    try:
        import ipaddress  # local import to avoid hard dependency at import time
        if isinstance(obj, (ipaddress.IPv4Address, ipaddress.IPv4Network, ipaddress.IPv6Address, ipaddress.IPv6Network)):
            return str(obj)
    except Exception:
        pass
    return obj


@dataclass
class Interface:
    name: str
    physical: Optional[str] = None
    ipv4: Optional[str] = None
    security_level: Optional[int] = None


@dataclass
class Object:
    name: str
    literals: List[str] = field(default_factory=list)  # IPv4Address/IPv4Network strings


@dataclass
class GroupMember:
    kind: str  # 'object' | 'group' | 'literal'
    ref: Optional[str] = None
    literal: Optional[str] = None


@dataclass
class Group:
    name: str
    members: List[GroupMember] = field(default_factory=list)


@dataclass
class ServiceGroup:
    name: str
    # members can be {'group': name}, {'object': name}, or {'proto', 'op', 'v1', 'v2'}
    members: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ACLEntry:
    action: str
    proto: Optional[str]
    src: List[str]
    dst: List[str]
    svc: Dict[str, Any]
    raw: str
    acl: Optional[str] = None
    bound_to: Optional[str] = None  # interface name if bound
    binding: Optional[Dict[str, Any]] = None


@dataclass
class ACL:
    name: str
    bound_to: Optional[str]
    entries: List[ACLEntry] = field(default_factory=list)
    binding: Optional[Dict[str, Any]] = None


@dataclass
class NAT:
    kind: str  # 'auto' | 'manual'
    src_if: Optional[str] = None
    dst_if: Optional[str] = None
    section: Optional[int] = None
    detail: Dict[str, Any] = field(default_factory=dict)
    raw: Optional[str] = None


@dataclass
class Route:
    dest: str
    via: str
    interface: Optional[str] = None


@dataclass
class Device:
    vendor: str
    os: str
    version: str
    name: Optional[str] = None
    ir_version: str = IR_VERSION
    interfaces: List[Interface] = field(default_factory=list)
    objects: List[Object] = field(default_factory=list)
    groups: List[Group] = field(default_factory=list)
    service_groups: List[ServiceGroup] = field(default_factory=list)
    acls: List[ACL] = field(default_factory=list)
    nats: List[NAT] = field(default_factory=list)
    routes: List[Route] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _jsonable(self)
