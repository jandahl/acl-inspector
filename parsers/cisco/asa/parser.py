# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
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

from ciscoconfparse2 import CiscoConfParse

from ._extract import parse_dynamic_routing_block
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
from .utils import to_ip_network, nets_overlap
from .acl_matching import (
    _has_any_endpoint,
    _pick_preferred_address,
    _entry_summary,
    _binding_applicable,
    _evaluate_acl_flow,
)
from . import ir_export

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

re_object_group = re.compile(r"^object-group\s+(?P<type>network|service)\s+(?P<name>\S+)(?:\s+(?P<proto>tcp|udp|tcp-udp|ip))?", re.IGNORECASE)
re_group_network_object = re.compile(r"^\s*network-object\s+object\s+(?P<name>\S+)", re.IGNORECASE)
re_group_network_host = re.compile(r"^\s*network-object\s+host\s+(?P<ip>\S+)", re.IGNORECASE)
re_group_network_subnet = re.compile(r"^\s*network-object\s+(?!object\b)(?!host\b)(?P<ip>\S+)\s+(?P<mask>\S+)", re.IGNORECASE)
re_group_network_groupobj = re.compile(r"^\s*group-object\s+(?P<name>\S+)", re.IGNORECASE)

re_acl = re.compile(
    r"^access-list\s+(?P<name>\S+)\s+extended\s+(?P<action>permit|deny)\s+(?P<rest>.*)$",
    re.IGNORECASE,
)
re_tokenized = re.compile(r"\S+")


class ASAConfig:
    def __init__(self, text: str) -> None:
        self.raw_text = text  # Store raw config text for analysis functions
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
        # Routing (static and dynamic)
        self.static_routes: List[dict] = []
        self.dynamic_routing: Dict[str, dict] = {}  # key: protocol_processid
        self._network_cache: Dict[str, Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]] = {}
        self._service_group_cache: Dict[str, Tuple[dict, ...]] = {}
        self._group_membership_cache: Optional[Dict[str, List[str]]] = None
        self.parse()
        self._build_reverse_indexes()

    # ------------------- IR export -------------------
    def to_ir(self, device_name: Optional[str] = None) -> "ir.Device":
        """Map the parsed ASA config to the common IR.Device shape.

        Delegates to ir_export.to_ir() for the actual conversion. This preserves
        both raw and normalized views of ACLs, includes basic interface context,
        network objects and groups, service groups, and NAT rules.

        Args:
            device_name: Optional device name to include in IR

        Returns:
            ir.Device object representing the configuration

        See Also:
            parsers.cisco.asa.ir_export.to_ir: Full documentation of IR export process
        """
        return ir_export.to_ir(self, device_name)

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
        """Parse the ASA config using ciscoconfparse2's parent-child hierarchy.

        ciscoconfparse2 is a hard dependency (the single parsing engine). This
        method covers every construct the resolution/flatten/eval layers rely on:
        network objects, object-groups, interfaces, ACL lines, access-group
        bindings, object/manual NAT, static routes, and dynamic routing.
        """
        ccp = CiscoConfParse(self.lines, syntax='asa')

        # ── Network objects ──────────────────────────────────────────────────
        for obj in ccp.find_objects(r'^object\s+network\s+'):
            m = re_object.match(obj.text)
            if not m:
                continue
            name = m.group('name')
            nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]] = set()
            for child in obj.children:
                ct = child.text.strip()
                nat_m = re.match(
                    r'nat\s*\((?P<src_if>[^,]+),(?P<dst_if>[^\)]+)\)\s+(?P<rest>.+)',
                    ct, re.IGNORECASE,
                )
                if nat_m:
                    mm = re.match(
                        r'(?P<kind>static|dynamic)\s+(?P<target>\S+)',
                        nat_m.group('rest'), re.IGNORECASE,
                    )
                    self.nat_rules.append({
                        'type': 'auto', 'section': 2,
                        'src_if': nat_m.group('src_if').strip(),
                        'dst_if': nat_m.group('dst_if').strip(),
                        'real_object': name,
                        'kind': mm.group('kind').lower() if mm else None,
                        'mapped': mm.group('target') if mm else None,
                        'service': None, 'sequence': None,
                        'order_keyword': None, 'raw': ct,
                    })
                    continue
                lm = re_object_network_host.match(child.text)
                if lm:
                    try:
                        nets.add(to_ip_network(lm.group('ip')))
                    except Exception:
                        self.network_object_literals[name].add(ct)
                    continue
                lm2 = re_object_network_subnet.match(child.text)
                if lm2:
                    try:
                        nets.add(to_ip_network(lm2.group('ip'), lm2.group('mask')))
                    except Exception:
                        self.network_object_literals[name].add(ct)
                    continue
                if ct and not ct.lower().startswith(('description', 'nat')):
                    self.network_object_literals[name].add(ct)
            self.network_objects[name] = nets

        # ── Object groups ────────────────────────────────────────────────────
        for grp in ccp.find_objects(r'^object-group\s+'):
            mg = re_object_group.match(grp.text)
            if not mg:
                continue
            typ = mg.group('type').lower()
            name = mg.group('name')
            service_group_proto = (mg.group('proto') or '').lower() if typ == 'service' else None
            members: List[object] = []

            for child in grp.children:
                ln = child.text
                if typ == 'network':
                    m_host = re_group_network_host.match(ln)
                    m_obj = re_group_network_object.match(ln)
                    m_subnet = re_group_network_subnet.match(ln)
                    m_grpobj = re_group_network_groupobj.match(ln)
                    if m_host:
                        try:
                            members.append(to_ip_network(m_host.group('ip')))
                        except Exception:
                            self.network_object_group_literals[name].add(ln.strip())
                    elif m_subnet:
                        try:
                            members.append(to_ip_network(m_subnet.group('ip'), m_subnet.group('mask')))
                        except Exception:
                            self.network_object_group_literals[name].add(ln.strip())
                    elif m_obj:
                        members.append({'object': m_obj.group('name')})
                    elif m_grpobj:
                        members.append({'group-object': m_grpobj.group('name')})

                elif typ == 'service':
                    m_grpobj = re_group_network_groupobj.match(ln)
                    if m_grpobj:
                        members.append({'group-object': m_grpobj.group('name')})
                        continue
                    mport = re.match(
                        r'^\s*port-object\s+(eq|lt|gt|neq|range)\s+(\S+)(?:\s+(\S+))?',
                        ln, re.IGNORECASE,
                    )
                    if mport:
                        members.append({
                            'proto': service_group_proto or 'tcp',
                            'op': mport.group(1).lower(),
                            'v1': mport.group(2),
                            'v2': mport.group(3),
                        })
                        continue
                    msvc = re.match(
                        r'^\s*service-object\s+(tcp|udp|icmp|ip)(?:\s+(eq|lt|gt|neq|range)\s+(\S+)(?:\s+(\S+))?)?',
                        ln, re.IGNORECASE,
                    )
                    if msvc:
                        spec: dict = {'proto': msvc.group(1).lower()}
                        op = (msvc.group(2) or '').lower()
                        if op in {'eq', 'lt', 'gt', 'neq', 'range'}:
                            spec.update({'op': op, 'v1': msvc.group(3), 'v2': msvc.group(4)})
                        members.append(spec)
                        continue
                    mobj = re.match(r'^\s*service-object\s+object\s+(\S+)', ln, re.IGNORECASE)
                    if mobj:
                        members.append({'object': mobj.group(1)})

            if typ == 'network':
                self.network_object_groups[name] = members
            elif typ == 'service':
                if not hasattr(self, 'service_object_groups'):
                    self.service_object_groups = {}
                self.service_object_groups[name] = members

        # ── Interfaces ───────────────────────────────────────────────────────
        for iface in ccp.find_objects(r'^interface\s+'):
            phys = iface.text.split(None, 1)[1].strip()
            nameif = None
            ipv4 = None
            sec = None
            for child in iface.children:
                ct = child.text.strip()
                low = ct.lower()
                if low.startswith('nameif '):
                    nameif = ct.split(None, 1)[1].strip()
                elif low.startswith('ip address '):
                    parts = ct.split()
                    if len(parts) >= 3:
                        try:
                            mask = parts[3] if len(parts) >= 4 else None
                            ipv4 = to_ip_network(parts[2], mask)
                        except Exception:
                            pass
                elif low.startswith('security-level '):
                    try:
                        sec = int(ct.split()[-1])
                    except Exception:
                        pass
            key = nameif or phys
            self.interfaces[key] = {
                'phys': phys, 'nameif': nameif, 'ipv4': ipv4, 'security_level': sec,
            }

        # ── ACL lines (flat — no parent-child benefit) ────────────────────────
        for line_obj in ccp.find_objects(re_acl):
            m = re_acl.match(line_obj.text)
            if m:
                # linenum is 0-based; legacy stores 1-based
                self.acls[m.group('name')].append((line_obj.text, line_obj.linenum + 1))

        # ── Access groups ─────────────────────────────────────────────────────
        for ag in ccp.find_objects(r'^access-group\s+'):
            m = re.match(r'^access-group\s+(\S+)\s+(.+)$', ag.text, re.IGNORECASE)
            if m:
                self.acl_bindings[m.group(1)] = self._parse_access_group_binding(
                    m.group(2), ag.text
                )

        # ── Manual NAT (top-level nat lines) ──────────────────────────────────
        for nat_obj in ccp.find_objects(r'^nat\s*\('):
            line = nat_obj.text
            mnat = re.match(
                r'^nat\s*\((?P<src_if>[^,]+),(?P<dst_if>[^\)]+)\)\s*(?P<rest>.+)$',
                line, re.IGNORECASE,
            )
            if not mnat:
                continue
            src_if = mnat.group('src_if').strip()
            dst_if = mnat.group('dst_if').strip()
            rest = mnat.group('rest').strip()
            section = 1
            sequence = None
            order_kw = None
            m_seq = re.match(r'^(?P<num>\d+)\s+(?P<tail>.+)$', rest)
            if m_seq:
                sequence = int(m_seq.group('num'))
                rest = m_seq.group('tail').strip()
            lower_rest = rest.lower()
            if lower_rest.startswith('after-auto'):
                order_kw = 'after-auto'
                rest = rest.split(None, 1)[1].strip() if ' ' in rest else ''
                section = 3
            elif lower_rest.startswith('before-auto'):
                order_kw = 'before-auto'
                rest = rest.split(None, 1)[1].strip() if ' ' in rest else ''
            msrc = re.match(
                r'^source\s+(static|dynamic)\s+(\S+)\s+(\S+)(?P<tail>.*)$',
                rest, re.IGNORECASE,
            )
            if msrc:
                s_kind = msrc.group(1).lower()
                s_real = msrc.group(2)
                s_map = msrc.group(3)
                tail = (msrc.group('tail') or '').strip()
                dest_data = None
                service_data = None
                if tail.lower().startswith('destination '):
                    mdest = re.match(
                        r'^destination\s+(static|dynamic)\s+(\S+)\s+(\S+)(?P<tail>.*)$',
                        tail, re.IGNORECASE,
                    )
                    if mdest:
                        dest_data = {
                            'kind': mdest.group(1).lower(),
                            'real': mdest.group(2),
                            'mapped': mdest.group(3),
                        }
                        tail = (mdest.group('tail') or '').strip()
                if tail:
                    service_data, _ = self._parse_nat_service_clause(tail)
                self.nat_rules.append({
                    'type': 'manual', 'section': section, 'sequence': sequence,
                    'order_keyword': order_kw,
                    'src_if': src_if, 'dst_if': dst_if,
                    'source': {'kind': s_kind, 'real': s_real, 'mapped': s_map},
                    'destination': dest_data,
                    'service': service_data,
                    'raw': line.strip(),
                })
                continue
            # Dynamic PAT to interface without an explicit 'source' keyword.
            mdyn = re.match(r'^(?:source\s+)?dynamic\s+(\S+)\s+interface', rest, re.IGNORECASE)
            if mdyn:
                self.nat_rules.append({
                    'type': 'manual', 'section': section, 'sequence': sequence,
                    'order_keyword': order_kw,
                    'src_if': src_if, 'dst_if': dst_if,
                    'source': {'kind': 'dynamic', 'real': mdyn.group(1), 'mapped': 'interface'},
                    'destination': None,
                    'service': None,
                    'raw': line.strip(),
                })

        # ── Static routes ─────────────────────────────────────────────────────
        for rt in ccp.find_objects(r'^route\s+'):
            parts = rt.text.split()
            if len(parts) < 5:
                continue
            try:
                dest_ip, mask = parts[2], parts[3]
                try:
                    dest_cidr = str(to_ip_network(dest_ip, mask))
                except Exception:
                    dest_cidr = f"{dest_ip}/{mask}"
                rest_tokens = parts[5:]
                distance = None
                track = None
                tunneled = False
                if rest_tokens and rest_tokens[0].isdigit():
                    distance = int(rest_tokens[0])
                    rest_tokens = rest_tokens[1:]
                if 'tunneled' in [t.lower() for t in rest_tokens]:
                    tunneled = True
                for idx, token in enumerate(rest_tokens):
                    if token.lower() == 'track' and idx + 1 < len(rest_tokens):
                        try:
                            track = int(rest_tokens[idx + 1])
                        except ValueError:
                            pass
                self.static_routes.append({
                    'destination': dest_cidr,
                    'next_hop': parts[4] if parts[4].lower() != 'dhcp' else None,
                    'interface': parts[1],
                    'distance': distance,
                    'track': track,
                    'tunneled': tunneled,
                    'raw': rt.text.strip(),
                })
            except Exception:
                pass

        # ── Dynamic routing protocols (router ospf/eigrp/bgp/rip) ─────────────
        for robj in ccp.find_objects(r'^router\s+(ospf|eigrp|bgp|rip)\b'):
            parsed = parse_dynamic_routing_block(
                robj.text, [c.text for c in robj.children]
            )
            if parsed:
                key, routing_config = parsed
                self.dynamic_routing[key] = routing_config

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

    def build_flow_context(
        self,
        src_ip: str,
        dst_ip: str,
        proto: Optional[str] = None,
        src_port: Optional[int] = None,
        dst_port: Optional[int] = None
    ) -> "ir.FlowContext":
        """Build vendor-agnostic flow context for packet flow analysis.

        This method determines which interfaces, ACLs, and NAT rules apply to
        a specific packet flow, providing vendor-neutral abstractions for path
        checking and policy evaluation.

        Args:
            src_ip: Source IP address (string format)
            dst_ip: Destination IP address (string format)
            proto: Optional protocol (tcp/udp/icmp/etc.)
            src_port: Optional source port number
            dst_port: Optional destination port number

        Returns:
            ir.FlowContext with ingress/egress zones, applicable policies,
            and vendor-specific metadata.

        Raises:
            ValueError: If IP addresses are malformed
        """
        if ir is None:
            raise RuntimeError("IR module not available")

        # Resolve IPs to ipaddress objects
        try:
            src_ip_obj = ipaddress.ip_address(src_ip)
            dst_ip_obj = ipaddress.ip_address(dst_ip)
        except ValueError as e:
            raise ValueError(f"Invalid IP address: {e}")

        # Determine which interface owns each IP (if any)
        src_local_if = self.interface_for_ip(src_ip_obj)  # Interface where src IP lives
        dst_local_if = self.interface_for_ip(dst_ip_obj)  # Interface where dst IP lives

        # Determine physical ingress/egress interfaces and flow direction
        # For ASA, we need to consider:
        # - If src is local (has interface), packet exits via that interface (outbound)
        # - If dst is local (has interface), packet enters via... we need routing!
        # - For now, simplified: assume all non-local traffic uses a default interface

        # Simplified model (without full routing table):
        # - src_local + dst_local = lateral (between interfaces)
        # - src_local + dst_external = outbound (from local to internet)
        # - src_external + dst_local = inbound (from internet to local)
        # - src_external + dst_external = transit (unlikely without routing)

        if src_local_if and dst_local_if:
            direction = 'lateral' if src_local_if != dst_local_if else 'loopback'
            physical_ingress = src_local_if  # Packet leaves source interface
            physical_egress = dst_local_if   # Packet arrives at destination interface
        elif src_local_if and not dst_local_if:
            direction = 'outbound'
            physical_ingress = src_local_if  # Packet leaves this interface
            physical_egress = None           # Unknown external path
        elif not src_local_if and dst_local_if:
            direction = 'inbound'
            # For inbound, we need to determine which interface the packet enters
            # Without full routing, we assume it enters via the "lowest security" interface
            # that's NOT the destination interface
            physical_ingress = self._guess_ingress_interface(dst_local_if)
            physical_egress = dst_local_if   # Packet routed to this interface
        else:
            direction = 'transit'
            physical_ingress = None
            physical_egress = None

        # Collect applicable ACLs based on physical interfaces and direction
        # ASA evaluates ACLs at the interface where packet physically arrives/departs
        acls = []

        if direction == 'inbound' and physical_ingress:
            # Packet enters via physical_ingress, apply 'in' ACL
            acls.extend(self.acls_for_interface(physical_ingress, 'in'))
        elif direction == 'outbound' and physical_ingress:
            # Packet exits via physical_ingress, apply 'out' ACL
            acls.extend(self.acls_for_interface(physical_ingress, 'out'))
        elif direction == 'lateral':
            # Packet traverses both interfaces
            if physical_ingress:
                acls.extend(self.acls_for_interface(physical_ingress, 'out'))
            if physical_egress:
                acls.extend(self.acls_for_interface(physical_egress, 'in'))
        elif direction == 'loopback' and physical_ingress:
            # Same interface, check both directions
            acls.extend(self.acls_for_interface(physical_ingress, 'in'))
            acls.extend(self.acls_for_interface(physical_ingress, 'out'))

        # Global ACLs always apply
        acls.extend(self.acls_for_global())

        # ingress_zone/egress_zone represent IP ownership, not physical packet path
        # ingress_zone = interface where source IP resides (None if external)
        # egress_zone = interface where destination IP resides (None if external)
        ingress_zone = src_local_if
        egress_zone = dst_local_if

        # Collect applicable NAT rules
        # NAT rules are evaluated based on interface pair (physical path)
        nat_candidates = []
        for rule in self.nat_rules:
            if self._nat_applies_to_flow(rule, physical_ingress, physical_egress):
                # Include raw config line as identifier
                nat_id = rule.get('raw', f"NAT-{rule.get('type', 'unknown')}")
                nat_candidates.append(nat_id)

        # Build vendor-specific context
        # Security levels are based on physical path, not IP ownership
        ingress_sec = self.security_level_for_interface(physical_ingress) or 0
        egress_sec = self.security_level_for_interface(physical_egress) or 0

        vendor_ctx = {
            'ingress_security_level': ingress_sec,
            'egress_security_level': egress_sec,
            # ASA implicit permit: higher sec to lower sec (no ACL needed)
            'implicit_permit': physical_ingress and physical_egress and ingress_sec > egress_sec,
            'physical_ingress_interface': physical_ingress,
            'physical_egress_interface': physical_egress,
            'src_local_interface': src_local_if,
            'dst_local_interface': dst_local_if,
        }

        return ir.FlowContext(
            src_ip=src_ip,
            dst_ip=dst_ip,
            proto=proto,
            src_port=src_port,
            dst_port=dst_port,
            ingress_zone=ingress_zone,  # Interface where src IP resides
            egress_zone=egress_zone,     # Interface where dst IP resides
            flow_direction=direction,
            applicable_policies=acls,
            applicable_nats=nat_candidates,
            vendor_context=vendor_ctx,
        )

    def _guess_ingress_interface(self, dst_interface: str) -> Optional[str]:
        """Guess which interface an inbound packet enters through.

        Without full routing information, we use a heuristic:
        - Return the interface with the lowest security level
        - Exclude the destination interface

        Args:
            dst_interface: The destination interface (to exclude)

        Returns:
            Name of the likely ingress interface, or None if cannot determine
        """
        candidates = []
        for name, meta in self.interfaces.items():
            if name == dst_interface:
                continue
            sec_level = meta.get('security_level')
            if sec_level is not None:
                candidates.append((sec_level, name))

        if not candidates:
            return None

        # Return interface with lowest security level (most likely "outside")
        candidates.sort()
        return candidates[0][1]

    def _nat_applies_to_flow(
        self,
        nat_rule: dict,
        ingress_if: Optional[str],
        egress_if: Optional[str]
    ) -> bool:
        """Check if NAT rule applies to this interface pair.

        Args:
            nat_rule: Parsed NAT rule dict
            ingress_if: Ingress interface name (or None)
            egress_if: Egress interface name (or None)

        Returns:
            True if the NAT rule's src_if/dst_if match the flow interfaces.
        """
        src_if = (nat_rule.get('src_if') or '').lower()
        dst_if = (nat_rule.get('dst_if') or '').lower()

        if not src_if or not dst_if:
            return False

        # Match interface names (case-insensitive)
        ingress_match = not ingress_if or ingress_if.lower() == src_if
        egress_match = not egress_if or egress_if.lower() == dst_if

        return ingress_match and egress_match

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

    def resolve_service_group(
        self,
        name: str,
        visited: Optional[Set[str]] = None,
        incomplete: Optional[Set[str]] = None,
    ) -> List[dict]:
        if not hasattr(self, 'service_object_groups'):
            return []
        is_top_level = visited is None
        if visited is None:
            visited = set()
        if incomplete is None:
            incomplete = set()

        cache_key = name
        cached = self._service_group_cache.get(cache_key)
        if cached is not None:
            return self._clone_service_members(cached)
        if name in visited:
            incomplete.update(visited)
            return []
        visited.add(name)
        out: List[dict] = []
        self._service_group_cache[cache_key] = out  # pre-cache mutable ref so cycle re-entry returns partial members
        for m in self.service_object_groups.get(name, []):
            if isinstance(m, dict) and 'group-object' in m:
                dep = m['group-object']
                out.extend(self.resolve_service_group(dep, visited, incomplete))
                if dep in incomplete:
                    incomplete.add(name)
            elif isinstance(m, dict) and 'proto' in m:
                out.append(m)
            elif isinstance(m, dict) and 'object' in m:
                out.append(m)
        visited.discard(name)

        # Deduplicate: cycle re-entry via pre-cache may have returned members
        # already present in out (e.g. members accumulated before the recursive call).
        deduped: List[dict] = []
        for item in out:
            if item not in deduped:
                deduped.append(item)

        cached_members = tuple(self._clone_service_members(deduped))
        self._service_group_cache[cache_key] = cached_members

        if is_top_level:
            for key in incomplete:
                self._service_group_cache.pop(key, None)

        return self._clone_service_members(cached_members)

    def group_membership(self) -> Dict[str, List[str]]:
        """Return a reverse lookup: object/group name → list of parent group names.

        Useful for displaying which object-groups contain a matched named object.
        The mapping is computed once and cached on first access. Returns a copy
        so callers cannot corrupt the internal cache.

        Only named members (``network-object object <NAME>`` and
        ``group-object <NAME>``) are indexed; inline host/subnet entries have
        no resolvable name and are skipped.
        """
        if self._group_membership_cache is None:
            temp: Dict[str, Set[str]] = {}
            for grp_name, members in self.network_object_groups.items():
                for m in members:
                    if isinstance(m, dict):
                        child = m.get('object') or m.get('group-object')
                        if child:
                            temp.setdefault(child, set()).add(grp_name)
            self._group_membership_cache = {
                child: sorted(parents) for child, parents in temp.items()
            }
        # Copy each list so callers cannot mutate the cache.
        return {k: list(parents) for k, parents in self._group_membership_cache.items()}

    def resolve_network(
        self,
        token: Union[str, ipaddress.IPv4Address, ipaddress.IPv4Network],
        visited: Optional[Set[str]] = None,
        incomplete: Optional[Set[str]] = None,
    ) -> Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]:
        is_top_level = visited is None
        if visited is None:
            visited = set()
        if incomplete is None:
            incomplete = set()

        if isinstance(token, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
            return {token}
        if isinstance(token, str):
            cache_key = token
            cached = self._network_cache.get(cache_key)
            if cached is not None:
                return set(cached)
            token_lower = token.lower()
            if token_lower in ('any', 'any4', 'any-ipv4'):
                result = {ipaddress.ip_network('0.0.0.0/0')}
                self._network_cache[cache_key] = set(result)
                return result
            if token_lower in ('any6', 'any-ipv6'):
                try:
                    result = {ipaddress.ip_network('::/0')}
                except (ValueError, TypeError):
                    result = set()
                self._network_cache[cache_key] = set(result)
                return result
            if token in self.network_objects:
                nets = set(self.network_objects[token])
                self._network_cache[cache_key] = set(nets)
                return nets
            if token in self.network_object_groups:
                if token in visited:
                    incomplete.update(visited)
                    cached_cycle = self._network_cache.get(cache_key)
                    return set(cached_cycle) if cached_cycle is not None else set()
                visited.add(token)
                resolved: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]] = set()
                self._network_cache[cache_key] = resolved
                for m in self.network_object_groups[token]:
                    if isinstance(m, dict):
                        if 'group-object' in m:
                            dep = m['group-object']
                            resolved.update(self.resolve_network(dep, visited, incomplete))
                            if dep in incomplete:
                                incomplete.add(token)
                        elif 'object' in m:
                            dep = m['object']
                            resolved.update(self.resolve_network(dep, visited, incomplete))
                            if dep in incomplete:
                                incomplete.add(token)
                    elif isinstance(m, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                        resolved.add(m)

                self._network_cache[cache_key] = set(resolved)
                visited.discard(token)

                if is_top_level:
                    for key in incomplete:
                        self._network_cache.pop(key, None)

                return set(resolved)
            try:
                result = {to_ip_network(token)}
            except (ValueError, TypeError):
                result = set()
            self._network_cache[cache_key] = set(result)
            return result
        try:
            return {to_ip_network(token)}
        except (ValueError, TypeError):
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

                # Extract bound_to and direction from binding for easier access
                bound_to = None
                direction = None
                if binding:
                    scope = (binding.get('scope') or '').lower()
                    if scope == 'global':
                        bound_to = 'global'
                        direction = 'global'
                    elif scope == 'control-plane':
                        bound_to = 'control-plane'
                        direction = binding.get('direction') or 'any'
                    else:
                        # Interface binding
                        bound_to = binding.get('interface')
                        direction = binding.get('direction') or 'any'

                entries.append({
                    'acl': acl_name,
                    'action': action,
                    'proto': proto,
                    'src': srcs,
                    'dst': dsts,
                    'svc': {**entry_svc, **svc_tail},
                    'binding': binding,
                    'bound_to': bound_to,
                    'direction': direction,
                    'raw': ln.strip(),
                    'line': lineno,
                })
        return entries

    def _packet_matches_acl_entry(
        self,
        packet: dict,
        entry: dict
    ) -> bool:
        """Check if a packet matches an ACL entry.

        Args:
            packet: Dict with src_ip, dst_ip, proto, src_port, dst_port (all as objects)
            entry: Flattened ACL entry dict

        Returns:
            True if packet matches all criteria in the entry
        """
        # Match protocol
        entry_proto = entry.get('proto', '').lower()
        packet_proto = packet.get('proto', '').lower()

        # Handle service-group at proto position
        if entry.get('svc', {}).get('service_group_at_proto'):
            # Service group matching not fully implemented yet
            # For now, consider it a match if packet has a protocol
            pass
        elif entry_proto and entry_proto not in ('ip', 'any'):
            if packet_proto != entry_proto:
                return False

        # Match source IP
        src_ip = packet.get('src_ip')
        entry_srcs = entry.get('src', [])
        if src_ip and entry_srcs:
            src_match = False
            for src_spec in entry_srcs:
                if isinstance(src_spec, str):
                    if src_spec in ('any', 'any4'):
                        src_match = True
                        break
                    # Try resolving object/group names
                    resolved = self.resolve_object_or_group(src_spec)
                    if nets_overlap({src_ip}, resolved):
                        src_match = True
                        break
                elif isinstance(src_spec, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                    if isinstance(src_ip, ipaddress.IPv4Address):
                        if src_spec == src_ip or (isinstance(src_spec, ipaddress.IPv4Network) and src_ip in src_spec):
                            src_match = True
                            break
            if not src_match:
                return False

        # Match destination IP
        dst_ip = packet.get('dst_ip')
        entry_dsts = entry.get('dst', [])
        if dst_ip and entry_dsts:
            dst_match = False
            for dst_spec in entry_dsts:
                if isinstance(dst_spec, str):
                    if dst_spec in ('any', 'any4'):
                        dst_match = True
                        break
                    # Try resolving object/group names
                    resolved = self.resolve_object_or_group(dst_spec)
                    if nets_overlap({dst_ip}, resolved):
                        dst_match = True
                        break
                elif isinstance(dst_spec, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                    if isinstance(dst_ip, ipaddress.IPv4Address):
                        if dst_spec == dst_ip or (isinstance(dst_spec, ipaddress.IPv4Network) and dst_ip in dst_spec):
                            dst_match = True
                            break
            if not dst_match:
                return False

        # Match destination port (if protocol is tcp/udp)
        if packet_proto in ('tcp', 'udp'):
            dst_port = packet.get('dst_port')
            svc = entry.get('svc', {})
            dst_ports = svc.get('dst_ports', [])

            if dst_port is not None and dst_ports:
                port_match = False
                for op, (p1, p2) in dst_ports:
                    if op == 'eq' and p1 == dst_port:
                        port_match = True
                        break
                    elif op == 'range' and p1 is not None and p2 is not None:
                        if p1 <= dst_port <= p2:
                            port_match = True
                            break
                    elif op == 'lt' and p1 is not None and dst_port < p1:
                        port_match = True
                        break
                    elif op == 'gt' and p1 is not None and dst_port > p1:
                        port_match = True
                        break
                    elif op == 'neq' and p1 is not None and dst_port != p1:
                        port_match = True
                        break

                if not port_match:
                    return False

        return True

    def evaluate_packet(
        self,
        src_ip: str,
        dst_ip: str,
        proto: Optional[str] = None,
        src_port: Optional[int] = None,
        dst_port: Optional[int] = None
    ) -> dict:
        """Evaluate whether a packet is permitted or denied.

        Uses build_flow_context() to determine applicable ACLs, then evaluates
        them in order to find the first match. Returns detailed result with
        hop-by-hop explanation.

        Args:
            src_ip: Source IP address (string)
            dst_ip: Destination IP address (string)
            proto: Optional protocol (tcp/udp/icmp/etc.)
            src_port: Optional source port
            dst_port: Optional destination port

        Returns:
            Dict with:
                - verdict: 'permit' | 'deny' | 'implicit-permit' | 'implicit-deny'
                - matched_acl: Name of ACL that matched (or None)
                - matched_entry: The ACL entry that matched (or None)
                - flow_context: The FlowContext object
                - explanation: Human-readable explanation
                - steps: List of evaluation steps
        """
        if ir is None:
            raise RuntimeError("IR module not available")

        # Build flow context
        try:
            ctx = self.build_flow_context(src_ip, dst_ip, proto, src_port, dst_port)
        except ValueError as e:
            return {
                'verdict': 'error',
                'error': str(e),
                'explanation': f"Failed to build flow context: {e}"
            }

        # Prepare packet object for matching
        try:
            src_ip_obj = ipaddress.ip_address(src_ip)
            dst_ip_obj = ipaddress.ip_address(dst_ip)
        except ValueError as e:
            return {
                'verdict': 'error',
                'error': str(e),
                'explanation': f"Invalid IP address: {e}"
            }

        packet = {
            'src_ip': src_ip_obj,
            'dst_ip': dst_ip_obj,
            'proto': (proto or 'ip').lower(),
            'src_port': src_port,
            'dst_port': dst_port,
        }

        steps = []

        # Step 1: Flow classification
        steps.append({
            'step': 'flow_classification',
            'description': f"Flow classified as {ctx.flow_direction}",
            'details': {
                'direction': ctx.flow_direction,
                'ingress_zone': ctx.ingress_zone,
                'egress_zone': ctx.egress_zone,
            }
        })

        # Step 2: Check implicit permit (ASA allows higher→lower security)
        if ctx.vendor_context.get('implicit_permit'):
            steps.append({
                'step': 'implicit_permit_check',
                'description': 'Traffic permitted by security level (higher→lower)',
                'details': {
                    'ingress_security': ctx.vendor_context.get('ingress_security_level'),
                    'egress_security': ctx.vendor_context.get('egress_security_level'),
                }
            })

        # Step 3: Evaluate applicable ACLs
        all_entries = self.flatten_acl()

        for acl_name in ctx.applicable_policies:
            acl_entries = [e for e in all_entries if e.get('acl') == acl_name]

            steps.append({
                'step': 'acl_evaluation',
                'description': f"Evaluating ACL '{acl_name}' ({len(acl_entries)} entries)",
                'acl_name': acl_name,
            })

            for entry in acl_entries:
                if self._packet_matches_acl_entry(packet, entry):
                    action = entry.get('action', '').lower()
                    verdict = 'permit' if action == 'permit' else 'deny'

                    steps.append({
                        'step': 'acl_match',
                        'description': f"Matched ACL entry: {action}",
                        'entry': entry.get('raw'),
                        'line': entry.get('line'),
                    })

                    return {
                        'verdict': verdict,
                        'matched_acl': acl_name,
                        'matched_entry': entry,
                        'flow_context': ctx,
                        'explanation': f"Traffic {verdict}ted by ACL '{acl_name}' at line {entry.get('line')}",
                        'steps': steps,
                    }

        # No explicit match found
        if ctx.vendor_context.get('implicit_permit'):
            verdict = 'implicit-permit'
            explanation = "No explicit ACL match; permitted by security level policy"
        else:
            verdict = 'implicit-deny'
            explanation = "No explicit ACL match; denied by default"

        steps.append({
            'step': 'implicit_action',
            'description': explanation,
        })

        return {
            'verdict': verdict,
            'matched_acl': None,
            'matched_entry': None,
            'flow_context': ctx,
            'explanation': explanation,
            'steps': steps,
        }
