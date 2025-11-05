"""FortiGate parser and evaluation helpers.

This module parses FortiOS configuration snippets (7.4/7.6 tested) relevant to
IPv4 policy evaluation and conversion to the shared intermediate
representation. Compared to the initial rudimentary draft, this version adds:

* VDOM-aware parsing – ``config vdom`` blocks are honoured and a caller may
  request a specific VDOM. If none is supplied the first non-empty VDOM is
  selected.
* Interface discovery from ``config system interface`` so policies can be tied
  back to the VDOM context when exporting to the IR.
* FortiOS 7.4/7.6 address and service enhancements (``iprange``, ``fqdn`` and
  explicit protocol hints).
* A :meth:`FTGConfig.to_ir` helper that maps FortiGate objects, groups and
  policies into :mod:`parsers.model` for cross-vendor comparisons.

Assumptions and scope
---------------------
* IPv4 only. IPv6 constructs are ignored for now.
* Time-ranges are out of scope per requirements.
* Service objects are resolved from ``service custom`` and ``service group``
  blocks where available; unknown names fall back to best-effort socket lookups
  or wildcard behaviour.
* Policy default action ``accept`` maps to ``permit`` (FortiOS ``deny`` maps to
  ``deny``).
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set, Tuple, Union

try:
    from parsers import model as ir
except Exception:  # pragma: no cover - optional dependency at import time
    ir = None  # type: ignore


def to_ip_network(ip: str, mask: Optional[str] = None) -> Union[ipaddress.IPv4Address, ipaddress.IPv4Network]:
    if mask is not None:
        return ipaddress.ip_network(f"{ip}/{mask}", strict=False)
    if "/" in ip:
        return ipaddress.ip_network(ip, strict=False)
    return ipaddress.ip_address(ip)


class FTGConfig:
    """Parsed representation of relevant FortiGate configuration."""

    def __init__(self, text: str, vdom: Optional[str] = None) -> None:
        """Initialise with raw config text and optional VDOM name."""

        self._raw_lines = [line.rstrip() for line in text.splitlines()]
        self.vdom = vdom
        self.version = self._detect_version(self._raw_lines)
        self.lines, self.active_vdom, self.available_vdoms = self._select_vdom_lines(
            self._raw_lines, vdom
        )
        self.interfaces_by_vdom = self._parse_global_interfaces(self._raw_lines)
        self.addresses: Dict[str, Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]]] = {}
        self.addrgrps: Dict[str, List[Union[dict, ipaddress.IPv4Address, ipaddress.IPv4Network, str]]] = {}
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
            if line.startswith('config system interface'):
                # Some VDOM dumps embed system interface blocks
                i = self._parse_vdom_interfaces(i + 1)
                continue
            i += 1

    def _select_vdom_lines(
        self, lines: List[str], want_vdom: Optional[str]
    ) -> Tuple[List[str], Optional[str], List[str]]:
        """Return lines belonging to the requested VDOM (if present)."""

        i = 0
        L = len(lines)
        seen: Dict[str, List[str]] = {}
        while i < L:
            s = lines[i].strip()
            if s.startswith('config vdom'):
                i += 1
                vdom_blocks: Dict[str, List[str]] = {}
                while i < L:
                    s2 = lines[i].strip()
                    if s2.startswith('edit '):
                        name = s2.split('edit', 1)[1].strip().strip('"')
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
                seen.update(vdom_blocks)
                if want_vdom:
                    block = vdom_blocks.get(want_vdom)
                    if block:
                        return block, want_vdom, sorted(vdom_blocks)
                else:
                    for key, block in vdom_blocks.items():
                        if block:
                            return block, key, sorted(vdom_blocks)
                continue
            i += 1
        if want_vdom and want_vdom in seen and seen[want_vdom]:
            return seen[want_vdom], want_vdom, sorted(seen)
        return lines, None, sorted(seen)

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
        start_ip = end_ip = None
        fqdn: Optional[str] = None
        addr_type = 'ipmask'
        for line in blk:
            s = line.strip()
            if s.startswith('edit '):
                cur = s.split('edit', 1)[1].strip().strip('"')
                subnet_ip = subnet_mask = None
                start_ip = end_ip = None
                fqdn = None
                addr_type = 'ipmask'
            elif s.startswith('set type '):
                addr_type = s.split('set type', 1)[1].strip().strip('"')
            elif s.startswith('set subnet '):
                parts = s.split()
                if len(parts) >= 4:
                    subnet_ip, subnet_mask = parts[2], parts[3]
            elif s.startswith('set start-ip '):
                parts = s.split()
                if len(parts) >= 3:
                    start_ip = parts[2]
            elif s.startswith('set end-ip '):
                parts = s.split()
                if len(parts) >= 3:
                    end_ip = parts[2]
            elif s.startswith('set fqdn '):
                fqdn = s.split('set fqdn', 1)[1].strip().strip('"')
            elif s.startswith('next') and cur:
                nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]] = set()
                if addr_type in ('ipmask', 'subnet', 'ipnet'):
                    if subnet_ip and subnet_mask:
                        nets.add(to_ip_network(subnet_ip, subnet_mask))
                    elif subnet_ip:
                        nets.add(to_ip_network(subnet_ip))
                elif addr_type == 'iprange' and start_ip and end_ip:
                    try:
                        start = ipaddress.ip_address(start_ip)
                        end = ipaddress.ip_address(end_ip)
                        for net in ipaddress.summarize_address_range(start, end):
                            nets.add(net)
                    except Exception:
                        pass
                elif addr_type == 'fqdn' and fqdn:
                    nets.add(f"fqdn:{fqdn}")
                elif subnet_ip and subnet_mask:
                    nets.add(to_ip_network(subnet_ip, subnet_mask))
                if fqdn and addr_type != 'fqdn':
                    nets.add(f"fqdn:{fqdn}")
                self.addresses[cur] = nets
                cur = None
        return i

    def _parse_addrgrp(self, i: int) -> int:
        i, blk = self._parse_block(i)
        cur: Optional[str] = None
        members: List[Union[dict, ipaddress.IPv4Address, ipaddress.IPv4Network, str]] = []
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
        tcp_range = udp_range = None
        proto_hint: Optional[str] = None
        for line in blk:
            s = line.strip()
            if s.startswith('edit '):
                cur = s.split('edit', 1)[1].strip().strip('"')
                tcp_range = udp_range = None
                proto_hint = None
            elif s.startswith('set tcp-portrange '):
                tcp_range = s.split('set tcp-portrange', 1)[1].strip()
            elif s.startswith('set udp-portrange '):
                udp_range = s.split('set udp-portrange', 1)[1].strip()
            elif s.startswith('set protocol '):
                proto_hint = s.split('set protocol', 1)[1].strip().strip('"').lower()
            elif s.startswith('set protocol-number '):
                proto_hint = s.split('set protocol-number', 1)[1].strip().lower()
            elif s.startswith('next') and cur:
                spec: Dict[str, Union[str, List[Tuple[Optional[int], Optional[int]]]]] = {}
                if tcp_range:
                    spec.setdefault('tcp', []).extend(self._split_ranges(tcp_range))
                if udp_range:
                    spec.setdefault('udp', []).extend(self._split_ranges(udp_range))
                if proto_hint:
                    spec['proto'] = proto_hint
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
                cur = {
                    'srcaddr': [],
                    'dstaddr': [],
                    'service': [],
                    'srcintf': [],
                    'dstintf': [],
                    'status': 'enable',
                    'policyid': s.split('edit', 1)[1].strip().strip('"'),
                }
            elif s.startswith('set action '):
                act = s.split()[-1].strip('"')
                cur['action'] = 'permit' if act == 'accept' else 'deny'
            elif s.startswith('set srcaddr '):
                cur['srcaddr'] = [x.strip('"') for x in s.split()[2:]]
            elif s.startswith('set dstaddr '):
                cur['dstaddr'] = [x.strip('"') for x in s.split()[2:]]
            elif s.startswith('set service '):
                cur['service'] = [x.strip('"') for x in s.split()[2:]]
            elif s.startswith('set srcintf '):
                cur['srcintf'] = [x.strip('"') for x in s.split()[2:]]
            elif s.startswith('set dstintf '):
                cur['dstintf'] = [x.strip('"') for x in s.split()[2:]]
            elif s.startswith('set schedule '):
                cur['schedule'] = s.split('set schedule', 1)[1].strip().strip('"')
            elif s.startswith('set status '):
                cur['status'] = s.split('set status', 1)[1].strip().strip('"')
            elif s.startswith('set name '):
                cur['name'] = s.split('set name', 1)[1].strip().strip('"')
            elif s.startswith('set nat '):
                cur['nat'] = s.split('set nat', 1)[1].strip().strip('"')
            elif s.startswith('next'):
                if cur:
                    self.policies.append(cur.copy())
                cur = {}
        return i

    def _parse_vdom_interfaces(self, i: int) -> int:
        """Parse ``config system interface`` inside a VDOM block."""

        i, blk = self._parse_block(i)
        cur: Optional[str] = None
        vdom_name = self.active_vdom or self.vdom or 'global'
        store = self.interfaces_by_vdom.setdefault(vdom_name, {})
        meta: Dict[str, Union[str, ipaddress.IPv4Interface]] = {}
        for line in blk:
            s = line.strip()
            if s.startswith('edit '):
                cur = s.split('edit', 1)[1].strip().strip('"')
                meta = {}
            elif s.startswith('set ip '):
                parts = s.split()
                ip_val = parts[2] if len(parts) >= 3 else None
                mask_val = parts[3] if len(parts) >= 4 else None
                if ip_val:
                    meta['ipv4'] = self._parse_interface_ip(ip_val, mask_val)
            elif s.startswith('set alias '):
                meta['alias'] = s.split('set alias', 1)[1].strip().strip('"')
            elif s.startswith('next') and cur:
                store[cur] = meta.copy()
                cur = None
        return i

    def _parse_global_interfaces(
        self, lines: List[str]
    ) -> Dict[str, Dict[str, Dict[str, Union[str, ipaddress.IPv4Interface]]]]:
        interfaces: Dict[str, Dict[str, Dict[str, Union[str, ipaddress.IPv4Interface]]]] = defaultdict(dict)
        i = 0
        L = len(lines)

        def parse_block(source: List[str], start: int) -> Tuple[int, List[str]]:
            acc: List[str] = []
            j = start
            while j < len(source):
                raw = source[j].rstrip()
                if raw.strip() == 'end':
                    return j + 1, acc
                acc.append(source[j])
                j += 1
            return j, acc

        while i < L:
            stripped = lines[i].strip()
            if stripped.startswith('config system interface'):
                i, block = parse_block(lines, i + 1)
                cur_name: Optional[str] = None
                cur_meta: Dict[str, Union[str, ipaddress.IPv4Interface]] = {}
                for raw in block:
                    s = raw.strip()
                    if s.startswith('edit '):
                        cur_name = s.split('edit', 1)[1].strip().strip('"')
                        cur_meta = {}
                    elif s.startswith('set vdom '):
                        cur_meta['vdom'] = s.split('set vdom', 1)[1].strip().strip('"')
                    elif s.startswith('set ip '):
                        parts = s.split()
                        ip_val = parts[2] if len(parts) >= 3 else None
                        mask_val = parts[3] if len(parts) >= 4 else None
                        if ip_val:
                            cur_meta['ipv4'] = self._parse_interface_ip(ip_val, mask_val)
                    elif s.startswith('set alias '):
                        cur_meta['alias'] = s.split('set alias', 1)[1].strip().strip('"')
                    elif s.startswith('next') and cur_name:
                        vdom_name = str(cur_meta.get('vdom') or 'global')
                        interfaces[vdom_name][cur_name] = cur_meta.copy()
                        cur_name = None
                continue
            i += 1
        return interfaces

    def _parse_interface_ip(
        self, ip_val: str, mask_val: Optional[str]
    ) -> Optional[ipaddress.IPv4Interface]:
        try:
            if mask_val:
                return ipaddress.ip_interface(f"{ip_val}/{mask_val}")
            return ipaddress.ip_interface(ip_val)
        except Exception:
            try:
                return ipaddress.ip_interface(ip_val.replace(' ', '/'))
            except Exception:
                return None

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

    def resolve_service_names(self, names: List[str], visited: Optional[Set[str]] = None) -> dict:
        dst_ports: List[Tuple[str, Tuple[Optional[int], Optional[int]]]] = []
        groups: Set[str] = set()
        service_objects: Set[str] = set()
        proto: Optional[str] = None
        visited = set() if visited is None else set(visited)
        for name in names:
            if name == 'ALL':
                return {
                    "dst_ports": [],
                    "dst_service_groups": set(),
                    "dst_service_objects": set(),
                    "proto": 'ip',
                }
            if name in self.service_groups:
                if name in visited:
                    continue
                visited.add(name)
                groups.add(name)
                for m in self.service_groups[name]:
                    sub = self.resolve_service_names([m], visited)
                    dst_ports.extend(sub.get('dst_ports', []))
                    groups.update(sub.get('dst_service_groups', set()))
                    service_objects.update(sub.get('dst_service_objects', set()))
                    if not proto:
                        proto = sub.get('proto')
                visited.discard(name)
                continue
            spec = self.services.get(name)
            if spec:
                service_objects.add(name)
                if not proto and spec.get('proto'):
                    proto = spec.get('proto')
                for proto_name in ('tcp', 'udp'):
                    for rng in spec.get(proto_name, []):
                        if rng[0] is not None and rng[1] is not None and rng[0] == rng[1]:
                            dst_ports.append(('eq', (rng[0], rng[1])))
                        else:
                            dst_ports.append(('range', (rng[0], rng[1])))
            else:
                for proto_name in ('tcp', 'udp'):
                    try:
                        p = socket.getservbyname(name.lower(), proto_name)
                        dst_ports.append(('eq', (p, p)))
                        service_objects.add(name)
                        break
                    except Exception:
                        continue
        return {
            "dst_ports": dst_ports,
            "dst_service_groups": groups,
            "dst_service_objects": service_objects,
            "proto": proto,
        }

    # ---------- Flattening and evaluation ----------
    def flatten_policies(self) -> List[dict]:
        entries: List[dict] = []
        for p in self.policies:
            if p.get('status', 'enable') == 'disable':
                continue
            srcs: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]] = set()
            dsts: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]] = set()
            for token in p.get('srcaddr', []):
                srcs.update(self.resolve_addr_token(token))
            for token in p.get('dstaddr', []):
                dsts.update(self.resolve_addr_token(token))
            svc = self.resolve_service_names(p.get('service', []))
            policy_name = p.get('name') or p.get('policyid')
            raw = (
                f"policy {policy_name} action {p.get('action', 'permit')} srcaddr {p.get('srcaddr', [])} "
                f"dstaddr {p.get('dstaddr', [])} service {p.get('service', [])}"
            )
            binding = {
                'srcintf': p.get('srcintf', []),
                'dstintf': p.get('dstintf', []),
                'schedule': p.get('schedule'),
                'nat': p.get('nat'),
                'policyid': p.get('policyid'),
                'name': p.get('name'),
            }
            bound_to = None
            if binding['srcintf'] or binding['dstintf']:
                bound_to = 'src:{} dst:{}'.format(
                    ','.join(binding['srcintf'] or ['any']),
                    ','.join(binding['dstintf'] or ['any']),
                )
            entries.append(
                {
                    'acl': 'policy',
                    'action': p.get('action', 'permit'),
                    'proto': svc.get('proto') or 'ip',
                    'src': srcs,
                    'dst': dsts,
                    'svc': svc,
                    'raw': raw,
                    'binding': binding,
                    'bound_to': bound_to,
                }
            )
        return entries

    # ---------- IR export ----------
    def to_ir(self, device_name: Optional[str] = None) -> "ir.Device":
        if ir is None:
            raise RuntimeError("IR module not available")

        version = self.version or 'unknown'
        name = device_name or self.active_vdom or 'fortigate'
        interfaces: List[ir.Interface] = []
        vdom_key = self.active_vdom or self.vdom or 'global'
        for iface_name, meta in sorted(self.interfaces_by_vdom.get(vdom_key, {}).items()):
            ipv4 = meta.get('ipv4')
            interfaces.append(
                ir.Interface(
                    name=iface_name,
                    physical=None,
                    ipv4=str(ipv4) if ipv4 else None,
                    security_level=None,
                )
            )

        objects: List[ir.Object] = []
        for name_key, nets in sorted(self.addresses.items()):
            literals: List[str] = []
            for n in nets:
                try:
                    literals.append(str(n))
                except Exception:
                    pass
            objects.append(ir.Object(name=name_key, literals=sorted(literals)))

        groups: List[ir.Group] = []
        for name_key, members in sorted(self.addrgrps.items()):
            items: List[ir.GroupMember] = []
            for m in members:
                if isinstance(m, dict) and 'object' in m:
                    items.append(ir.GroupMember(kind='object', ref=m['object']))
                elif isinstance(m, dict) and 'group' in m:
                    items.append(ir.GroupMember(kind='group', ref=m['group']))
                else:
                    items.append(ir.GroupMember(kind='literal', literal=str(m)))
            groups.append(ir.Group(name=name_key, members=items))

        svc_groups: List[ir.ServiceGroup] = []
        for name_key, members in sorted(self.service_groups.items()):
            svc_groups.append(
                ir.ServiceGroup(
                    name=name_key,
                    members=[{'object': m} for m in sorted(members)],
                )
            )

        flattened = self.flatten_policies()
        acl_entries: List[ir.ACLEntry] = []
        for entry in flattened:
            svc = entry.get('svc') or {}
            svc_norm = {
                'proto': svc.get('proto'),
                'dst_ports': [
                    {'op': op, 'start': rng[0], 'end': rng[1]}
                    for (op, rng) in svc.get('dst_ports', [])
                ],
                'dst_service_groups': sorted(list(svc.get('dst_service_groups') or [])),
                'dst_service_objects': sorted(list(svc.get('dst_service_objects') or [])),
            }
            src = sorted(str(s) for s in entry.get('src', []))
            dst = sorted(str(d) for d in entry.get('dst', []))
            acl_entries.append(
                ir.ACLEntry(
                    action=entry.get('action'),
                    proto=entry.get('proto'),
                    src=src,
                    dst=dst,
                    svc=svc_norm,
                    raw=entry.get('raw'),
                    acl=entry.get('acl'),
                    bound_to=entry.get('bound_to'),
                    binding=entry.get('binding'),
                )
            )

        ir_acls = [ir.ACL(name='policy', bound_to=None, entries=acl_entries, binding=None)]

        device = ir.Device(
            vendor='fortigate',
            os='FortiOS',
            version=version,
            name=name,
            interfaces=interfaces,
            objects=objects,
            groups=groups,
            service_groups=svc_groups,
            acls=ir_acls,
        )
        return device

    # ---------- Metadata ----------
    def _detect_version(self, lines: Iterable[str]) -> Optional[str]:
        version_re = re.compile(r"config-version=.+?-([0-9]+\.[0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
        for line in lines:
            m = version_re.search(line)
            if m:
                return m.group(1)
            m2 = re.search(r"#\s*FortiGate\s+Version\s+([0-9]+\.[0-9]+(?:\.[0-9]+)?)", line, re.IGNORECASE)
            if m2:
                return m2.group(1)
        return None


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
