# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""FortiGate parser and evaluation helpers.

This module parses the FortiOS CLI syntax used across configuration blocks and
captures the subset required for ACL/NAT analysis and IR export:

- config system interface / zone
- config firewall address / addrgrp / vip / vipgrp / ippool
- config firewall service custom / group
- config firewall policy (IPv4)
- config firewall central-snat-map
- config router static / ospf / bgp

Assumptions and scope
---------------------
- IPv4 focused. IPv6, SD-WAN, and fabric connectors are future work.
- VDOM-awareness is supported via `_select_vdom_lines`, but only one VDOM is
  parsed per FTGConfig instance (first or user-selected).
- Time-ranges and UTM profile resolution are out of scope for now.
- Service objects referenced by name fall back to socket lookup when not
  defined in `service custom` or `service group`.
- Policy default action 'accept' maps to 'permit', 'deny' to 'deny'.

The flattened rule structure matches parsers.cisco.asa output to enable
cross-vendor comparison at the CLI level while preserving Forti-specific
metadata (interfaces, NAT flags, UUIDs) for IR consumption.
"""

from __future__ import annotations

import ipaddress
import shlex
import socket
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple, Union


def to_ip_network(ip: str, mask: Optional[str] = None) -> Union[ipaddress.IPv4Address, ipaddress.IPv4Network]:
    if mask is not None:
        return ipaddress.ip_network(f"{ip}/{mask}", strict=False)
    if "/" in ip:
        return ipaddress.ip_network(ip, strict=False)
    return ipaddress.ip_address(ip)


class FTGConfig:
    """Parsed representation of relevant FortiGate configuration.

    Public attributes:
    - addresses: Dict[str, Set[IPv4Address|IPv4Network]]
    - addrgrps: Dict[str, List[Union['object', IPv4*]]]
    - services: Dict[str, dict] (proto, ranges); groups: Dict[str, Set[name]]
    - policies: List[dict] with keys: action, srcaddr (names), dstaddr (names), services (names)
    """

    def __init__(self, text: str, vdom: Optional[str] = None) -> None:
        """Initialize with raw config text and optional VDOM name.

        If the config contains 'config vdom' blocks and no vdom is provided,
        the first VDOM encountered is parsed. If no 'config vdom' is present,
        the whole file is parsed as a single context.
        """
        self.raw_text = text
        self._raw_lines = [line.rstrip() for line in text.splitlines()]
        self.vdom = vdom
        # Extract VDOM-specific view if applicable
        self.lines, self.vdom = self._select_vdom_lines(self._raw_lines, vdom)
        self.addresses: Dict[str, Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]] = {}
        self.addrgrps: Dict[str, List[Union[dict, ipaddress.IPv4Address, ipaddress.IPv4Network]]] = {}
        self.services: Dict[str, dict] = {}
        self.service_groups: Dict[str, Set[str]] = {}
        self.interfaces: Dict[str, dict] = {}
        self.zones: Dict[str, dict] = {}
        self.interface_zones: Dict[str, str] = {}
        self.vips: Dict[str, dict] = {}
        self.vipgrps: Dict[str, List[str]] = {}
        self.ippools: Dict[str, dict] = {}
        self.central_snat_map: List[dict] = []
        self.policies: List[dict] = []
        self.policy_vip_refs: Dict[str, Set[str]] = defaultdict(set)
        self.static_routes: List[dict] = []
        self.dynamic_routing: Dict[str, dict] = {}  # key: protocol_processid
        self._group_membership_cache: Optional[Dict[str, List[str]]] = None
        self._parse()
        self._build_reverse_indexes()
        self._map_zones()

    # ---------- Block parsers ----------
    def _parse(self) -> None:
        i = 0
        L = len(self.lines)
        while i < L:
            line = self.lines[i].strip()
            if line.startswith('config firewall address'):
                i = self._parse_addresses(i + 1)
                continue
            if line.startswith('config firewall addrgrp'):
                i = self._parse_addrgrp(i + 1)
                continue
            if line.startswith('config firewall service custom'):
                i = self._parse_service_custom(i + 1)
                continue
            if line.startswith('config firewall service group'):
                i = self._parse_service_group(i + 1)
                continue
            if line.startswith('config firewall policy'):
                i = self._parse_policy(i + 1)
                continue
            if line.startswith('config system interface'):
                i = self._parse_system_interface(i + 1)
                continue
            if line.startswith('config system zone'):
                i = self._parse_system_zone(i + 1)
                continue
            if line.startswith('config firewall vipgrp'):
                i = self._parse_firewall_vipgrp(i + 1)
                continue
            if line.startswith('config firewall vip'):
                i = self._parse_firewall_vip(i + 1)
                continue
            if line.startswith('config firewall ippool'):
                i = self._parse_firewall_ippool(i + 1)
                continue
            if line.startswith('config firewall central-snat-map'):
                i = self._parse_central_snat(i + 1)
                continue
            if line.startswith('config router static'):
                i = self._parse_static_routes(i + 1)
                continue
            if line.startswith('config router ospf'):
                i = self._parse_router_ospf(i + 1)
                continue
            if line.startswith('config router bgp'):
                i = self._parse_router_bgp(i + 1)
                continue
            i += 1

    @staticmethod
    def list_vdom_names(lines: List[str]) -> List[str]:
        """Return the ordered list of unique VDOM names defined in the config."""
        names: List[str] = []
        seen: Set[str] = set()
        i = 0
        L = len(lines)
        while i < L:
            s = lines[i].strip()
            if s.startswith("config vdom"):
                i += 1
                while i < L:
                    s2 = lines[i].strip()
                    if s2.startswith("edit "):
                        name = s2.split("edit", 1)[1].strip().strip('"')
                        if name not in seen:
                            names.append(name)
                            seen.add(name)
                        # skip inner block
                        i += 1
                        nest = 0
                        while i < L:
                            s3 = lines[i].strip()
                            if s3 == "next" and nest == 0:
                                break
                            if s3.startswith("config "):
                                nest += 1
                            if s3 == "end" and nest > 0:
                                nest -= 1
                            i += 1
                        i += 1  # skip 'next'
                    elif s2 == "end":
                        i += 1
                        break
                    else:
                        i += 1
                continue
            i += 1
        return names

    def _select_vdom_lines(self, lines: List[str], want_vdom: Optional[str]) -> Tuple[List[str], Optional[str]]:
        """Return lines belonging to the specified VDOM sub-block if present.

        If 'config vdom' is found, choose the 'edit <name>' block matching
        want_vdom; if want_vdom is None, pick the first. Returns the inner
        lines of that VDOM context and the resolved VDOM name. If no 'config vdom'
        is found, returns the original lines with vdom=None.
        """
        i = 0
        L = len(lines)
        while i < L:
            s = lines[i].strip()
            if s.startswith('config vdom'):
                i += 1
                vdom_blocks: Dict[str, List[str]] = {}
                order: List[str] = []
                while i < L:
                    s2 = lines[i].strip()
                    if s2.startswith('edit '):
                        name = s2.split('edit', 1)[1].strip().strip('"')
                        order.append(name)
                        i += 1
                        sub: List[str] = []
                        nest = 0
                        while i < L:
                            s3 = lines[i].strip()
                            if s3 == 'next' and nest == 0:
                                break
                            if s3.startswith('config '):
                                nest += 1
                            if s3 == 'end' and nest > 0:
                                nest -= 1
                            sub.append(lines[i])
                            i += 1
                        vdom_blocks[name] = sub[:]
                        i += 1  # skip 'next'
                    elif s2 == 'end':
                        i += 1
                        break
                    else:
                        i += 1
                # Choose requested VDOM if it has content
                if want_vdom:
                    block = vdom_blocks.get(want_vdom)
                    if block:
                        return block, want_vdom
                    # Requested VDOM exists but empty; continue searching later blocks
                else:
                    for name in order:
                        block = vdom_blocks.get(name)
                        if block:
                            return block, name
                continue
            i += 1
        return lines, None
    def _parse_block(self, i: int, end_token: str = 'end') -> Tuple[int, List[str]]:
        acc: List[str] = []
        L = len(self.lines)
        while i < L:
            line = self.lines[i].rstrip()
            if line.strip() == end_token:
                return i + 1, acc
            acc.append(line)
            i += 1
        return i, acc

    # ---------- Helpers ----------
    @staticmethod
    def _strip_quotes(token: str) -> str:
        if token.startswith('"') and token.endswith('"'):
            return token[1:-1]
        return token

    @staticmethod
    def _tokenize(line: str) -> List[str]:
        lexer = shlex.shlex(line, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = ''
        try:
            return list(lexer)
        except ValueError:
            return line.split()

    def _parse_addresses(self, i: int) -> int:
        i, blk = self._parse_block(i)
        cur: Optional[str] = None
        subnet_ip = subnet_mask = None
        for line in blk:
            s = line.strip()
            if s.startswith('edit '):
                cur = s.split('edit', 1)[1].strip().strip('"')
                subnet_ip = subnet_mask = None
            elif s.startswith('set subnet '):
                parts = s.split()
                if len(parts) >= 4:
                    subnet_ip, subnet_mask = parts[2], parts[3]
            elif s.startswith('next') and cur:
                nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]] = set()
                if subnet_ip and subnet_mask:
                    nets.add(to_ip_network(subnet_ip, subnet_mask))
                self.addresses[cur] = nets
                cur = None
        return i

    def group_membership(self) -> Dict[str, List[str]]:
        """Return a reverse lookup: address/addrgrp name → list of parent addrgrp names.

        Only named members (``set member <NAME> ...``) are indexed; inline
        host/subnet entries have no resolvable name and are skipped.
        The mapping is computed once and cached. Returns a copy so callers
        cannot corrupt the internal cache.

        Note: FortiGate stores both named addresses and nested addrgrp references
        as ``{'object': name}`` (a single key), unlike ASA which uses separate
        ``'object'`` and ``'group-object'`` keys. Only ``m.get('object')`` is
        needed here.
        """
        if self._group_membership_cache is None:
            temp: Dict[str, Set[str]] = {}
            for grp_name, members in self.addrgrps.items():
                for m in members:
                    if isinstance(m, dict):
                        child = m.get('object')
                        if child:
                            temp.setdefault(child, set()).add(grp_name)
            self._group_membership_cache = {
                child: sorted(parents) for child, parents in temp.items()
            }
        # Copy each list so callers cannot mutate the cache.
        return {k: list(parents) for k, parents in self._group_membership_cache.items()}

    def _parse_addrgrp(self, i: int) -> int:
        i, blk = self._parse_block(i)
        cur: Optional[str] = None
        members: List[Union[dict, ipaddress.IPv4Address, ipaddress.IPv4Network]] = []
        for line in blk:
            s = line.strip()
            if s.startswith('edit '):
                cur = s.split('edit', 1)[1].strip().strip('"')
                members = []
            elif s.startswith('set member '):
                names = [x.strip('"') for x in s.split()[2:]]
                for n in names:
                    members.append({'object': n})
            elif s.startswith('next') and cur is not None:
                self.addrgrps[cur] = members[:]
                cur = None
        return i

    def _parse_system_interface(self, i: int) -> int:
        i, blk = self._parse_block(i)
        cur: Optional[str] = None
        cur_data: Dict[str, Union[str, List[str], bool]] = {}
        for line in blk:
            s = line.strip()
            if not s:
                continue
            tokens = self._tokenize(s)
            if not tokens:
                continue
            head = tokens[0].lower()
            if head == 'edit' and len(tokens) >= 2:
                cur = self._strip_quotes(tokens[1])
                cur_data = {}
            elif head == 'set' and len(tokens) >= 3 and cur:
                key = tokens[1].lower()
                values = [self._strip_quotes(t) for t in tokens[2:]]
                if key == 'ip':
                    cur_data['ip'] = ' '.join(values)
                elif key == 'allowaccess':
                    cur_data['allowaccess'] = values
                elif key == 'alias':
                    cur_data['alias'] = ' '.join(values)
                elif key == 'description':
                    cur_data['description'] = ' '.join(values)
                else:
                    cur_data[key] = values if len(values) > 1 else values[0]
            elif head == 'next' and cur:
                self.interfaces[cur] = cur_data.copy()
                cur = None
        return i

    def _parse_system_zone(self, i: int) -> int:
        i, blk = self._parse_block(i)
        cur: Optional[str] = None
        cur_data: Dict[str, Union[str, List[str]]] = {}
        for line in blk:
            s = line.strip()
            if not s:
                continue
            tokens = self._tokenize(s)
            if not tokens:
                continue
            head = tokens[0].lower()
            if head == 'edit' and len(tokens) >= 2:
                cur = self._strip_quotes(tokens[1])
                cur_data = {}
            elif head == 'set' and len(tokens) >= 3 and cur:
                key = tokens[1].lower()
                values = [self._strip_quotes(t) for t in tokens[2:]]
                # Most zone properties are multi-value; collapse singletons for readability
                cur_data[key] = values if len(values) > 1 else values
            elif head == 'next' and cur:
                self.zones[cur] = cur_data.copy()
                cur = None
        return i

    def _map_zones(self) -> None:
        """Build interface→zone mapping from parsed zone data."""
        self.interface_zones = {}
        for zone, data in self.zones.items():
            interfaces = data.get('interface')
            if interfaces is None:
                continue
            if isinstance(interfaces, list):
                names = interfaces
            else:
                names = [interfaces]
            for iface in names:
                if iface:
                    self.interface_zones[iface] = zone

    def _interfaces_to_zones(self, interfaces: Union[List[str], str]) -> List[str]:
        if isinstance(interfaces, str):
            iface_list = [interfaces]
        else:
            iface_list = interfaces
        zones: List[str] = []
        for iface in iface_list:
            zone = self.interface_zones.get(iface)
            if zone:
                zones.append(zone)
        return zones

    def _parse_service_custom(self, i: int) -> int:
        i, blk = self._parse_block(i)
        cur: Optional[str] = None
        tcp_range = udp_range = None
        for line in blk:
            s = line.strip()
            if s.startswith('edit '):
                cur = s.split('edit', 1)[1].strip().strip('"')
                tcp_range = udp_range = None
            elif s.startswith('set tcp-portrange '):
                tcp_range = s.split('set tcp-portrange', 1)[1].strip()
            elif s.startswith('set udp-portrange '):
                udp_range = s.split('set udp-portrange', 1)[1].strip()
            elif s.startswith('next') and cur:
                spec = {}
                if tcp_range:
                    spec.setdefault('tcp', []).extend(self._split_ranges(tcp_range))
                if udp_range:
                    spec.setdefault('udp', []).extend(self._split_ranges(udp_range))
                self.services[cur] = spec
                cur = None
        return i

    def _parse_service_group(self, i: int) -> int:
        i, blk = self._parse_block(i)
        cur: Optional[str] = None
        members: Set[str] = set()
        for line in blk:
            s = line.strip()
            if s.startswith('edit '):
                cur = s.split('edit', 1)[1].strip().strip('"')
                members = set()
            elif s.startswith('set member '):
                names = [x.strip('"') for x in s.split()[2:]]
                members.update(names)
            elif s.startswith('next') and cur:
                self.service_groups[cur] = set(members)
                cur = None
        return i

    def _parse_firewall_vip(self, i: int) -> int:
        i, blk = self._parse_block(i)
        cur: Optional[str] = None
        current: Dict[str, Union[str, List[str], bool]] = {}
        for line in blk:
            s = line.strip()
            if not s:
                continue
            tokens = self._tokenize(s)
            if not tokens:
                continue
            head = tokens[0].lower()
            if head == 'edit' and len(tokens) >= 2:
                cur = self._strip_quotes(tokens[1])
                current = {}
            elif head == 'set' and len(tokens) >= 3 and cur:
                key = tokens[1].lower()
                values = [self._strip_quotes(t) for t in tokens[2:]]
                if key in {'extip', 'mappedip'}:
                    current[key] = values
                elif key in {'extintf', 'type'}:
                    current[key] = values[0]
                elif key in {'extport', 'mappedport'} and values:
                    current[key] = values[0]
                elif key == 'portforward' and values:
                    current[key] = values[0].lower() == 'enable'
                else:
                    current[key] = values if len(values) > 1 else values[0]
            elif head == 'next' and cur:
                self.vips[cur] = current.copy()
                cur = None
        return i

    def _parse_firewall_vipgrp(self, i: int) -> int:
        i, blk = self._parse_block(i)
        cur: Optional[str] = None
        members: List[str] = []
        for line in blk:
            s = line.strip()
            if not s:
                continue
            tokens = self._tokenize(s)
            if not tokens:
                continue
            head = tokens[0].lower()
            if head == 'edit' and len(tokens) >= 2:
                cur = self._strip_quotes(tokens[1])
                members = []
            elif head == 'set' and len(tokens) >= 3 and tokens[1].lower() == 'member':
                members.extend(self._strip_quotes(t) for t in tokens[2:])
            elif head == 'next' and cur:
                self.vipgrps[cur] = members[:]
                cur = None
        return i

    def _parse_firewall_ippool(self, i: int) -> int:
        i, blk = self._parse_block(i)
        cur: Optional[str] = None
        current: Dict[str, Union[str, bool]] = {}
        for line in blk:
            s = line.strip()
            if not s:
                continue
            tokens = self._tokenize(s)
            if not tokens:
                continue
            head = tokens[0].lower()
            if head == 'edit' and len(tokens) >= 2:
                cur = self._strip_quotes(tokens[1])
                current = {}
            elif head == 'set' and len(tokens) >= 3 and cur:
                key = tokens[1].lower()
                values = [self._strip_quotes(t) for t in tokens[2:]]
                if key in {'startip', 'endip', 'type'}:
                    current[key] = values[0]
                else:
                    current[key] = values if len(values) > 1 else values[0]
            elif head == 'next' and cur:
                self.ippools[cur] = current.copy()
                cur = None
        return i

    def _parse_central_snat(self, i: int) -> int:
        i, blk = self._parse_block(i)
        current: Dict[str, Union[str, List[str]]] = {}
        for line in blk:
            s = line.strip()
            if not s:
                continue
            tokens = self._tokenize(s)
            if not tokens:
                continue
            head = tokens[0].lower()
            if head == 'edit':
                current = {'seq': self._strip_quotes(tokens[1])} if len(tokens) >= 2 else {}
            elif head == 'set' and len(tokens) >= 3:
                key = tokens[1].lower()
                values = [self._strip_quotes(t) for t in tokens[2:]]
                current[key] = values if len(values) > 1 else values[0]
            elif head == 'next' and current:
                self.central_snat_map.append(current.copy())
                current = {}
        return i

    def _parse_policy(self, i: int) -> int:
        i, blk = self._parse_block(i)
        cur: Dict[str, Union[str, List[str], bool]] = {}
        for line in blk:
            s = line.strip()
            if not s:
                continue
            tokens = self._tokenize(s)
            if not tokens:
                continue
            head = tokens[0].lower()
            if head == 'edit' and len(tokens) >= 2:
                cur = {
                    'id': self._strip_quotes(tokens[1]),
                    'srcaddr': [],
                    'dstaddr': [],
                    'service': [],
                    'srcintf': [],
                    'dstintf': [],
                }
            elif head == 'set' and len(tokens) >= 3:
                key = tokens[1].lower()
                values = [self._strip_quotes(t) for t in tokens[2:]]
                if key == 'action' and values:
                    act = values[0].lower()
                    cur['action'] = 'permit' if act == 'accept' else 'deny'
                elif key == 'srcaddr':
                    cur['srcaddr'] = values
                elif key == 'dstaddr':
                    cur['dstaddr'] = values
                elif key == 'service':
                    cur['service'] = values
                elif key == 'srcintf':
                    cur['srcintf'] = values
                elif key == 'dstintf':
                    cur['dstintf'] = values
                elif key == 'schedule' and values:
                    cur['schedule'] = values[0]
                elif key == 'name' and values:
                    cur['name'] = values[0]
                elif key == 'uuid' and values:
                    cur['uuid'] = values[0]
                elif key == 'logtraffic' and values:
                    cur['logtraffic'] = values[0]
                elif key == 'nat' and values:
                    cur['nat'] = values[0].lower() == 'enable'
                elif key == 'ippool' and values:
                    cur['ippool'] = values[0].lower() == 'enable'
                elif key == 'poolname':
                    cur['poolname'] = values
                elif key == 'status' and values:
                    cur['status'] = values[0]
                elif key == 'comments' and values:
                    cur['comments'] = ' '.join(values)
            elif head == 'next':
                if cur:
                    self.policies.append(cur.copy())
                cur = {}
        return i

    # ---------- Resolution helpers ----------
    def _build_reverse_indexes(self) -> None:
        ip_to_objects: Dict[Union[ipaddress.IPv4Address, ipaddress.IPv4Network], Set[str]] = defaultdict(set)
        for name, nets in self.addresses.items():
            for n in nets:
                if isinstance(n, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                    ip_to_objects[n].add(name)
        self.ip_to_objects = dict(ip_to_objects)

    def resolve_addr_token(self, token: str, visited: Optional[Set[str]] = None) -> Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]]:
        if token.lower() in ('all',):
            return {ipaddress.ip_network('0.0.0.0/0')}
        if token in self.addresses:
            return self.addresses[token]
        if token in self.vips:
            literals: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]] = set()
            vip = self.vips[token]
            extips = vip.get('extip')
            if isinstance(extips, list):
                for ip in extips:
                    literals.add(to_ip_network(ip))
            elif isinstance(extips, str):
                literals.add(to_ip_network(extips))
            return literals
        if token in self.addrgrps:
            visited = set() if visited is None else visited
            if token in visited:
                return set()
            visited.add(token)
            out: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]] = set()
            for m in self.addrgrps[token]:
                if isinstance(m, dict) and 'object' in m:
                    out.update(self.resolve_addr_token(m['object'], visited))
                else:
                    out.add(m)
            return out
        if token in self.vipgrps:
            visited = set() if visited is None else visited
            if token in visited:
                return set()
            visited.add(token)
            out: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]] = set()
            for member in self.vipgrps[token]:
                out.update(self.resolve_addr_token(member, visited))
            return out
        return {token}

    def _collect_vip_names(self, token: str, visited: Optional[Set[str]] = None) -> Set[str]:
        visited = set() if visited is None else visited
        if token in visited:
            return set()
        visited.add(token)
        if token in self.vips:
            return {token}
        if token in self.vipgrps:
            names: Set[str] = set()
            for member in self.vipgrps[token]:
                names.update(self._collect_vip_names(member, visited))
            return names
        return set()

    def _split_ranges(self, spec: str) -> List[Tuple[Optional[int], Optional[int]]]:
        """Split FortiGate port range string like '80-81 443' into numeric ranges."""
        out: List[Tuple[Optional[int], Optional[int]]] = []
        for part in spec.split():
            if '-' in part:
                a, b = part.split('-', 1)
                p1 = int(a) if a.isdigit() else None
                p2 = int(b) if b.isdigit() else None
                out.append((p1, p2))
            else:
                out.append((int(part) if part.isdigit() else None, int(part) if part.isdigit() else None))
        return out

    def resolve_service_names(self, names: List[str]) -> dict:
        """Resolve a list of service names/groups to a unified svc dict.

        Returns dict with keys:
        - dst_ports: list of (op, (start,end)) where op='eq' or 'range'
        - dst_service_groups: referenced groups (optional informational)
        - proto: None (protocol implied by port tuple), informational only
        """
        dst_ports: List[Tuple[str, Tuple[Optional[int], Optional[int]]]] = []
        groups: Set[str] = set()
        for name in names:
            if name == 'ALL':
                return {"dst_ports": [], "dst_service_groups": set(), "proto": 'ip'}
            # Service group
            if name in self.service_groups:
                groups.add(name)
                for m in self.service_groups[name]:
                    sub = self.resolve_service_names([m])
                    dst_ports.extend(sub.get('dst_ports', []))
                continue
            spec = self.services.get(name)
            if spec:
                for proto in ('tcp', 'udp'):
                    for rng in spec.get(proto, []):
                        if rng[0] is not None and rng[1] is not None and rng[0] == rng[1]:
                            dst_ports.append(('eq', (rng[0], rng[1])))
                        else:
                            dst_ports.append(('range', (rng[0], rng[1])))
            else:
                # Try socket name resolution
                for proto in ('tcp', 'udp'):
                    try:
                        p = socket.getservbyname(name.lower(), proto)
                        dst_ports.append(('eq', (p, p)))
                        break
                    except Exception:
                        continue
        return {"dst_ports": dst_ports, "dst_service_groups": sorted(groups), "proto": None}

    # ---------- Flattening and evaluation ----------
    def flatten_policies(self) -> List[dict]:
        entries: List[dict] = []
        # Build VIP refs into a local map and rebind atomically at the end so a
        # concurrent reader of a shared/cached FTGConfig never observes a
        # half-populated dict (this method is idempotent and deterministic).
        policy_vip_refs: Dict[str, Set[str]] = defaultdict(set)
        for p in self.policies:
            srcs: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]] = set()
            dsts: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]] = set()
            vip_refs_for_policy: Set[str] = set()
            for token in p.get('srcaddr', []):
                srcs.update(self.resolve_addr_token(token))
            for token in p.get('dstaddr', []):
                dsts.update(self.resolve_addr_token(token))
                vip_refs_for_policy.update(self._collect_vip_names(token))
            svc = self.resolve_service_names(p.get('service', []))
            binding = {
                'srcintf': p.get('srcintf'),
                'dstintf': p.get('dstintf'),
                'schedule': p.get('schedule'),
                'uuid': p.get('uuid'),
                'name': p.get('name'),
            }
            policy_id = str(p.get('id')) if p.get('id') is not None else None
            src_zones = self._interfaces_to_zones(p.get('srcintf') or [])
            dst_zones = self._interfaces_to_zones(p.get('dstintf') or [])
            if src_zones:
                binding['srczone'] = src_zones
            if dst_zones:
                binding['dstzone'] = dst_zones
            if policy_id:
                binding['policy_id'] = policy_id
            if vip_refs_for_policy:
                binding['vip_refs'] = sorted(vip_refs_for_policy)
            binding = {k: v for k, v in binding.items() if v}
            raw = f"policy {p.get('id')} action {p.get('action','permit')} srcaddr {p.get('srcaddr',[])} dstaddr {p.get('dstaddr',[])} service {p.get('service',[])}"
            if policy_id:
                for vip_name in vip_refs_for_policy:
                    policy_vip_refs[vip_name].add(policy_id)
            entries.append({
                'acl': 'policy',
                'action': p.get('action', 'permit'),
                'proto': 'ip',
                'src': srcs,
                'dst': dsts,
                'svc': svc,
                'raw': raw,
                'binding': binding,
                'policy_id': p.get('id'),
                'nat': p.get('nat', False),
                'ippool': p.get('ippool', False),
                'poolname': p.get('poolname', []),
            })
        self.policy_vip_refs = policy_vip_refs
        return entries

    def _parse_static_routes(self, i: int) -> int:
        """Parse FortiGate static routes: config router static."""
        i, blk = self._parse_block(i)
        cur_route: Optional[dict] = None
        for line in blk:
            s = line.strip()
            if s.startswith('edit '):
                seq = s.split('edit', 1)[1].strip().strip('"')
                cur_route = {'seq': seq, 'destination': None, 'gateway': None, 'device': None, 'distance': None}
            elif s.startswith('set dst ') and cur_route:
                dst = s.split('set dst', 1)[1].strip()
                cur_route['destination'] = dst
            elif s.startswith('set gateway ') and cur_route:
                gw = s.split('set gateway', 1)[1].strip()
                cur_route['gateway'] = gw
            elif s.startswith('set device ') and cur_route:
                dev = s.split('set device', 1)[1].strip().strip('"')
                cur_route['device'] = dev
            elif s.startswith('set distance ') and cur_route:
                try:
                    dist = int(s.split('set distance', 1)[1].strip())
                    cur_route['distance'] = dist
                except ValueError:
                    pass
            elif s.startswith('next') and cur_route:
                if cur_route.get('destination'):
                    self.static_routes.append(cur_route.copy())
                cur_route = None
        return i

    def _parse_router_ospf(self, i: int) -> int:
        """Parse FortiGate OSPF config: config router ospf."""
        i, blk = self._parse_block(i)
        routing_config = {
            'protocol': 'ospf',
            'process_id': None,
            'router_id': None,
            'networks': [],
            'redistribute': [],
            'passive_interfaces': [],
            'areas': [],
            'areas_config': {},
            'timers': {},
            'authentication': {},
            'distance': {},
            'config': {},
        }

        j = 0
        while j < len(blk):
            line = blk[j]
            s = line.strip()

            if s.startswith('set router-id '):
                routing_config['router_id'] = s.split('set router-id', 1)[1].strip()
            elif s.startswith('set distance '):
                try:
                    routing_config['distance']['default'] = int(s.split('set distance', 1)[1].strip())
                except ValueError:
                    pass
            elif s.startswith('config passive-interface'):
                # Parse passive interface sub-block
                j += 1
                while j < len(blk) and (blk[j].startswith('    ') or blk[j].strip() == ''):
                    if not blk[j].strip():
                        j += 1
                        continue
                    ps = blk[j].strip()
                    if ps.startswith('edit '):
                        iface = ps.split('edit', 1)[1].strip().strip('"')
                        routing_config['passive_interfaces'].append(iface)
                        # Skip to next after the edit line
                        j += 1
                        while j < len(blk) and blk[j].startswith('        '):
                            if blk[j].strip() == 'next':
                                j += 1
                                break
                            j += 1
                        continue
                    elif ps == 'end':
                        break
                    j += 1
            elif s.startswith('config network'):
                # Parse network sub-block
                j += 1
                while j < len(blk) and (blk[j].startswith('    ') or blk[j].strip() == ''):
                    if not blk[j].strip():
                        j += 1
                        continue
                    ns = blk[j].strip()
                    if ns.startswith('edit '):
                        net_id = ns.split('edit', 1)[1].strip().strip('"')
                        net_entry = {'id': net_id}
                        j += 1
                        while j < len(blk) and blk[j].startswith('        '):
                            nns = blk[j].strip()
                            if nns.startswith('set prefix '):
                                net_entry['prefix'] = nns.split('set prefix', 1)[1].strip()
                            elif nns.startswith('set area '):
                                net_entry['area'] = nns.split('set area', 1)[1].strip()
                            elif nns == 'next':
                                # End of this edit block
                                j += 1
                                break
                            j += 1
                        routing_config['networks'].append(net_entry)
                        continue
                    elif ns == 'end':
                        break
                    j += 1
            elif s.startswith('config redistribute'):
                # Parse redistribute sub-block
                j += 1
                while j < len(blk) and (blk[j].startswith('    ') or blk[j].strip() == ''):
                    if not blk[j].strip():
                        j += 1
                        continue
                    rs = blk[j].strip()
                    if rs.startswith('edit '):
                        redis_source = rs.split('edit', 1)[1].strip().strip('"')
                        routing_config['redistribute'].append({'source': redis_source})
                    elif rs == 'end':
                        break
                    j += 1
            j += 1

        self.dynamic_routing['ospf'] = routing_config
        return i

    def _parse_router_bgp(self, i: int) -> int:
        """Parse FortiGate BGP config: config router bgp."""
        i, blk = self._parse_block(i)
        routing_config = {
            'protocol': 'bgp',
            'process_id': None,
            'router_id': None,
            'networks': [],
            'neighbors': [],
            'redistribute': [],
            'config': {},
        }

        j = 0
        while j < len(blk):
            line = blk[j]
            s = line.strip()

            if s.startswith('set as '):
                routing_config['process_id'] = s.split('set as', 1)[1].strip()
            elif s.startswith('set router-id '):
                routing_config['router_id'] = s.split('set router-id', 1)[1].strip()
            elif s.startswith('config neighbor'):
                # Parse neighbor sub-block
                j += 1
                while j < len(blk) and (blk[j].startswith('    ') or blk[j].strip() == ''):
                    if not blk[j].strip():
                        j += 1
                        continue
                    ns = blk[j].strip()
                    if ns.startswith('edit '):
                        neighbor_ip = ns.split('edit', 1)[1].strip().strip('"')
                        neighbor_entry = {'ip': neighbor_ip}
                        j += 1
                        while j < len(blk) and blk[j].startswith('        '):
                            nns = blk[j].strip()
                            if nns.startswith('set remote-as '):
                                neighbor_entry['remote_as'] = nns.split('set remote-as', 1)[1].strip()
                            elif nns == 'next':
                                # End of this edit block
                                j += 1
                                break
                            j += 1
                        routing_config['neighbors'].append(neighbor_entry)
                        continue
                    elif ns == 'end':
                        break
                    j += 1
            j += 1

        self.dynamic_routing['bgp'] = routing_config
        return i


def nets_overlap(set_a: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]], set_b: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]]) -> bool:
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


def _service_matches(entry: dict, svc_filter: Optional[dict]) -> bool:
    if not svc_filter:
        return True
    want_proto = svc_filter.get('proto')
    want_ports = svc_filter.get('dports') or set()
    if want_proto and want_proto not in {'ip', 'tcp', 'udp', 'icmp'}:
        return False
    if not want_ports:
        return True
    ports = entry.get('svc', {}).get('dst_ports', [])
    if not ports:
        return True
    for p in want_ports:
        for op, (start, end) in ports:
            if start is None and end is None:
                return True
            if start is not None and end is not None and start <= p <= end:
                return True
            if start is None and end is not None and p <= end:
                return True
            if start is not None and end is None and p >= start:
                return True
    return False


def load_fortigate_vdoms(text: str, target_vdom: Optional[str] = None) -> List[FTGConfig]:
    """Return FTGConfig instances for either all VDOMs or a named VDOM.

    If target_vdom is provided, only that VDOM is parsed (or an empty list if missing).
    If not provided and the config contains VDOMs, each VDOM is parsed separately.
    If no VDOM blocks are present, a single FTGConfig is returned.
    """
    raw_lines = [line.rstrip() for line in text.splitlines()]
    names = FTGConfig.list_vdom_names(raw_lines)
    configs: List[FTGConfig] = []
    if target_vdom:
        if target_vdom in names:
            configs.append(FTGConfig(text, vdom=target_vdom))
        return configs
    if names:
        for name in names:
            configs.append(FTGConfig(text, vdom=name))
        return configs
    return [FTGConfig(text, vdom=None)]
