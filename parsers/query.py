# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Query/resolution layer over the versioned IR (`parsers.model.Device`).

This is the IR "spine": inspect/compare consumers read resolved rules, resolve
object/group tokens, and match services through :class:`DeviceQuery` instead of
reaching into vendor-specific parser internals. Because the IR already stores the
*result* of the parser's flatten step (addresses as strings, ports as
{op,start,end}), reconstructing the flattened-rule view is a faithful,
loss-free inverse — it does not re-tokenize raw config.

The resolution/matching logic mirrors the ASA parser (``resolve_network``,
``resolve_service_group``, ``service_matches``, ``evaluate_acl``) so results are
identical; parity is asserted in ``tests/test_device_query.py``.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any, Dict, List, Optional, Set, Union

from parsers import ir_normalize
from parsers.cisco.asa.utils import nets_overlap
from parsers.cisco.asa.acl_matching import _has_any_endpoint

__all__ = ["DeviceQuery"]

NetOrAddr = Union[ipaddress.IPv4Address, ipaddress.IPv4Network,
                  ipaddress.IPv6Address, ipaddress.IPv6Network]

_ANY4 = {"any", "any4", "any-ipv4"}
_ANY6 = {"any6", "any-ipv6"}
_PROTO_SET = {"ip", "tcp", "udp", "icmp"}


def _to_net(value: str) -> Optional[NetOrAddr]:
    """Parse an IR address string back into an ipaddress object."""
    try:
        if "/" in value:
            return ipaddress.ip_network(value, strict=False)
        return ipaddress.ip_address(value)
    except ValueError:
        try:
            return ipaddress.ip_network(value, strict=False)
        except ValueError:
            return None


def _port_from_token(tok: Optional[str], proto_hint: Optional[str] = None) -> Optional[int]:
    """Mirror of ASAConfig._port_from_token (numeric or service-name lookup)."""
    if not tok:
        return None
    if tok.isdigit():
        try:
            return int(tok)
        except ValueError:
            return None
    protos = (proto_hint,) if proto_hint in ("tcp", "udp") else ("tcp", "udp")
    for p in protos:
        try:
            return socket.getservbyname(tok, p)
        except OSError:
            continue
    return None


class DeviceQuery:
    """Resolution + rule-matching over an IR :class:`~parsers.model.Device`."""

    def __init__(self, device: Any):
        self.device = device
        self._objects: Dict[str, List[str]] = {o.name: list(o.literals) for o in device.objects}
        self._groups: Dict[str, Any] = {g.name: g for g in device.groups}
        self._service_groups: Dict[str, List[dict]] = {
            sg.name: list(sg.members) for sg in device.service_groups
        }
        self._net_cache: Dict[str, Set[NetOrAddr]] = {}
        self._svc_cache: Dict[str, List[dict]] = {}
        self._ip_to_objects: Optional[Dict[NetOrAddr, Set[str]]] = None
        self._membership: Optional[Dict[str, List[str]]] = None

    # ------------------------- address resolution -------------------------
    def resolve(self, token: Union[str, NetOrAddr], _visited: Optional[Set[str]] = None) -> Set[NetOrAddr]:
        """Resolve a name / IP / CIDR token to a set of addresses/networks."""
        if isinstance(token, (ipaddress.IPv4Address, ipaddress.IPv4Network,
                              ipaddress.IPv6Address, ipaddress.IPv6Network)):
            return {token}
        if not isinstance(token, str):
            return set()

        if _visited is None:
            cached = self._net_cache.get(token)
            if cached is not None:
                return set(cached)
            _visited = set()

        low = token.lower()
        if low in _ANY4:
            return {ipaddress.ip_network("0.0.0.0/0")}
        if low in _ANY6:
            try:
                return {ipaddress.ip_network("::/0")}
            except ValueError:
                return set()

        if token in self._objects:
            nets = {n for n in (_to_net(s) for s in self._objects[token]) if n is not None}
            self._net_cache[token] = set(nets)
            return set(nets)

        if token in self._groups:
            if token in _visited:
                return set()
            _visited.add(token)
            resolved: Set[NetOrAddr] = set()
            for m in self._groups[token].members:
                if m.kind in ("object", "group") and m.ref:
                    resolved.update(self.resolve(m.ref, _visited))
                elif m.kind == "literal" and m.literal:
                    n = _to_net(m.literal)
                    if n is not None:
                        resolved.add(n)
            _visited.discard(token)
            self._net_cache[token] = set(resolved)
            return set(resolved)

        n = _to_net(token)
        result = {n} if n is not None else set()
        self._net_cache[token] = set(result)
        return set(result)

    # ------------------------- service resolution -------------------------
    def resolve_service_group(self, name: str, _visited: Optional[Set[str]] = None) -> List[dict]:
        cached = self._svc_cache.get(name)
        if cached is not None:
            return [dict(s) for s in cached]
        if _visited is None:
            _visited = set()
        if name in _visited or name not in self._service_groups:
            return []
        _visited.add(name)
        out: List[dict] = []
        for m in self._service_groups.get(name, []):
            if not isinstance(m, dict):
                continue
            if "group" in m:
                out.extend(self.resolve_service_group(m["group"], _visited))
            elif "proto" in m or "object" in m:
                out.append(dict(m))
        _visited.discard(name)
        deduped: List[dict] = []
        for item in out:
            if item not in deduped:
                deduped.append(item)
        self._svc_cache[name] = [dict(s) for s in deduped]
        return [dict(s) for s in deduped]

    def _effective_protos(self, entry: dict) -> Set[str]:
        svc = entry.get("svc") or {}
        protos: Set[str] = set()
        if svc.get("proto") in _PROTO_SET:
            protos.add(svc["proto"])
        sg = svc.get("service_group_at_proto")
        if sg and sg.get("kind") == "object-group":
            for spec in self.resolve_service_group(sg.get("name")):
                if "proto" in spec:
                    protos.add(spec["proto"])
        if entry.get("proto") in _PROTO_SET:
            protos.add(entry["proto"])
        return protos or {"ip"}

    @staticmethod
    def _spec_to_range(spec: dict):
        op = spec.get("op")
        if not op:
            return (None, None)
        v1, v2 = spec.get("v1"), spec.get("v2")
        p1 = _port_from_token(v1, spec.get("proto")) if v1 else None
        p2 = _port_from_token(v2, spec.get("proto")) if v2 else None
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

    def _dst_ports_from_entry(self, entry: dict):
        svc = entry.get("svc") or {}
        ports = []
        for op, rng in svc.get("dst_ports", []):
            for proto in self._effective_protos(entry):
                ports.append((proto, op, rng))
        for group_name in svc.get("dst_service_groups", set()):
            for spec in self.resolve_service_group(group_name):
                rng = self._spec_to_range(spec)
                if rng is not None:
                    ports.append((spec["proto"], spec.get("op") or "eq", rng))
        sg = svc.get("service_group_at_proto")
        if sg and sg.get("kind") == "object-group":
            for spec in self.resolve_service_group(sg.get("name")):
                rng = self._spec_to_range(spec)
                if rng is not None:
                    ports.append((spec["proto"], spec.get("op") or "eq", rng))
        return ports

    def _service_matches(self, entry: dict, svc_filter: Optional[dict]) -> bool:
        if not svc_filter:
            return True
        want_proto = svc_filter.get("proto")
        want_ports = svc_filter.get("dports") or set()
        entry_protos = self._effective_protos(entry)
        if want_proto and want_proto not in entry_protos and "ip" not in entry_protos:
            return False
        if not want_ports:
            return True
        port_specs = self._dst_ports_from_entry(entry)
        if not port_specs:
            return True
        for port in want_ports:
            for eproto, _op, (start, end) in port_specs:
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

    # ------------------------- flattened rules -------------------------
    def flat_rules(self) -> List[dict]:
        """Reconstruct the parser's flattened-ACL dict view from the IR."""
        out: List[dict] = []
        for acl in self.device.acls:
            for e in acl.entries:
                src = {n for n in (_to_net(s) for s in e.src) if n is not None}
                dst = {n for n in (_to_net(s) for s in e.dst) if n is not None}
                svc_ir = e.svc or {}
                dst_ports = ir_normalize.dst_ports_from_ir(svc_ir.get("dst_ports"))
                svc = {
                    "proto": svc_ir.get("proto"),
                    "service_group_at_proto": svc_ir.get("service_group_at_proto"),
                    "dst_ports": dst_ports,
                    "dst_ops": {op for op, _ in dst_ports},
                    "dst_service_groups": set(svc_ir.get("dst_service_groups") or []),
                    "dst_service_objects": set(svc_ir.get("dst_service_objects") or []),
                }
                out.append({
                    "acl": e.acl,
                    "action": e.action,
                    "proto": e.proto,
                    "src": src,
                    "dst": dst,
                    "svc": svc,
                    "binding": e.binding,
                    "bound_to": e.bound_to,
                    "direction": e.direction,
                    "raw": e.raw,
                    "line": e.line,
                })
        return out

    def rules_affecting(
        self,
        target_nets: Set[NetOrAddr],
        service_filter: Optional[dict] = None,
        ignore_any: bool = True,
    ) -> List[dict]:
        """Mirror of ASA evaluate_acl: rules whose src or dst overlaps the target."""
        out: List[dict] = []
        for entry in self.flat_rules():
            if ignore_any and _has_any_endpoint(entry):
                continue
            if nets_overlap(entry["src"], target_nets) or nets_overlap(entry["dst"], target_nets):
                if service_filter and not self._service_matches(entry, service_filter):
                    continue
                out.append(entry)
        return out

    # ------------------------- reverse lookups -------------------------
    def group_membership(self) -> Dict[str, List[str]]:
        """Reverse lookup: object/group name → sorted parent group names."""
        if self._membership is None:
            temp: Dict[str, Set[str]] = {}
            for g in self.device.groups:
                for m in g.members:
                    if m.kind in ("object", "group") and m.ref:
                        temp.setdefault(m.ref, set()).add(g.name)
            self._membership = {k: sorted(v) for k, v in temp.items()}
        return {k: list(v) for k, v in self._membership.items()}

    def _reverse_index(self) -> Dict[NetOrAddr, Set[str]]:
        if self._ip_to_objects is None:
            idx: Dict[NetOrAddr, Set[str]] = {}
            for name, literals in self._objects.items():
                for s in literals:
                    n = _to_net(s)
                    if n is not None:
                        idx.setdefault(n, set()).add(name)
            self._ip_to_objects = idx
        return self._ip_to_objects

    def alias_objects(
        self,
        target: Union[str, NetOrAddr],
        target_nets: Set[NetOrAddr],
    ) -> Dict[NetOrAddr, Set[str]]:
        """Other object names resolving to the same address(es) as ``target``."""
        exclude: Set[str] = {target} if isinstance(target, str) and target in self._objects else set()
        idx = self._reverse_index()
        aliases: Dict[NetOrAddr, Set[str]] = {}
        for n in target_nets:
            if not isinstance(n, (ipaddress.IPv4Address, ipaddress.IPv4Network,
                                  ipaddress.IPv6Address, ipaddress.IPv6Network)):
                continue
            names = set(idx.get(n, set())) - exclude
            if names:
                aliases[n] = names
        return aliases
