"""Cisco ASA parser and evaluation helpers.

This module encapsulates parsing of Cisco ASA configuration constructs relevant
to ACL impact analysis. It resolves network objects and object-groups into
concrete IPv4 primitives, tokenizes ACL lines into a normalized shape, and
provides evaluation helpers for inspecting and comparing rule impact.

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
from typing import Dict, List, Optional, Set, Tuple, Union


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
    """Convert ASA-style IP/mask or host representations to ipaddress objects.

    Behavior:
    - If mask is provided (dotted or prefix), returns IPv4Network with strict=False.
    - If IP contains '/', returns IPv4Network with strict=False.
    - Otherwise returns IPv4Address.
    Raises ValueError for invalid inputs.
    """
    if mask is not None:
        return ipaddress.ip_network(f"{ip}/{mask}", strict=False)
    if "/" in ip:
        return ipaddress.ip_network(ip, strict=False)
    return ipaddress.ip_address(ip)


class ASAConfig:
    """Holds parsed objects, groups, and ACLs for a single ASA config text.

    Public attributes:
    - network_objects: Dict[str, Set[IPv4Address|IPv4Network]]
    - network_object_groups: Dict[str, List[Union[IPv4*, {object/group-object}]]]
    - service_object_groups: Dict[str, List[spec or group-ref]] (if present)
    - acls: Dict[str, List[str]] raw ACL lines by ACL name
    - ip_to_objects: Reverse index of exact primitives to object names
    """

    def __init__(self, text: str) -> None:
        self.lines = [l.rstrip() for l in text.splitlines()]
        self.network_objects: Dict[str, Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]] = {}
        self.network_object_groups: Dict[str, List[Union[dict, ipaddress.IPv4Address, ipaddress.IPv4Network]]] = {}
        self.acls: Dict[str, List[str]] = defaultdict(list)
        self.parse()
        self._build_reverse_indexes()

    def _consume_endpoint(self, tokens: List[str]) -> Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]:
        """Consume tokens to parse a single ASA endpoint (src or dst).

        Supported forms:
        - host <ip>
        - object <name>
        - object-group <name>
        - any, any4, any6
        - <ip> <mask>  (or <ip>[/prefix])

        Returns set of IPv4Address/IPv4Network primitives.
        """
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

        # Otherwise treat as IP[/mask] possibly followed by dotted mask
        mask = None
        if tokens and '.' in tokens[0]:
            mask = tokens.pop(0)
        nets.add(to_ip_network(tok, mask))
        return nets

    def _port_from_token(self, tok: str, proto_hint: Optional[str] = None) -> Optional[int]:
        """Convert a port token (number or name) to an integer if possible.

        Resolution order:
        - Fast-path numeric
        - socket.getservbyname(token, proto_hint)
        - socket.getservbyname(token, 'tcp' then 'udp')
        Returns None if resolution fails.
        """
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
        """Parse the trailing service/port segment after destination endpoint.

        Supported patterns:
        - eq/lt/gt/neq <port>
        - range <start> <end>
        - object-group <name>
        - object <name>  (service object)

        Returns a dict understood by evaluation/formatting with keys:
        - dst_ports: list[(op, (start,end))]
        - dst_ops: set[str]
        - dst_service_groups: set[str]
        - dst_service_objects: set[str]
        """
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
        """Parse the ASA configuration lines into objects, groups, and ACL lists."""
        i = 0
        L = len(self.lines)
        while i < L:
            line = self.lines[i]
            m = re_object.match(line)
            if m:
                name = m.group('name')
                nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]] = set()
                i += 1
                while i < L and self.lines[i].startswith(' '):
                    lm = re_object_network_host.match(self.lines[i])
                    if lm:
                        nets.add(to_ip_network(lm.group('ip')))
                    else:
                        lm2 = re_object_network_subnet.match(self.lines[i])
                        if lm2:
                            nets.add(to_ip_network(lm2.group('ip'), lm2.group('mask')))
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
                            members.append(to_ip_network(m_host.group('ip')))
                        elif m_subnet:
                            members.append(to_ip_network(m_subnet.group('ip'), m_subnet.group('mask')))
                        elif m_obj:
                            members.append({'object': m_obj.group('name')})
                        elif m_group:
                            members.append({'group-object': m_group.group('name')})
                    elif typ == 'service':
                        # Parse service object-groups with basic ops and nested groups
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
                self.acls[macl.group('name')].append(line)
                i += 1
                continue
            i += 1

    def _build_reverse_indexes(self) -> None:
        """Build reverse indexes for exact primitive -> object names.

        Used to surface duplicate network-objects mapping to the same address/network.
        """
        ip_to_objects: Dict[Union[ipaddress.IPv4Address, ipaddress.IPv4Network], Set[str]] = defaultdict(set)
        for name, nets in self.network_objects.items():
            for n in nets:
                if isinstance(n, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                    ip_to_objects[n].add(name)
        self.ip_to_objects = dict(ip_to_objects)

    def resolve_service_group(self, name: str, visited: Optional[Set[str]] = None) -> List[dict]:
        """Resolve a service object-group name into a list of specs.

        Spec: {'proto': str, 'op': str|None, 'v1': str|None, 'v2': str|None} or
        {'object': name} for unresolved service objects.
        """
        if not hasattr(self, 'service_object_groups'):
            return []
        if visited is None:
            visited = set()
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
        return out

    def resolve_network(self, token: Union[str, ipaddress.IPv4Address, ipaddress.IPv4Network], visited: Optional[Set[str]] = None) -> Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]]:
        """Resolve a token to a set of IPv4 primitives.

        Accepts:
        - IPv4Address/IPv4Network: returns singleton set
        - 'any'/'any4' => 0.0.0.0/0, 'any6' => ::/0 (ignored in IPv4 flows)
        - Object/group names: resolves with recursion protection
        - IP strings: parsed into primitives
        - Unknown strings: returned as-is to avoid crashes
        """
        visited = set() if visited is None else visited
        results: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]] = set()
        if isinstance(token, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
            return {token}
        token_lower = token.lower() if isinstance(token, str) else token
        if token_lower in ('any', 'any4', 'any-ipv4'):
            return {ipaddress.ip_network('0.0.0.0/0')}
        if token_lower in ('any6', 'any-ipv6'):
            try:
                return {ipaddress.ip_network('::/0')}
            except Exception:
                return set()
        if isinstance(token, str) and token in self.network_objects:
            return self.network_objects[token]
        if isinstance(token, str) and token in self.network_object_groups:
            if token in visited:
                return set()
            visited.add(token)
            for m in self.network_object_groups[token]:
                if isinstance(m, dict):
                    if 'group-object' in m:
                        results.update(self.resolve_network(m['group-object'], visited))
                    elif 'object' in m:
                        results.update(self.resolve_network(m['object'], visited))
                else:
                    results.add(m)
            return results
        try:
            return {to_ip_network(token)}
        except Exception:
            return {token}

    def find_alias_objects(self, target: Union[str, ipaddress.IPv4Address, ipaddress.IPv4Network], target_nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]) -> Dict[Union[ipaddress.IPv4Address, ipaddress.IPv4Network], Set[str]]:
        """Return mapping of address/network -> other object names that map to it.

        Only considers exact primitives (no containment). Excludes the target's
        own object name if the target was an object.
        """
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
        """Produce a list of flattened ACL entries with src/dst/service details.

        Each entry is a dict containing:
        - acl, action, proto (raw token), src, dst, svc (service details), raw
        The 'svc' sub-dict includes parsed protocol/service-group info and
        tail-based port constraints.
        """
        entries: List[dict] = []
        for acl_name, lines in self.acls.items():
            for ln in lines:
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
                entries.append({'acl': acl_name, 'action': action, 'proto': proto, 'src': srcs, 'dst': dsts, 'svc': {**entry_svc, **svc_tail}, 'raw': ln.strip()})
        return entries


# ------------------- Evaluation helpers -------------------

def nets_overlap(set_a: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]], set_b: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]]) -> bool:
    """Return True if any network/address in set_a overlaps with any in set_b.

    Unknown string tokens are ignored.
    """
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


def _entry_effective_protos(cfg: ASAConfig, entry: dict) -> Set[str]:
    svc = entry.get('svc') or {}
    protos: Set[str] = set()
    if svc.get('proto') in {'ip', 'tcp', 'udp', 'icmp'}:
        protos.add(svc['proto'])
    sg = svc.get('service_group_at_proto')
    if sg and sg.get('kind') == 'object-group' and hasattr(cfg, 'service_object_groups'):
        name = sg.get('name')
        for spec in cfg.resolve_service_group(name):
            if 'proto' in spec:
                protos.add(spec['proto'])
    if entry.get('proto') in {'ip', 'tcp', 'udp', 'icmp'}:
        protos.add(entry['proto'])
    return protos or {'ip'}


def _spec_to_range_tuple(cfg: ASAConfig, spec: dict) -> Optional[Tuple[Optional[int], Optional[int]]]:
    op = spec.get('op')
    if not op:
        return (None, None)
    v1 = spec.get('v1')
    v2 = spec.get('v2')
    p1 = cfg._port_from_token(v1, spec.get('proto')) if v1 else None
    p2 = cfg._port_from_token(v2, spec.get('proto')) if v2 else None
    if op == 'range':
        return (p1, p2)
    if op == 'eq':
        return (p1, p1)
    if op == 'lt':
        return (0, (p1 - 1) if (p1 is not None and p1 > 0) else None)
    if op == 'gt':
        return ((p1 + 1) if p1 is not None else None, 65535)
    if op == 'neq':
        return (None, None)
    return None


def _dst_ports_from_entry(cfg: ASAConfig, entry: dict) -> List[Tuple[str, str, Tuple[Optional[int], Optional[int]]]]:
    svc = entry.get('svc') or {}
    ports: List[Tuple[str, str, Tuple[Optional[int], Optional[int]]]] = []
    for op, rng in svc.get('dst_ports', []):
        for p in _entry_effective_protos(cfg, entry):
            ports.append((p, op, rng))
    for g in svc.get('dst_service_groups', set()):
        for spec in cfg.resolve_service_group(g):
            rng = _spec_to_range_tuple(cfg, spec)
            if rng is not None:
                ports.append((spec['proto'], spec.get('op') or 'eq', rng))
    sg = svc.get('service_group_at_proto')
    if sg and sg.get('kind') == 'object-group':
        for spec in cfg.resolve_service_group(sg.get('name')):
            rng = _spec_to_range_tuple(cfg, spec)
            if rng is not None:
                ports.append((spec['proto'], spec.get('op') or 'eq', rng))
    return ports


def _service_matches(cfg: ASAConfig, entry: dict, svc_filter: Optional[dict]) -> bool:
    """Return True if entry matches an optional service filter.

    svc_filter: {'proto': Optional[str], 'dports': Set[int]}
    - If None: always True
    - If filter has 'proto': entry must allow that proto (or be 'ip')
    - If filter has 'dports': entry must allow at least one of those ports
    """
    if not svc_filter:
        return True
    want_proto = svc_filter.get('proto')
    want_ports = svc_filter.get('dports') or set()
    entry_protos = _entry_effective_protos(cfg, entry)
    if want_proto and want_proto not in entry_protos and 'ip' not in entry_protos:
        return False
    if not want_ports:
        return True
    port_specs = _dst_ports_from_entry(cfg, entry)
    if not port_specs:
        return True
    for p in want_ports:
        for eproto, op, (start, end) in port_specs:
            if want_proto and eproto not in {want_proto, 'ip'}:
                continue
            if start is None and end is None:
                return True
            if start is not None and end is not None and start <= p <= end:
                return True
            if start is None and end is not None and p <= end:
                return True
            if start is not None and end is None and p >= start:
                return True
    return False


def evaluate_acl(entries: List[dict], target_nets: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network, str]], cfg: Optional[ASAConfig] = None, service_filter: Optional[dict] = None) -> List[dict]:
    """Return all ACL entries that affect the target networks.

    - Matches by IP overlap. If service_filter is provided, also filter by
      protocol and destination ports. cfg is required when service_filter is used.
    """
    affected: List[dict] = []
    for e in entries:
        if nets_overlap(e['src'], target_nets) or nets_overlap(e['dst'], target_nets):
            if service_filter:
                if cfg is None:
                    continue
                if not _service_matches(cfg, e, service_filter):
                    continue
            affected.append(e)
    return affected


# ------------------- Inspect / Compare helpers -------------------

def compare_old_new(cfg_text: str, old_target: str, new_target: str, service_filter: Optional[dict] = None) -> dict:
    """Compare ACL impact between two targets (old -> new).

    Returns a dict with keys:
    - old_hits, new_hits: lists of matching entries for each target
    - added_to_new: rules present in new_hits but not in old_hits (by raw identity)
    - removed_from_old: rules present in old_hits but not in new_hits
    """
    cfg = ASAConfig(cfg_text)
    old_nets = cfg.resolve_network(old_target)
    new_nets = cfg.resolve_network(new_target)
    entries = cfg.flatten_acl()
    old_hits = evaluate_acl(entries, old_nets, cfg, service_filter=service_filter)
    new_hits = evaluate_acl(entries, new_nets, cfg, service_filter=service_filter)
    rule_id = lambda e: e['raw']
    old_ids = {rule_id(e) for e in old_hits}
    new_ids = {rule_id(e) for e in new_hits}
    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids
    added_to_new = [e for e in new_hits if rule_id(e) in added_ids]
    removed_from_old = [e for e in old_hits if rule_id(e) in removed_ids]
    return {'old_hits': old_hits, 'new_hits': new_hits, 'added_to_new': added_to_new, 'removed_from_old': removed_from_old}


def inspect_host(cfg_text: str, target: str, service_filter: Optional[dict] = None) -> dict:
    """Inspect all ACL entries affecting a single target.

    Returns a dict with keys:
    - hits: list of flattened entries matching the target
    - target_nets: set of resolved address/network primitives
    - aliases: mapping from primitive to object names that also resolve to it
    """
    cfg = ASAConfig(cfg_text)
    target_nets = cfg.resolve_network(target)
    entries = cfg.flatten_acl()
    hits = evaluate_acl(entries, target_nets, cfg, service_filter=service_filter)
    aliases = cfg.find_alias_objects(target, target_nets)
    return {'hits': hits, 'target_nets': target_nets, 'aliases': aliases}

