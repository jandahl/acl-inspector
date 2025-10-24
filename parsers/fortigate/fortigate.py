"""FortiGate parser and evaluation helpers (rudimentary).

This module parses a subset of FortiOS configuration relevant to IPv4 policy
evaluation and object resolution:

- config firewall address / addrgrp
- config firewall policy (IPv4)
- config firewall service custom / group

Assumptions and scope
---------------------
- IPv4 only. VDOM-awareness is not implemented yet; parsing is global.
- Time-ranges are out of scope per requirements.
- Service objects are resolved from 'service custom' and 'service group' blocks
  where available; unknown names fall back to best-effort (socket name lookup)
  or wildcard behavior.
- Policy default action 'accept' maps to 'permit', 'deny' to 'deny'.

The flattened rule structure matches parsers.cisco.asa output to enable
cross-vendor compare at the CLI level.
"""

from __future__ import annotations

import ipaddress
import re
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

    def __init__(self, text: str) -> None:
        self.lines = [l.rstrip() for l in text.splitlines()]
        self.addresses: Dict[str, Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]] = {}
        self.addrgrps: Dict[str, List[Union[dict, ipaddress.IPv4Address, ipaddress.IPv4Network]]] = {}
        self.services: Dict[str, dict] = {}
        self.service_groups: Dict[str, Set[str]] = {}
        self.policies: List[dict] = []
        self._parse()
        self._build_reverse_indexes()

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
            i += 1

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

    def _parse_service_custom(self, i: int) -> int:
        i, blk = self._parse_block(i)
        cur: Optional[str] = None
        proto = None
        tcp_range = udp_range = None
        for line in blk:
            s = line.strip()
            if s.startswith('edit '):
                cur = s.split('edit', 1)[1].strip().strip('"')
                proto = None
                tcp_range = udp_range = None
            elif s.startswith('set tcp-portrange '):
                proto = 'tcp'
                tcp_range = s.split('set tcp-portrange', 1)[1].strip()
            elif s.startswith('set udp-portrange '):
                proto = 'udp'
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

    def _parse_policy(self, i: int) -> int:
        i, blk = self._parse_block(i)
        cur: Dict[str, Union[str, List[str]]] = {}
        for line in blk:
            s = line.strip()
            if s.startswith('edit '):
                cur = {'srcaddr': [], 'dstaddr': [], 'service': []}
            elif s.startswith('set action '):
                act = s.split()[-1].strip('"')
                cur['action'] = 'permit' if act == 'accept' else 'deny'
            elif s.startswith('set srcaddr '):
                cur['srcaddr'] = [x.strip('"') for x in s.split()[2:]]
            elif s.startswith('set dstaddr '):
                cur['dstaddr'] = [x.strip('"') for x in s.split()[2:]]
            elif s.startswith('set service '):
                cur['service'] = [x.strip('"') for x in s.split()[2:]]
            elif s.startswith('next'):
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
        return {token}

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
        return {"dst_ports": dst_ports, "dst_service_groups": groups, "proto": None}

    # ---------- Flattening and evaluation ----------
    def flatten_policies(self) -> List[dict]:
        entries: List[dict] = []
        for p in self.policies:
            srcs: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]] = set()
            dsts: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]] = set()
            for token in p.get('srcaddr', []):
                srcs.update(self.resolve_addr_token(token))
            for token in p.get('dstaddr', []):
                dsts.update(self.resolve_addr_token(token))
            svc = self.resolve_service_names(p.get('service', []))
            raw = f"policy action {p.get('action','permit')} srcaddr {p.get('srcaddr',[])} dstaddr {p.get('dstaddr',[])} service {p.get('service',[])}"
            entries.append({'acl': 'policy', 'action': p.get('action', 'permit'), 'proto': 'ip', 'src': srcs, 'dst': dsts, 'svc': svc, 'raw': raw})
        return entries


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


def evaluate(entries: List[dict], target_nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]], svc_filter: Optional[dict] = None) -> List[dict]:
    out: List[dict] = []
    for e in entries:
        if nets_overlap(e['src'], target_nets) or nets_overlap(e['dst'], target_nets):
            if not _service_matches(e, svc_filter):
                continue
            out.append(e)
    return out


def compare_old_new(cfg_text: str, old_target: str, new_target: str, service_filter: Optional[dict] = None) -> dict:
    cfg = FTGConfig(cfg_text)
    old_nets = cfg.resolve_addr_token(old_target)
    new_nets = cfg.resolve_addr_token(new_target)
    entries = cfg.flatten_policies()
    old_hits = evaluate(entries, old_nets, service_filter)
    new_hits = evaluate(entries, new_nets, service_filter)
    rule_id = lambda e: e['raw']
    old_ids = {rule_id(e) for e in old_hits}
    new_ids = {rule_id(e) for e in new_hits}
    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids
    added_to_new = [e for e in new_hits if rule_id(e) in added_ids]
    removed_from_old = [e for e in old_hits if rule_id(e) in removed_ids]
    return {'old_hits': old_hits, 'new_hits': new_hits, 'added_to_new': added_to_new, 'removed_from_old': removed_from_old}


def inspect_host(cfg_text: str, target: str, service_filter: Optional[dict] = None) -> dict:
    cfg = FTGConfig(cfg_text)
    target_nets = cfg.resolve_addr_token(target)
    entries = cfg.flatten_policies()
    hits = evaluate(entries, target_nets, service_filter)
    aliases = {}
    for n in target_nets:
        if not isinstance(n, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
            continue
        names = cfg.ip_to_objects.get(n, set())
        if names:
            aliases[n] = names
    return {'hits': hits, 'target_nets': target_nets, 'aliases': aliases}

