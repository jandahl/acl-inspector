"""Core Cisco ASA parsing primitives.

This module encapsulates parsing of Cisco ASA configuration constructs relevant
to ACL impact analysis. It resolves network objects and object-groups into
concrete IPv4 primitives, tokenizes ACL lines into a normalized shape, and
exposes helpers consumed by :mod:`parsers.cisco.asa.inspect` and
:mod:`parsers.cisco.asa.path`.

Design choices
--------------
- Keep the normalized output close to the ASA lines: we preserve the raw ACL
  line as a stable identity while also exposing a structured view.
- Parse service/port information in two places:
  1) The protocol position of an ACL may be an ASA service object-group.
  2) Trailing tokens after the destination endpoint (eq/range/object-group).
- Keep resolution of named service objects ("service-object object NAME") as a
  future enhancement: we record references and exclude them from numeric-port
  filtering for now.

The normalized entries produced here are intentionally compatible with the
shared modeling approach described in parsers.base. This module predates a full
refactor into those dataclasses but can be adapted with minimal changes.
"""


from __future__ import annotations

import ipaddress
import re
import socket
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

from .services import entry_effective_protos, spec_to_range_tuple, dst_ports_from_entry, service_matches
from .nat import (
    nat_result_template,
    value_matches_ip,
    map_value_to_ip,
    apply_nat_rule_outbound,
    apply_nat_rule_inbound,
    resolve_nat_interface,
    match_nat_interface,
    evaluate_nat,
)

__all__ = [
    "ASAConfig",
    "to_ip_network",
    "nets_overlap",
    "entry_effective_protos",
    "_entry_effective_protos",
    "spec_to_range_tuple",
    "_spec_to_range_tuple",
    "dst_ports_from_entry",
    "_dst_ports_from_entry",
    "service_matches",
    "_service_matches",
    "_has_any_endpoint",
    "_entry_summary",
    "_pick_preferred_address",
    "value_matches_ip",
    "_value_matches_ip",
    "map_value_to_ip",
    "_map_value_to_ip",
    "nat_result_template",
    "_nat_result_template",
    "apply_nat_rule_outbound",
    "_apply_nat_rule_outbound",
    "apply_nat_rule_inbound",
    "_apply_nat_rule_inbound",
    "resolve_nat_interface",
    "_resolve_nat_interface",
    "match_nat_interface",
    "_match_nat_interface",
    "evaluate_nat",
    "_evaluate_nat",
    "_binding_applicable",
    "_evaluate_acl_flow",
]

_entry_effective_protos = entry_effective_protos
_spec_to_range_tuple = spec_to_range_tuple
_dst_ports_from_entry = dst_ports_from_entry
_service_matches = service_matches
_nat_result_template = nat_result_template
_value_matches_ip = value_matches_ip
_map_value_to_ip = map_value_to_ip
_apply_nat_rule_outbound = apply_nat_rule_outbound
_apply_nat_rule_inbound = apply_nat_rule_inbound
_resolve_nat_interface = resolve_nat_interface
_match_nat_interface = match_nat_interface
_evaluate_nat = evaluate_nat

# IR model for cross-vendor mapping
try:
    from parsers import model as ir
except Exception:
    ir = None  # type: ignore


# ------------------- Regex and tokenization helpers -------------------

re_object = re.compile(r"^object(?: network)?\s+(?P<name>\S+)", re.IGNORECASE)
re_object_network_host = re.compile(r"^\s*host\s+(?P<ip>\S+)", re.IGNORECASE)
re_object_network_subnet = re.compile(r"^\s*(?:subnet|network)\s+(?P<ip>\S+)\s+(?P<mask>\S+)", re.IGNORECASE)

re_object_group = re.compile(r"^object-group\s+(?P<type>network|service)\s+(?P<name>\S+)", re.IGNORECASE)
re_group_network_object = re.compile(r"^\s*network-object\s+object\s+(?P<name>\S+)", re.IGNORECASE)
re_group_network_host = re.compile(r"^\s*network-object\s+host\s+(?P<ip>\S+)", re.IGNORECASE)
re_group_network_subnet = re.compile(r"^\s*network-object\s+(?!object\b)(?!host\b)(?P<ip>\S+)\s+(?P<mask>\S+)", re.IGNORECASE)
re_group_network_groupobj = re.compile(r"^\s*group-object\s+(?P<name>\S+)", re.IGNORECASE)

re_acl = re.compile(
    r"^access-list\s+(?P<name>\S+)\s+extended\s+(?P<action>permit|deny)\s+(?P<rest>.*)$",
    re.IGNORECASE,
)
re_tokenized = re.compile(r"\S+")


def to_ip_network(ip: str, mask: Optional[str] = None) -> Union[ipaddress.IPv4Address, ipaddress.IPv4Network]:
    if mask is not None:
        return ipaddress.ip_network(f"{ip}/{mask}", strict=False)
    if "/" in ip:
        return ipaddress.ip_network(ip, strict=False)
    return ipaddress.ip_address(ip)


class ASAConfig:
    def __init__(self, text: str) -> None:
        self.lines = [line.rstrip() for line in text.splitlines()]
        self.network_objects: Dict[
            str, Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]
        ] = {}
        self.network_object_literals: Dict[str, Set[str]] = defaultdict(set)
        self.network_object_groups: Dict[
            str, List[Union[dict, ipaddress.IPv4Address, ipaddress.IPv4Network]]
        ] = {}
        self.network_object_group_literals: Dict[str, Set[str]] = defaultdict(set)
        self.acls: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        # Interfaces, ACL bindings, and NAT rules (initial subset)
        self.interfaces: Dict[str, dict] = {}
        self.acl_bindings: Dict[str, Dict[str, Optional[str]]] = {}
        self.nat_rules: List[dict] = []
        self._network_cache: Dict[str, Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]] = {}
        self._network_in_progress: Dict[
            str, Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]
        ] = {}
        self._service_group_cache: Dict[str, Tuple[dict, ...]] = {}
        self.parse()
        self._build_reverse_indexes()

    # ------------------- IR export -------------------
    def to_ir(self, device_name: Optional[str] = None) -> "ir.Device":
        """Map the parsed ASA config to the common IR.Device shape.

        This preserves both raw and normalized views of ACLs, includes basic
        interface context, network objects and groups, service groups, and NAT
        rules parsed by this module. Routes are not parsed yet.
        """
        if ir is None:
            raise RuntimeError("IR module not available")
        # Version detection best-effort from banner lines
        version = 'unknown'
        for ln in self.lines:
            m = re.search(r"ASA\s+Version\s+([^\s]+)", ln, flags=re.IGNORECASE)
            if m:
                version = m.group(1)
                break
            m2 = re.search(r"Adaptive Security Appliance Software\s+Version\s+([^\s]+)", ln, flags=re.IGNORECASE)
            if m2:
                version = m2.group(1)
                break
        # Interfaces
        interfaces: List[ir.Interface] = []
        for name, meta in self.interfaces.items():
            ipv4 = meta.get('ipv4')
            interfaces.append(ir.Interface(
                name=name,
                physical=meta.get('phys'),
                ipv4=str(ipv4) if ipv4 else None,
                security_level=meta.get('security_level'),
            ))
        # Objects
        objects: List[ir.Object] = []
        for name, nets in self.network_objects.items():
            literals = []
            for n in nets:
                try:
                    literals.append(str(n))
                except Exception:
                    pass
            objects.append(ir.Object(name=name, literals=sorted(literals)))
        # Groups (network)
        groups: List[ir.Group] = []
        for name, members in self.network_object_groups.items():
            mlist: List[ir.GroupMember] = []
            for m in members:
                if isinstance(m, dict):
                    if 'group-object' in m:
                        mlist.append(ir.GroupMember(kind='group', ref=m['group-object']))
                    elif 'object' in m:
                        mlist.append(ir.GroupMember(kind='object', ref=m['object']))
                else:
                    mlist.append(ir.GroupMember(kind='literal', literal=str(m)))
            groups.append(ir.Group(name=name, members=mlist))
        # Service groups
        svc_groups: List[ir.ServiceGroup] = []
        if hasattr(self, 'service_object_groups'):
            for name, members in getattr(self, 'service_object_groups').items():
                out: List[dict] = []
                for m in members:
                    if isinstance(m, dict) and 'group-object' in m:
                        out.append({'group': m['group-object']})
                    elif isinstance(m, dict) and 'object' in m:
                        out.append({'object': m['object']})
                    elif isinstance(m, dict) and 'proto' in m:
                        spec = {'proto': m.get('proto')}
                        if m.get('op'):
                            spec.update({'op': m.get('op'), 'v1': m.get('v1'), 'v2': m.get('v2')})
                        out.append(spec)
                svc_groups.append(ir.ServiceGroup(name=name, members=out))
        # ACLs and entries (flattened)
        flattened = self.flatten_acl()
        acl_map: Dict[str, List[ir.ACLEntry]] = {}
        for e in flattened:
            src = sorted([str(s) for s in e.get('src', [])])
            dst = sorted([str(d) for d in e.get('dst', [])])
            svc = e.get('svc') or {}
            # normalize sets to lists for IR
            svc_norm = {
                'proto': svc.get('proto'),
                'service_group_at_proto': svc.get('service_group_at_proto'),
                'dst_ports': [
                    {'op': op, 'start': rng[0], 'end': rng[1]}
                    for (op, rng) in svc.get('dst_ports', [])
                ],
                'dst_service_groups': sorted(list(svc.get('dst_service_groups') or [])),
                'dst_service_objects': sorted(list(svc.get('dst_service_objects') or [])),
            }
            acl_name = e.get('acl')
            binding = self.acl_bindings.get(acl_name) if acl_name else None
            bound_to = self._binding_target_value(binding)
            entry = ir.ACLEntry(
                action=e.get('action'),
                proto=e.get('proto'),
                src=src,
                dst=dst,
                svc=svc_norm,
                raw=e.get('raw'),
                acl=acl_name,
                bound_to=bound_to,
                binding=binding,
            )
            acl_map.setdefault(acl_name or 'UNNAMED', []).append(entry)
        ir_acls: List[ir.ACL] = []
        for name, entries in acl_map.items():
            binding = self.acl_bindings.get(name)
            bound_to = self._binding_target_value(binding)
            ir_acls.append(ir.ACL(name=name, bound_to=bound_to, entries=entries, binding=binding))
        # NAT rules
        ir_nats: List[ir.NAT] = []
        for idx, r in enumerate(self.nat_rules):
            kind = r.get('type') or 'manual'
            detail: Dict[str, Union[str, int, dict, None]] = {}
            section = r.get('section')
            sequence = r.get('sequence')
            precedence = self._nat_precedence_key(section if section is not None else (2 if kind == 'auto' else 1), sequence, idx)
            if r.get('type') == 'auto':
                detail = {
                    'real_object': r.get('real_object'),
                    'kind': r.get('kind'),
                    'mapped': r.get('mapped'),
                    'service': r.get('service'),
                    'sequence': sequence,
                    'precedence': precedence,
                }
            else:
                detail = {
                    'source': r.get('source'),
                    'destination': r.get('destination'),
                    'service': r.get('service'),
                    'sequence': sequence,
                    'precedence': precedence,
                }
            ir_nats.append(ir.NAT(
                kind=kind,
                src_if=r.get('src_if'),
                dst_if=r.get('dst_if'),
                section=section,
                detail=detail,
                raw=r.get('raw')
            ))
        dev = ir.Device(
            vendor='asa', os='ASA', version=version, name=device_name or None,
            interfaces=interfaces,
            objects=objects,
            groups=groups,
            service_groups=svc_groups,
            acls=ir_acls,
            nats=ir_nats,
            routes=[],
        )
        return dev

    def _consume_endpoint(self, tokens: List[str]) -> Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]:
        nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]] = set()
        if not tokens:
            return nets
        tok = tokens.pop(0)
        low = tok.lower()

        if low == 'host':
            if tokens:
                nets.add(to_ip_network(tokens.pop(0)))
            return nets
        if low in ('object', 'object-group'):
            if tokens:
                nets.update(self.resolve_network(tokens.pop(0)))
            return nets
        if low in ('any', 'any4', 'any-ipv4'):
            nets.update(self.resolve_network('any4'))
            return nets
        if low in ('any6', 'any-ipv6'):
            nets.update(self.resolve_network('any6'))
            return nets

        mask = None
        if tokens and '.' in tokens[0]:
            mask = tokens.pop(0)
        nets.add(to_ip_network(tok, mask))
        return nets

    def _port_from_token(self, tok: str, proto_hint: Optional[str] = None) -> Optional[int]:
        if tok.isdigit():
            try:
                return int(tok)
            except Exception:
                return None
        if proto_hint in ("tcp", "udp"):
            try:
                return socket.getservbyname(tok, proto_hint)
            except Exception:
                return None
        for p in ("tcp", "udp"):
            try:
                return socket.getservbyname(tok, p)
            except Exception:
                continue
        return None

    def _consume_service_tail(self, tokens: List[str], proto_hint: Optional[str]) -> dict:
        dst_ports: List[Tuple[str, Tuple[Optional[int], Optional[int]]]] = []
        dst_ops: Set[str] = set()
        dst_service_groups: Set[str] = set()
        dst_service_objects: Set[str] = set()

        while tokens:
            t = tokens[0].lower()
            if t in {"eq", "lt", "gt", "neq"}:
                tokens.pop(0)
                if not tokens:
                    break
                v = tokens.pop(0)
                port = self._port_from_token(v, proto_hint)
                if port is not None:
                    dst_ports.append((t, (port, port)))
                    dst_ops.add(t)
                else:
                    dst_ports.append((t, (None, None)))
                    dst_ops.add(t)
            elif t == "range":
                tokens.pop(0)
                if len(tokens) < 2:
                    break
                v1 = tokens.pop(0)
                v2 = tokens.pop(0)
                p1 = self._port_from_token(v1, proto_hint)
                p2 = self._port_from_token(v2, proto_hint)
                dst_ports.append(("range", (p1, p2)))
                dst_ops.add("range")
            elif t == "object-group" and len(tokens) >= 2:
                tokens.pop(0)
                dst_service_groups.add(tokens.pop(0))
            elif t == "object" and len(tokens) >= 2:
                tokens.pop(0)
                dst_service_objects.add(tokens.pop(0))
            else:
                break

        return {
            "dst_ports": dst_ports,
            "dst_ops": dst_ops,
            "dst_service_groups": dst_service_groups,
            "dst_service_objects": dst_service_objects,
        }

    def parse(self) -> None:
        i = 0
        L = len(self.lines)
        while i < L:
            line = self.lines[i]
            # Interfaces
            if line.startswith('interface '):
                phys = line.split(None, 1)[1].strip()
                nameif = None
                ipv4 = None
                sec = None
                i += 1
                while i < L and self.lines[i].startswith(' '):
                    ln = self.lines[i].strip()
                    if ln.lower().startswith('nameif '):
                        nameif = ln.split(None, 1)[1].strip()
                    elif ln.lower().startswith('ip address '):
                        parts = ln.split()
                        if len(parts) >= 3:
                            try:
                                ipv4 = to_ip_network(parts[2], parts[3]) if len(parts) >= 4 else to_ip_network(parts[2])
                            except Exception:
                                pass
                    elif ln.lower().startswith('security-level '):
                        try:
                            sec = int(ln.split()[-1])
                        except Exception:
                            pass
                    i += 1
                key = nameif or phys
                self.interfaces[key] = {'phys': phys, 'nameif': nameif, 'ipv4': ipv4, 'security_level': sec}
                continue

            # ACL to interface binding
            m_ag = re.match(r"^access-group\s+(?P<acl>\S+)\s+(?P<body>.+)$", line, re.IGNORECASE)
            if m_ag:
                acl_name = m_ag.group('acl')
                body = m_ag.group('body')
                self.acl_bindings[acl_name] = self._parse_access_group_binding(body, line)
                i += 1
                continue
            m = re_object.match(line)
            if m:
                name = m.group('name')
                nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]] = set()
                i += 1
                while i < L and self.lines[i].startswith(' '):
                    current_line = self.lines[i]
                    lm = re_object_network_host.match(current_line)
                    if lm:
                        value = lm.group('ip')
                        try:
                            nets.add(to_ip_network(value))
                        except ValueError:
                            self.network_object_literals[name].add(current_line.strip())
                    else:
                        lm2 = re_object_network_subnet.match(current_line)
                        if lm2:
                            try:
                                nets.add(to_ip_network(lm2.group('ip'), lm2.group('mask')))
                            except ValueError:
                                self.network_object_literals[name].add(current_line.strip())
                        else:
                            # Auto NAT (object NAT) inside object network block
                            mnat = re.match(r"^\s*nat\s*\((?P<src_if>[^,]+),(?P<dst_if>[^\)]+)\)\s+(?P<rest>.+)$", current_line, re.IGNORECASE)
                            if mnat:
                                src_if = mnat.group('src_if').strip()
                                dst_if = mnat.group('dst_if').strip()
                                rest = mnat.group('rest').strip()
                                mm = re.match(r"^(?P<kind>static|dynamic)\s+(?P<target>\S+)", rest, re.IGNORECASE)
                                kind = mm.group('kind').lower() if mm else None
                                target = mm.group('target') if mm else None
                                self.nat_rules.append({
                                    'type': 'auto', 'section': 2,
                                    'src_if': src_if, 'dst_if': dst_if,
                                    'real_object': name,
                                    'kind': kind,
                                    'mapped': target,
                                    'service': None,
                                    'sequence': None,
                                    'order_keyword': None,
                                    'raw': self.lines[i].strip(),
                                })
                    i += 1
                self.network_objects[name] = nets
                continue

            mg = re_object_group.match(line)
            if mg:
                typ = mg.group('type').lower()
                name = mg.group('name')
                members = []
                i += 1
                while i < L and self.lines[i].startswith(' '):
                    ln = self.lines[i]
                    if typ == 'network':
                        m_host = re_group_network_host.match(ln)
                        m_obj = re_group_network_object.match(ln)
                        m_subnet = re_group_network_subnet.match(ln)
                        m_group = re_group_network_groupobj.match(ln)
                        if m_host:
                            host_val = m_host.group('ip')
                            try:
                                members.append(to_ip_network(host_val))
                            except ValueError:
                                self.network_object_group_literals[name].add(ln.strip())
                        elif m_subnet:
                            try:
                                members.append(to_ip_network(m_subnet.group('ip'), m_subnet.group('mask')))
                            except ValueError:
                                self.network_object_group_literals[name].add(ln.strip())
                        elif m_obj:
                            members.append({'object': m_obj.group('name')})
                        elif m_group:
                            members.append({'group-object': m_group.group('name')})
                    elif typ == 'service':
                        m_group = re_group_network_groupobj.match(ln)
                        if m_group:
                            members.append({'group-object': m_group.group('name')})
                        else:
                            msvc = re.match(r"^\s*service-object\s+(tcp|udp|icmp|ip)(?:\s+(eq|lt|gt|neq|range)\s+(\S+)(?:\s+(\S+))?)?", ln, re.IGNORECASE)
                            if msvc:
                                proto = msvc.group(1).lower()
                                op = (msvc.group(2) or '').lower()
                                v1 = msvc.group(3)
                                v2 = msvc.group(4)
                                spec = {"proto": proto}
                                if op in {"eq", "lt", "gt", "neq", "range"}:
                                    spec.update({"op": op, "v1": v1, "v2": v2})
                                members.append(spec)
                            else:
                                mobj = re.match(r"^\s*service-object\s+object\s+(\S+)", ln, re.IGNORECASE)
                                if mobj:
                                    members.append({"object": mobj.group(1)})
                    i += 1
                if typ == 'network':
                    self.network_object_groups[name] = members
                elif typ == 'service':
                    if not hasattr(self, 'service_object_groups'):
                        self.service_object_groups = {}
                    self.service_object_groups[name] = members
                continue

            macl = re_acl.match(line)
            if macl:
                self.acls[macl.group('name')].append((line, i + 1))
                i += 1
                continue
            # Manual NAT (common forms)
            mnat2 = re.match(r"^nat\s*\((?P<src_if>[^,]+),(?P<dst_if>[^\)]+)\)\s*(?P<rest>.+)$", line, re.IGNORECASE)
            if mnat2:
                src_if = mnat2.group('src_if').strip()
                dst_if = mnat2.group('dst_if').strip()
                rest = mnat2.group('rest').strip()
                section = 1
                sequence: Optional[int] = None
                order_kw: Optional[str] = None
                m_seq = re.match(r"^(?P<num>\d+)\s+(?P<tail>.+)$", rest)
                if m_seq:
                    sequence = int(m_seq.group('num'))
                    rest = m_seq.group('tail').strip()
                lower_rest = rest.lower()
                if lower_rest.startswith('after-auto'):
                    order_kw = 'after-auto'
                    parts = rest.split(None, 1)
                    rest = parts[1].strip() if len(parts) > 1 else ''
                elif lower_rest.startswith('before-auto'):
                    order_kw = 'before-auto'
                    parts = rest.split(None, 1)
                    rest = parts[1].strip() if len(parts) > 1 else ''
                if order_kw == 'after-auto':
                    section = 3
                elif order_kw == 'before-auto':
                    section = 1
                msrc = re.match(r"^source\s+(static|dynamic)\s+(\S+)\s+(\S+)(?P<tail>.*)$", rest, re.IGNORECASE)
                if msrc:
                    s_kind = msrc.group(1).lower()
                    s_real = msrc.group(2)
                    s_map = msrc.group(3)
                    tail = (msrc.group('tail') or '').strip()
                    dest_data = None
                    service_data = None
                    if tail.lower().startswith('destination '):
                        mdest = re.match(r"^destination\s+(static|dynamic)\s+(\S+)\s+(\S+)(?P<tail>.*)$", tail, re.IGNORECASE)
                        if mdest:
                            d_kind = mdest.group(1).lower()
                            d_real = mdest.group(2)
                            d_map = mdest.group(3)
                            dest_data = {'kind': d_kind, 'real': d_real, 'mapped': d_map}
                            tail = (mdest.group('tail') or '').strip()
                    if tail.lower().startswith('service '):
                        service_data, tail = self._parse_nat_service_clause(tail)
                    self.nat_rules.append({
                        'type': 'manual', 'section': section,
                        'src_if': src_if, 'dst_if': dst_if,
                        'source': {'kind': s_kind, 'real': s_real, 'mapped': s_map},
                        'destination': dest_data,
                        'service': service_data,
                        'sequence': sequence,
                        'order_keyword': order_kw,
                        'extra': tail if tail else None,
                        'raw': line.strip(),
                    })
                    i += 1
                    continue
                mdyn = re.match(r"^(?:source\s+)?dynamic\s+(\S+)\s+interface", rest, re.IGNORECASE)
                if mdyn:
                    self.nat_rules.append({
                        'type': 'manual', 'section': section,
                        'src_if': src_if, 'dst_if': dst_if,
                        'source': {'kind': 'dynamic', 'real': mdyn.group(1), 'mapped': 'interface'},
                        'destination': None,
                        'service': None,
                        'sequence': sequence,
                        'order_keyword': order_kw,
                        'raw': line.strip(),
                    })
                    i += 1
                    continue
            i += 1

    def _build_reverse_indexes(self) -> None:
        ip_to_objects: Dict[Union[ipaddress.IPv4Address, ipaddress.IPv4Network], Set[str]] = defaultdict(set)
        for name, nets in self.network_objects.items():
            for n in nets:
                if isinstance(n, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                    ip_to_objects[n].add(name)
        self.ip_to_objects = dict(ip_to_objects)

        interface_map: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
        control_plane_map: Dict[str, List[str]] = defaultdict(list)
        scope_map: Dict[str, List[str]] = defaultdict(list)
        global_acls: List[str] = []

        for acl_name, binding in self.acl_bindings.items():
            if not binding:
                continue
            scope = (binding.get("scope") or "interface").lower()
            direction_key = (binding.get("direction") or "any").lower()
            interface_name = binding.get("interface")
            if scope == "global":
                global_acls.append(acl_name)
                continue
            if scope == "control-plane":
                control_plane_map[direction_key].append(acl_name)
                continue
            if interface_name:
                interface_map[interface_name][direction_key].append(acl_name)
            else:
                scope_map[scope].append(acl_name)

        def _sorted_unique(values: List[str]) -> List[str]:
            return sorted({v for v in values if v}, key=lambda item: item.lower())

        interfaces_section: Dict[str, Dict[str, List[str]]] = {}
        for iface, dir_map in interface_map.items():
            interfaces_section[iface] = {}
            for dir_key, names in dir_map.items():
                interfaces_section[iface][dir_key] = _sorted_unique(names)
            if "any" not in interfaces_section[iface]:
                interfaces_section[iface]["any"] = []

        control_plane_section = {dir_key: _sorted_unique(names) for dir_key, names in control_plane_map.items()}
        other_scopes_section = {scope: _sorted_unique(names) for scope, names in scope_map.items()}
        global_section = _sorted_unique(global_acls)

        self.acl_interface_map = {
            "interfaces": interfaces_section,
            "control_plane": control_plane_section,
            "global": global_section,
            "other_scopes": other_scopes_section,
        }

        lookup: Dict[Tuple[str, str], List[str]] = {}
        for iface, dir_map in interfaces_section.items():
            for dir_key, names in dir_map.items():
                lookup[(iface.lower(), dir_key.lower())] = names
        self._acl_interface_lookup = lookup
        self._global_acl_lookup = global_section
        self._control_plane_lookup = {dir_key.lower(): names for dir_key, names in control_plane_section.items()}
        self._other_scope_lookup = {scope.lower(): names for scope, names in other_scopes_section.items()}

    def acls_for_interface(self, interface: Optional[str], direction: Optional[str] = None) -> List[str]:
        if not interface:
            return []
        lookup = getattr(self, "_acl_interface_lookup", {})
        iface_key = interface.lower()
        dir_key = (direction or "any").lower()
        names = lookup.get((iface_key, dir_key))
        if names is None and dir_key != "any":
            names = lookup.get((iface_key, "any"))
        return list(names) if names else []

    def acls_for_global(self) -> List[str]:
        return list(getattr(self, "_global_acl_lookup", []))

    def acls_for_control_plane(self, direction: Optional[str] = None) -> List[str]:
        lookup = getattr(self, "_control_plane_lookup", {})
        if direction:
            names = lookup.get(direction.lower())
            if names:
                return list(names)
        combined: List[str] = []
        for names in lookup.values():
            combined.extend(names)
        return sorted({name for name in combined}, key=lambda item: item.lower())

    def interface_for_ip(self, ip: ipaddress.IPv4Address) -> Optional[str]:
        best_name: Optional[str] = None
        best_prefix = -1
        for name, meta in self.interfaces.items():
            net = meta.get('ipv4')
            if isinstance(net, ipaddress.IPv4Network) and ip in net:
                if net.prefixlen > best_prefix:
                    best_prefix = net.prefixlen
                    best_name = name
        return best_name

    def security_level_for_interface(self, interface: Optional[str]) -> Optional[int]:
        if not interface:
            return None
        meta = self.interfaces.get(interface)
        if not meta:
            return None
        return meta.get('security_level')

    def _parse_access_group_binding(self, body: str, line: str) -> Dict[str, Optional[str]]:
        binding: Dict[str, Optional[str]] = {
            'scope': 'interface',
            'direction': None,
            'interface': None,
            'raw': line.strip(),
        }
        tokens = body.strip().split()
        if not tokens:
            return binding
        first = tokens[0].lower()
        if first == 'global':
            binding['scope'] = 'global'
            binding['direction'] = 'global'
            return binding
        if first == 'control-plane':
            binding['scope'] = 'control-plane'
            if len(tokens) >= 4 and tokens[1].lower() in ('in', 'out') and tokens[2].lower() == 'interface':
                binding['direction'] = tokens[1].lower()
                binding['interface'] = tokens[3]
            return binding
        if first in ('in', 'out'):
            binding['direction'] = first
            if len(tokens) >= 3 and tokens[1].lower() == 'interface':
                binding['interface'] = tokens[2]
            elif len(tokens) >= 2:
                binding['interface'] = tokens[1]
            return binding
        if first == 'interface' and len(tokens) >= 2:
            binding['interface'] = tokens[1]
            return binding
        # Fallback: preserve first token as scope and best-effort interface capture
        binding['scope'] = first
        if len(tokens) >= 3 and tokens[1].lower() == 'interface':
            binding['direction'] = tokens[0].lower()
            binding['interface'] = tokens[2]
        elif len(tokens) >= 2:
            binding['interface'] = tokens[1]
        return binding

    def _binding_target_value(self, binding: Optional[Dict[str, Optional[str]]]) -> Optional[str]:
        if not binding:
            return None
        scope = (binding.get('scope') or '').lower()
        interface = binding.get('interface')
        if scope == 'interface' and interface:
            return interface
        if scope == 'global':
            return 'global'
        if interface:
            return interface
        return binding.get('scope')

    def _parse_nat_service_clause(self, clause: str) -> Tuple[Optional[dict], str]:
        text = clause.strip()
        if not text.lower().startswith('service '):
            return None, text
        tokens = text.split()
        idx = 1  # skip 'service'
        try:
            real_proto = tokens[idx].lower()
            idx += 1
            real_dir = tokens[idx].lower()
            idx += 1
            real_op = tokens[idx].lower()
            idx += 1
            real_val = tokens[idx]
            idx += 1
        except IndexError:
            return None, text
        real_val2 = None
        if real_op == 'range':
            if idx >= len(tokens):
                return None, text
            real_val2 = tokens[idx]
            idx += 1
        try:
            mapped_proto = tokens[idx].lower()
            idx += 1
            mapped_dir = tokens[idx].lower()
            idx += 1
            mapped_op = tokens[idx].lower()
            idx += 1
            mapped_val = tokens[idx]
            idx += 1
        except IndexError:
            return None, text
        mapped_val2 = None
        if mapped_op == 'range':
            if idx >= len(tokens):
                return None, text
            mapped_val2 = tokens[idx]
            idx += 1
        service = {
            'raw': ' '.join(tokens[:idx]),
            'real': {
                'proto': real_proto,
                'direction': real_dir,
                'op': real_op,
                'value': real_val,
            },
            'mapped': {
                'proto': mapped_proto,
                'direction': mapped_dir,
                'op': mapped_op,
                'value': mapped_val,
            },
        }
        if real_val2:
            service['real']['value2'] = real_val2
        if mapped_val2:
            service['mapped']['value2'] = mapped_val2
        rest = ' '.join(tokens[idx:]).strip()
        return service, rest

    def _resolve_nat_value(self, token: Optional[str]) -> List[str]:
        if not token:
            return []
        value = token.strip()
        if not value:
            return []
        lower = value.lower()
        if lower == 'interface':
            return ['interface']
        try:
            resolved = self.resolve_network(value)
        except Exception:
            resolved = set()
        if resolved:
            out: List[str] = []
            for item in resolved:
                out.append(str(item))
            return sorted(out)
        try:
            network = ipaddress.ip_network(value, strict=False)
            return [str(network)]
        except Exception:
            pass
        return [value]

    def _nat_precedence_key(self, section: int, sequence: Optional[int], index: int) -> Tuple[int, int, int]:
        if section == 2:
            secondary = index
        else:
            secondary = sequence if sequence is not None else (1000 + index)
        return (section, secondary, index)

    def normalized_nat_rules(self) -> List[dict]:
        normalized: List[dict] = []
        for idx, rule in enumerate(self.nat_rules):
            section = rule.get('section', 2 if rule.get('type') == 'auto' else 1)
            sequence = rule.get('sequence')
            precedence = self._nat_precedence_key(section, sequence, idx)
            entry: Dict[str, Any] = {
                'type': rule.get('type'),
                'section': section,
                'sequence': sequence,
                'src_if': rule.get('src_if'),
                'dst_if': rule.get('dst_if'),
                'raw': rule.get('raw'),
                'precedence': precedence,
                'order_keyword': rule.get('order_keyword'),
            }
            if rule.get('type') == 'auto':
                real_obj = rule.get('real_object')
                mapped_token = rule.get('mapped')
                entry.update({
                    'real_object': real_obj,
                    'nat_kind': rule.get('kind'),
                    'real_values': sorted(str(n) for n in self.network_objects.get(real_obj, [])),
                    'mapped': mapped_token,
                    'mapped_values': self._resolve_nat_value(mapped_token),
                })
            else:
                source = rule.get('source') or {}
                dest = rule.get('destination')
                entry.update({
                    'source': source,
                    'destination': dest,
                    'service': rule.get('service'),
                    'policy': bool(dest),
                    'extra': rule.get('extra'),
                    'src_real_values': self._resolve_nat_value(source.get('real')),
                    'src_mapped_values': self._resolve_nat_value(source.get('mapped')),
                    'dst_real_values': self._resolve_nat_value(dest.get('real') if dest else None),
                    'dst_mapped_values': self._resolve_nat_value(dest.get('mapped') if dest else None),
                })
            normalized.append(entry)
        normalized.sort(key=lambda r: r['precedence'])
        return normalized

    def _clone_service_members(self, members: Iterable[dict]) -> List[dict]:
        return [dict(m) for m in members]

    def resolve_service_group(self, name: str, visited: Optional[Set[str]] = None) -> List[dict]:
        if not hasattr(self, 'service_object_groups'):
            return []
        if visited is None:
            visited = set()
        cache_key = name
        cached = self._service_group_cache.get(cache_key)
        if cached is not None:
            return self._clone_service_members(cached)
        if name in visited:
            return []
        visited.add(name)
        out: List[dict] = []
        for m in self.service_object_groups.get(name, []):
            if isinstance(m, dict) and 'group-object' in m:
                out.extend(self.resolve_service_group(m['group-object'], visited))
            elif isinstance(m, dict) and 'proto' in m:
                out.append(m)
            elif isinstance(m, dict) and 'object' in m:
                out.append(m)
        cached_members = tuple(self._clone_service_members(out))
        self._service_group_cache[cache_key] = cached_members
        return self._clone_service_members(cached_members)

    def resolve_network(
        self,
        token: Union[str, ipaddress.IPv4Address, ipaddress.IPv4Network],
        visited: Optional[Set[str]] = None,
    ) -> Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]:
        if isinstance(token, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
            return {token}
        if isinstance(token, str):
            cache_key = token
            cached = self._network_cache.get(cache_key)
            if cached is not None:
                return set(cached)
            in_progress = self._network_in_progress.get(cache_key)
            if in_progress is not None:
                return set(in_progress)
            token_lower = token.lower()
            if token_lower in ('any', 'any4', 'any-ipv4'):
                result = {ipaddress.ip_network('0.0.0.0/0')}
                self._network_cache[cache_key] = set(result)
                return result
            if token_lower in ('any6', 'any-ipv6'):
                try:
                    result = {ipaddress.ip_network('::/0')}
                except Exception:
                    result = set()
                self._network_cache[cache_key] = set(result)
                return result
            if token in self.network_objects:
                nets = set(self.network_objects[token])
                self._network_cache[cache_key] = set(nets)
                return nets
            if token in self.network_object_groups:
                self._network_in_progress[cache_key] = set()
                try:
                    working = self._network_in_progress[cache_key]
                    for m in self.network_object_groups[token]:
                        if isinstance(m, dict):
                            if 'group-object' in m:
                                working.update(self.resolve_network(m['group-object'], visited))
                            elif 'object' in m:
                                working.update(self.resolve_network(m['object'], visited))
                        elif isinstance(m, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                            working.add(m)
                    resolved = set(working)
                finally:
                    self._network_in_progress.pop(cache_key, None)
                self._network_cache[cache_key] = set(resolved)
                return resolved
            try:
                result = {to_ip_network(token)}
            except Exception:
                result = set()
            self._network_cache[cache_key] = set(result)
            return result
        try:
            return {to_ip_network(token)}
        except Exception:
            return set()

    def find_alias_objects(self, target: Union[str, ipaddress.IPv4Address, ipaddress.IPv4Network], target_nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]) -> Dict[Union[ipaddress.IPv4Address, ipaddress.IPv4Network], Set[str]]:
        exclude: Set[str] = set([target]) if isinstance(target, str) and target in self.network_objects else set()
        aliases = {}
        for n in target_nets:
            if not isinstance(n, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                continue
            names = set(self.ip_to_objects.get(n, set())) - exclude
            if names:
                aliases[n] = names
        return aliases

    def flatten_acl(self) -> List[dict]:
        entries: List[dict] = []
        for acl_name, entries_with_line in self.acls.items():
            for ln, lineno in entries_with_line:
                m = re_acl.match(ln)
                if not m:
                    continue
                action = m.group('action').lower()
                rest = m.group('rest')
                tokens = re_tokenized.findall(rest)
                if not tokens:
                    continue
                proto_tok = tokens.pop(0).lower()
                proto = proto_tok
                entry_svc = {"proto": None, "service_group_at_proto": None}
                if proto_tok in ('object-group', 'object', 'service-object') and tokens:
                    svc_name = tokens.pop(0)
                    entry_svc["service_group_at_proto"] = {"kind": proto_tok, "name": svc_name}
                else:
                    entry_svc["proto"] = proto_tok
                srcs = self._consume_endpoint(tokens)
                dsts = self._consume_endpoint(tokens)
                svc_tail = self._consume_service_tail(tokens, entry_svc["proto"]) if tokens else {"dst_ports": [], "dst_ops": set(), "dst_service_groups": set(), "dst_service_objects": set()}
                binding = self.acl_bindings.get(acl_name)
                entries.append({
                    'acl': acl_name,
                    'action': action,
                    'proto': proto,
                    'src': srcs,
                    'dst': dsts,
                    'svc': {**entry_svc, **svc_tail},
                    'binding': binding,
                    'raw': ln.strip(),
                    'line': lineno,
                })
        return entries


def nets_overlap(set_a: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]], set_b: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]) -> bool:
    for net_a in set_a:
        if not isinstance(net_a, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
            continue
        for net_b in set_b:
            if not isinstance(net_b, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                continue
            if isinstance(net_a, ipaddress.IPv4Address) and isinstance(net_b, ipaddress.IPv4Address):
                if net_a == net_b:
                    return True
            elif isinstance(net_a, ipaddress.IPv4Network) and isinstance(net_b, ipaddress.IPv4Address):
                if net_b in net_a:
                    return True
            elif isinstance(net_a, ipaddress.IPv4Address) and isinstance(net_b, ipaddress.IPv4Network):
                if net_a in net_b:
                    return True
            elif isinstance(net_a, ipaddress.IPv4Network) and isinstance(net_b, ipaddress.IPv4Network):
                if net_a.overlaps(net_b):
                    return True
    return False


def _has_any_endpoint(e: dict) -> bool:
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


def _pick_preferred_address(nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]]) -> Optional[ipaddress.IPv4Address]:
    addresses = sorted([n for n in nets if isinstance(n, ipaddress.IPv4Address)])
    if addresses:
        return addresses[0]
    networks = sorted([n for n in nets if isinstance(n, ipaddress.IPv4Network)], key=lambda n: (-n.prefixlen, str(n)))
    if networks:
        return networks[0].network_address
    return None


def _entry_summary(entry: dict) -> str:
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


def _binding_applicable(binding: Optional[dict], context: Optional[dict], acl_name: Optional[str] = None) -> bool:
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


def _evaluate_acl_flow(cfg: ASAConfig, src_ip: ipaddress.IPv4Address, dst_ip: ipaddress.IPv4Address, svc_filter: Optional[dict], include_any: bool, iface_context: Optional[dict] = None) -> dict:
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
