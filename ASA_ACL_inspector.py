#!/usr/bin/env python3
"""
ASA ACL diff by IP/object

This version:
- Parses a single ASA config (backup or live)
- Accepts a 'old' and 'new' IP or object name for comparison, or a single target for inspection
- Resolves ACLs affecting each target
- Shows differences or a detailed inspection report
- Uses a proper state machine for ACL evaluation
- Leverages the ipaddress module for network calculations
- CLI friendly, designed for future web integration
"""

import argparse
import re
import sys
import ipaddress
from collections import defaultdict
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
import socket

# ------------------- Parsing helpers -------------------

re_object = re.compile(r"^object(?: network)?\s+(?P<name>\S+)", re.IGNORECASE)
re_object_network_host = re.compile(r"^\s*host\s+(?P<ip>\S+)", re.IGNORECASE)
re_object_network_subnet = re.compile(r"^\s*(?:subnet|network)\s+(?P<ip>\S+)\s+(?P<mask>\S+)", re.IGNORECASE)

re_object_group = re.compile(r"^object-group\s+(?P<type>network|service)\s+(?P<name>\S+)", re.IGNORECASE)
re_group_network_object = re.compile(r"^\s*network-object\s+object\s+(?P<name>\S+)", re.IGNORECASE)

# Additional patterns for network-object lines inside object-groups
re_group_network_host = re.compile(r"^\s*network-object\s+host\s+(?P<ip>\S+)", re.IGNORECASE)
re_group_network_subnet = re.compile(r"^\s*network-object\s+(?!object\b)(?!host\b)(?P<ip>\S+)\s+(?P<mask>\S+)", re.IGNORECASE)
re_group_network_groupobj = re.compile(r"^\s*group-object\s+(?P<name>\S+)", re.IGNORECASE)

# ACL line matcher and tokenization for the rest of the line
re_acl = re.compile(
    r"^access-list\s+(?P<name>\S+)\s+extended\s+(?P<action>permit|deny)\s+(?P<rest>.*)$",
    re.IGNORECASE,
)
re_tokenized = re.compile(r"\S+")


def to_ip_network(ip: str, mask: str = None):
    """Convert ASA-style IP/mask or host representations to ipaddress objects.

    - If mask is provided, return an IPv4Network with that mask (dotted or prefix).
    - If ip contains a '/', parse as a network (strict=False to allow host bits).
    - Otherwise, return an IPv4Address.
    """
    if mask is not None:
        return ipaddress.ip_network(f"{ip}/{mask}", strict=False)
    if "/" in ip:
        return ipaddress.ip_network(ip, strict=False)
    return ipaddress.ip_address(ip)
# ... (rest of the file content up to the parse method)

class ASAConfig:
    def __init__(self, text):
        self.lines = [l.rstrip() for l in text.splitlines()]
        self.network_objects = {}
        self.network_object_groups = {}
        self.acls = defaultdict(list)
        self.parse()
        self._build_reverse_indexes()

    def _consume_endpoint(self, tokens):
        """Consume tokens to parse a single ASA endpoint (src or dst).

        Supported forms:
        - host <ip>
        - object <name>
        - object-group <name>
        - any
        - <ip> <mask>  (or <ip>[/prefix])
        """
        nets = set()
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

    def _port_from_token(self, tok, proto_hint=None):
        """Convert a port token (number or name) to an integer if possible.
        Falls back to None if resolution fails."""
        # Fast path: number
        if tok.isdigit():
            try:
                return int(tok)
            except Exception:
                return None
        # Named service, try socket.getservbyname with hint
        if proto_hint in ("tcp", "udp"):
            try:
                return socket.getservbyname(tok, proto_hint)
            except Exception:
                return None
        # Try tcp then udp
        for p in ("tcp", "udp"):
            try:
                return socket.getservbyname(tok, p)
            except Exception:
                continue
        return None

    def _consume_service_tail(self, tokens, proto_hint):
        """Parse trailing service/port spec after dst endpoint.

        Supports:
        - eq/lt/gt/neq <port>
        - range <start> <end>
        - object-group <name>
        - object <name> (service object)

        Returns dict with keys: 'dst_ports' (list of (start,end)), 'dst_ops' (set of ops),
        'dst_service_groups' (set), 'dst_service_objects' (set).
        """
        dst_ports = []
        dst_ops = set()
        dst_service_groups = set()
        dst_service_objects = set()

        while tokens:
            t = tokens[0].lower()
            if t in {"eq", "lt", "gt", "neq"}:
                tokens.pop(0)
                if not tokens:
                    break
                v = tokens.pop(0)
                port = self._port_from_token(v, proto_hint)
                if port is not None:
                    # Represent single-port as range (port, port)
                    dst_ports.append((t, (port, port)))
                    dst_ops.add(t)
                else:
                    # Unresolvable name; keep raw marker with None
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
                # Unknown tail token; stop parsing service portion to avoid eating next ACL
                break

        return {
            "dst_ports": dst_ports,
            "dst_ops": dst_ops,
            "dst_service_groups": dst_service_groups,
            "dst_service_objects": dst_service_objects,
        }

    def parse(self):
        i = 0
        L = len(self.lines)
        while i < L:
            line = self.lines[i]
            m = re_object.match(line)
            if m:
                name = m.group('name')
                nets = set()
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
                            captured_name = m_obj.group('name')
                            assert captured_name != 'object', f"Captured 'object' as name: {ln}"
                            members.append({'object': captured_name})
                        elif m_group:
                            members.append({'group-object': m_group.group('name')})
                    elif typ == 'service':
                        # Support basic service-group parsing: service-object tcp/udp <op> <ports>, and group nesting
                        m_group = re_group_network_groupobj.match(ln)
                        if m_group:
                            members.append({'group-object': m_group.group('name')})
                        else:
                            # service-object tcp|udp (eq|lt|gt|neq|range) <vals>
                            m = re.match(r"^\s*service-object\s+(tcp|udp|icmp|ip)(?:\s+(eq|lt|gt|neq|range)\s+(\S+)(?:\s+(\S+))?)?", ln, re.IGNORECASE)
                            if m:
                                proto = m.group(1).lower()
                                op = (m.group(2) or '').lower()
                                v1 = m.group(3)
                                v2 = m.group(4)
                                spec = {"proto": proto}
                                if op in {"eq", "lt", "gt", "neq", "range"}:
                                    spec["op"] = op
                                    spec["v1"] = v1
                                    if v2:
                                        spec["v2"] = v2
                                members.append(spec)
                            else:
                                # service-object object NAME
                                m2 = re.match(r"^\s*service-object\s+object\s+(\S+)", ln, re.IGNORECASE)
                                if m2:
                                    members.append({"object": m2.group(1)})
                    i += 1
                if typ == 'network':
                    self.network_object_groups[name] = members
                elif typ == 'service':
                    # Store raw service members; will be resolved on demand
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

    def _build_reverse_indexes(self):
        """Build reverse indexes for quick lookups (e.g., address -> object names)."""
        ip_to_objects = defaultdict(set)
        for name, nets in self.network_objects.items():
            for n in nets:
                if isinstance(n, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                    ip_to_objects[n].add(name)
        self.ip_to_objects = dict(ip_to_objects)

    def find_alias_objects(self, target, target_nets):
        """Return mapping of address/network -> other object names that map to it.

        Only considers network objects (not object-groups). If target is the
        name of a network object, it is excluded from the reported alias sets.
        """
        exclude = set()
        if isinstance(target, str) and target in self.network_objects:
            exclude.add(target)

        aliases = {}
        for n in target_nets:
            if not isinstance(n, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                continue
            names = set()
            # Exact match of the same primitive stored in objects
            if n in self.ip_to_objects:
                names.update(self.ip_to_objects[n])
            # Focus is on exact IP/Network duplicates; do not consider containment.
            names -= exclude
            if names:
                aliases[n] = names
        return aliases

    def resolve_service_group(self, name, visited=None):
        """Resolve a service object-group to a list of specs.

        Spec format: { 'proto': 'tcp'|'udp'|'ip'|'icmp', 'op': 'eq'|'lt'|'gt'|'neq'|'range'|None,
                        'v1': token or None, 'v2': token or None }
        """
        if not hasattr(self, 'service_object_groups'):
            return []
        if visited is None:
            visited = set()
        if name in visited:
            return []
        visited.add(name)
        out = []
        for m in self.service_object_groups.get(name, []):
            if isinstance(m, dict) and 'group-object' in m:
                out.extend(self.resolve_service_group(m['group-object'], visited))
            elif isinstance(m, dict) and 'proto' in m:
                out.append(m)
            elif isinstance(m, dict) and 'object' in m:
                # Unresolved service object; keep as-is
                out.append(m)
        return out
    def resolve_network(self, token, visited=None):
        visited = set() if visited is None else visited
        results = set()
        
        if isinstance(token, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
            return {token}

        token_lower = token.lower() if isinstance(token, str) else token
        if token_lower in ('any', 'any4', 'any-ipv4'):
            return {ipaddress.ip_network('0.0.0.0/0')}
        if token_lower in ('any6', 'any-ipv6'):
            try:
                return {ipaddress.ip_network('::/0')}
            except Exception:
                # If IPv6 not desired, return empty to avoid crashes in IPv4-only logic
                return set()

        if token in self.network_objects:
            return self.network_objects[token]

        if token in self.network_object_groups:
            if token in visited:
                return set()
            visited.add(token)
            for m in self.network_object_groups[token]:
                if isinstance(m, dict):
                    if 'group-object' in m:
                        results.update(self.resolve_network(m['group-object'], visited))
                    elif 'object' in m:
                         # Recursively resolve the object name
                         results.update(self.resolve_network(m['object'], visited))
                else:
                    results.add(m)
            return results
        
        # Try to parse as a direct IP/network
        try:
            return {to_ip_network(token)}
        except ValueError:
            pass # Not a valid IP address/network string

        return {token} # Return as is if unresolvable

    def flatten_acl(self):
        entries = []
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

                # Consume protocol/service portion first
                proto_tok = tokens.pop(0).lower()
                proto = proto_tok
                entry_svc = {"proto": None, "service_group_at_proto": None}
                if proto_tok in ('object-group', 'object', 'service-object') and tokens:
                    # Service object(-group) at protocol position; consume its name
                    svc_name = tokens.pop(0)
                    entry_svc["service_group_at_proto"] = {"kind": proto_tok, "name": svc_name}
                    # Protocol may be defined by the service spec; leave proto as token for display
                else:
                    # Standard protocol token
                    entry_svc["proto"] = proto_tok
                # Parse exactly two endpoints: src then dst; then parse service tail
                srcs = self._consume_endpoint(tokens)
                dsts = self._consume_endpoint(tokens)
                svc_tail = self._consume_service_tail(tokens, entry_svc["proto"]) if tokens else {"dst_ports": [], "dst_ops": set(), "dst_service_groups": set(), "dst_service_objects": set()}

                entries.append({'acl': acl_name, 'action': action, 'proto': proto, 'src': srcs, 'dst': dsts, 'svc': {**entry_svc, **svc_tail}, 'raw': ln.strip()})
        return entries

# ------------------- ACL evaluation -------------------

def nets_overlap(set_a, set_b):
    """Check if any network in set_a overlaps with any network in set_b."""
    for net_a in set_a:
        if not isinstance(net_a, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
            continue
        for net_b in set_b:
            if not isinstance(net_b, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                continue
            
            # Handle all combinations of address/network comparisons
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

def _entry_effective_protos(cfg, entry):
    svc = entry.get('svc') or {}
    protos = set()
    # If explicit proto set
    if svc.get('proto') in {'ip', 'tcp', 'udp', 'icmp'}:
        protos.add(svc['proto'])
    # If service group/object at proto position, derive protos from group specs
    sg = svc.get('service_group_at_proto')
    if sg and sg.get('kind') == 'object-group' and hasattr(cfg, 'service_object_groups'):
        name = sg.get('name')
        for spec in cfg.resolve_service_group(name):
            protos.add(spec['proto'])
    # Fallback to tokenized proto field if meaningful and not already covered
    if entry.get('proto') in {'ip', 'tcp', 'udp', 'icmp'}:
        protos.add(entry['proto'])
    return protos or {'ip'}


def _dst_ports_from_entry(cfg, entry):
    svc = entry.get('svc') or {}
    ports = []  # list of (proto, op, (start,end))
    # From tail
    for op, rng in svc.get('dst_ports', []):
        for p in _entry_effective_protos(cfg, entry):
            ports.append((p, op, rng))
    # From service groups referenced in tail
    for g in svc.get('dst_service_groups', set()):
        for spec in cfg.resolve_service_group(g):
            rng = _spec_to_range_tuple(cfg, spec)
            if rng is not None:
                ports.append((spec['proto'], spec.get('op') or 'eq', rng))
    # From proto-position service group
    sg = svc.get('service_group_at_proto')
    if sg and sg.get('kind') == 'object-group':
        for spec in cfg.resolve_service_group(sg.get('name')):
            rng = _spec_to_range_tuple(cfg, spec)
            if rng is not None:
                ports.append((spec['proto'], spec.get('op') or 'eq', rng))
    return ports


def _spec_to_range_tuple(cfg, spec):
    op = spec.get('op')
    if not op:
        # No op => any port; return sentinel None to indicate wildcard
        return (None, None)
    v1 = spec.get('v1')
    v2 = spec.get('v2')
    p1 = cfg._port_from_token(v1, spec.get('proto')) if v1 else None
    p2 = cfg._port_from_token(v2, spec.get('proto')) if v2 else None
    if op == 'range':
        return (p1, p2)
    # eq/lt/gt/neq -> represent as a range where possible
    if op == 'eq':
        return (p1, p1)
    if op == 'lt':
        # [0, p1-1]
        return (0, (p1 - 1) if (p1 is not None and p1 > 0) else None)
    if op == 'gt':
        # [p1+1, 65535]
        return ((p1 + 1) if p1 is not None else None, 65535)
    if op == 'neq':
        # Can't represent two disjoint ranges in single tuple; use wildcard and let filter check exact != when needed
        return (None, None)
    return None


def _service_matches(cfg, entry, svc_filter):
    """Return True if entry matches the optional service filter.

    svc_filter: dict with optional keys {'proto', 'dports': set[int]}
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

    # Build allowed dst port ranges for entry
    port_specs = _dst_ports_from_entry(cfg, entry)
    if not port_specs:
        # No specific ports -> all ports for allowed proto(s)
        return True

    # Check intersection
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


def evaluate_acl(entries, target_nets, cfg=None, service_filter=None):
    """Find all ACL entries that affect the target network set.

    If service_filter is provided, also require service/proto to match.
    Provide cfg when service_filter is used to resolve service groups.
    """
    affected = []
    for e in entries:
        if nets_overlap(e['src'], target_nets) or nets_overlap(e['dst'], target_nets):
            if service_filter:
                if cfg is None:
                    continue
                if not _service_matches(cfg, e, service_filter):
                    continue
            affected.append(e)
    return affected

# ------------------- Comparison & Inspection -------------------

def compare_old_new(cfg_text, old_target, new_target, service_filter=None):
    cfg = ASAConfig(cfg_text)
    
    old_nets = cfg.resolve_network(old_target)
    new_nets = cfg.resolve_network(new_target)

    entries = cfg.flatten_acl()
    
    old_hits = evaluate_acl(entries, old_nets, cfg, service_filter=service_filter)
    new_hits = evaluate_acl(entries, new_nets, cfg, service_filter=service_filter)

    # Create a unique ID for each rule based on its content
    rule_id = lambda e: e['raw']
    
    old_ids = {rule_id(e) for e in old_hits}
    new_ids = {rule_id(e) for e in new_hits}

    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids

    added_to_new = [e for e in new_hits if rule_id(e) in added_ids]
    removed_from_old = [e for e in old_hits if rule_id(e) in removed_ids]

    return {'old_hits': old_hits, 'new_hits': new_hits, 'added_to_new': added_to_new, 'removed_from_old': removed_from_old}

def inspect_host(cfg_text, target, service_filter=None):
    cfg = ASAConfig(cfg_text)
    target_nets = cfg.resolve_network(target)
    entries = cfg.flatten_acl()
    hits = evaluate_acl(entries, target_nets, cfg, service_filter=service_filter)
    aliases = cfg.find_alias_objects(target, target_nets)
    return {'hits': hits, 'target_nets': target_nets, 'aliases': aliases}

def format_flat_rule(rule):
    src_str = ', '.join(sorted([str(s) for s in rule['src']]))
    dst_str = ', '.join(sorted([str(s) for s in rule['dst']]))
    # Build service/ports display
    svc = rule.get('svc') or {}
    parts = []
    if svc.get('proto'):
        parts.append(svc['proto'])
    if svc.get('service_group_at_proto'):
        sg = svc['service_group_at_proto']
        parts.append(f"{sg['kind']}:{sg['name']}")
    # Ports
    port_parts = []
    for op, (p1, p2) in svc.get('dst_ports', []):
        if op == 'range':
            port_parts.append(f"{p1}-{p2}")
        else:
            port_parts.append(f"{op} {p1}")
    if svc.get('dst_service_groups'):
        for g in sorted(svc['dst_service_groups']):
            port_parts.append(f"group:{g}")
    if svc.get('dst_service_objects'):
        for o in sorted(svc['dst_service_objects']):
            port_parts.append(f"object:{o}")
    svc_str = ''
    if parts or port_parts:
        head = ' '.join(parts) if parts else ''
        tail = (' ports=' + ','.join(port_parts)) if port_parts else ''
        svc_str = f" {head}{tail}".rstrip()
    return f"{rule['action']}{(' ' + rule['proto']) if rule.get('proto') else ''}{svc_str} src=[{src_str}] dst=[{dst_str}]"

# ------------------- CLI -------------------

def print_examples():
    examples = [
        "Inspect a host object:",
        "  ./ASA_ACL_inspector.py --config asa.conf --inspect Sidzvsql05",
        "Inspect with protocol/port filter:",
        "  ./ASA_ACL_inspector.py --config asa.conf --inspect 10.0.0.1 --proto tcp --dport 443 --dport 1433",
        "Compare two targets:",
        "  ./ASA_ACL_inspector.py --config asa.conf --old SIDZVPERPAPP01 --new SIDZVPROWEBP1",
        "Compare with service filter:",
        "  ./ASA_ACL_inspector.py --config asa.conf --old 10.0.0.1 --new 10.0.0.2 --proto tcp --dport 3389",
        "Start the web UI on port 8080:",
        "  ./ASA_ACL_inspector.py --web --port 8080",
    ]
    print("\n".join(examples))


def list_config_files(dirpath):
    try:
        files = []
        for entry in os.listdir(dirpath):
            p = os.path.join(dirpath, entry)
            if os.path.isfile(p):
                files.append(entry)
        return sorted(files)
    except FileNotFoundError:
        return []


class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/'):
            self._render_form()
        else:
            self.send_error(404, "Not found")

    def do_POST(self):
        if self.path != '/run':
            self.send_error(404, "Not found")
            return
        length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(length).decode('utf-8')
        fields = parse_qs(data)
        vendor = (fields.get('vendor', ['asa'])[0] or 'asa').lower()
        mode = fields.get('mode', ['inspect'])[0]
        cfg_file = fields.get('config', [''])[0]
        proto = fields.get('proto', [''])[0]
        dports = fields.get('dport', [])
        dports_clean = set()
        for dp in dports:
            dp = dp.strip()
            if not dp:
                continue
            try:
                dports_clean.add(int(dp))
            except Exception:
                pass
        svc_filter = None
        if proto or dports_clean:
            svc_filter = {'proto': (proto or None), 'dports': dports_clean}

        if vendor not in {'asa', 'fortigate'}:
            body = f"Unsupported vendor: {vendor}"
            self._html_response(body)
            return

        # Resolve config path
        cfg_dir = self.server.config_dirs.get(vendor, '.')
        cfg_path = os.path.join(cfg_dir, cfg_file) if cfg_file else ''
        if not cfg_path or not os.path.isfile(cfg_path):
            self._html_response("<p style='color:red'>Invalid or missing config file.</p>" + self._form_html())
            return

        try:
            with open(cfg_path, 'r') as f:
                cfg_text = f.read()
        except Exception as e:
            self._html_response(f"<p style='color:red'>Failed to read config: {e}</p>" + self._form_html())
            return

        if vendor == 'fortigate':
            self._html_response("<p>FortiGate parsing is not implemented yet.</p>" + self._form_html())
            return

        try:
            if mode == 'inspect':
                target = fields.get('inspect', [''])[0]
                report = inspect_host(cfg_text, target, service_filter=svc_filter)
                body = self._render_report_html(target, report)
            else:
                old = fields.get('old', [''])[0]
                new = fields.get('new', [''])[0]
                diff = compare_old_new(cfg_text, old, new, service_filter=svc_filter)
                body = self._render_diff_html(old, new, diff)
            self._html_response(body + self._form_html())
        except Exception as e:
            self._html_response(f"<p style='color:red'>Error: {e}</p>" + self._form_html())

    # -------------- helpers --------------
    def _render_form(self):
        self._html_response(self._form_html())

    def _form_html(self):
        cisco_files = list_config_files(self.server.config_dirs.get('asa', 'configs/cisco'))
        ftg_files = list_config_files(self.server.config_dirs.get('fortigate', 'configs/fortigate'))
        options_asa = "\n".join([f"<option value='{x}'>{x}</option>" for x in cisco_files])
        options_ftg = "\n".join([f"<option value='{x}'>{x}</option>" for x in ftg_files])
        return f"""
<!doctype html>
<html><head><meta charset='utf-8'><title>ACL Inspector</title></head>
<body>
  <h2>ACL Inspector</h2>
  <form method='POST' action='/run'>
    <label>Vendor:</label>
    <select name='vendor' id='vendor' onchange='toggleVendor()'>
      <option value='asa' selected>ASA</option>
      <option value='fortigate'>FortiGate</option>
    </select>
    <br/>
    <div id='asa_cfg'>
      <label>ASA Config:</label>
      <select name='config'>
        {options_asa}
      </select>
    </div>
    <div id='ftg_cfg' style='display:none'>
      <label>FortiGate Config:</label>
      <select name='config'>
        {options_ftg}
      </select>
    </div>
    <br/>
    <label>Mode:</label>
    <select name='mode' id='mode' onchange='toggleMode()'>
      <option value='inspect' selected>Inspect</option>
      <option value='compare'>Compare</option>
    </select>
    <div id='inspect_fields'>
      <label>Inspect target:</label>
      <input type='text' name='inspect' placeholder='ip|cidr|object'/>
    </div>
    <div id='compare_fields' style='display:none'>
      <label>Old target:</label>
      <input type='text' name='old' placeholder='ip|cidr|object'/>
      <label>New target:</label>
      <input type='text' name='new' placeholder='ip|cidr|object'/>
    </div>
    <br/>
    <label>Protocol:</label>
    <select name='proto'>
      <option value=''>Any</option>
      <option value='tcp'>TCP</option>
      <option value='udp'>UDP</option>
      <option value='icmp'>ICMP</option>
      <option value='ip'>IP</option>
    </select>
    <label>Destination ports (comma separated):</label>
    <input type='text' name='dport' placeholder='443,1433'/>
    <br/>
    <button type='submit'>Run</button>
  </form>
  <script>
    function toggleVendor(){{
      var v = document.getElementById('vendor').value;
      document.getElementById('asa_cfg').style.display = (v==='asa') ? 'block':'none';
      document.getElementById('ftg_cfg').style.display = (v==='fortigate') ? 'block':'none';
    }}
    function toggleMode(){{
      var m = document.getElementById('mode').value;
      document.getElementById('inspect_fields').style.display = (m==='inspect') ? 'block':'none';
      document.getElementById('compare_fields').style.display = (m==='compare') ? 'block':'none';
    }}
  </script>
</body></html>
"""

    def _render_report_html(self, target, report):
        lines_raw = "\n".join(f"  {e['raw']}" for e in report['hits'])
        lines_flat = "\n".join(f"  {format_flat_rule(e)}" for e in report['hits'])
        alias_section = ""
        if report.get('aliases'):
            alias_lines = []
            for addr, names in sorted(report['aliases'].items(), key=lambda x: str(x[0])):
                alias_lines.append(f"  {addr}: {', '.join(sorted(names))}")
            alias_section = "<h3>Aliases</h3><pre>" + "\n".join(alias_lines) + "</pre>"
        return f"""
<h3>Inspection Report for {target}</h3>
<p>Resolved to: {', '.join(str(n) for n in report['target_nets'])}</p>
<p>Found {len(report['hits'])} matching ACL entries.</p>
<h3>Matched Rules (Raw)</h3>
<pre>{lines_raw}</pre>
<h3>Matched Rules (Flattened)</h3>
<pre>{lines_flat}</pre>
{alias_section}
"""

    def _render_diff_html(self, old, new, diff):
        added = "\n".join(f" + {e['raw']}" for e in diff['added_to_new'][:200])
        removed = "\n".join(f" - {e['raw']}" for e in diff['removed_from_old'][:200])
        return f"""
<h3>Comparison</h3>
<p>Old target: {old}</p>
<p>New target: {new}</p>
<p>Old hits: {len(diff['old_hits'])} &nbsp; New hits: {len(diff['new_hits'])}</p>
<p>Added to new: {len(diff['added_to_new'])} &nbsp; Removed from old: {len(diff['removed_from_old'])}</p>
<h3>Rules Added to New</h3>
<pre>{added}</pre>
<h3>Rules Removed from Old</h3>
<pre>{removed}</pre>
"""

    def _html_response(self, body, status=200):
        content = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main():
    ap = argparse.ArgumentParser(
        description='ASA ACL inspector for comparing targets or inspecting a single host.',
        epilog='Examples:\n  Compare: ./ASA-ACL-inspector.py --config asa.conf --old 10.1.1.1 --new 10.2.2.2\n  Inspect: ./ASA-ACL-inspector.py --config asa.conf --inspect 10.1.1.1'
    )
    ap.add_argument('--config', help='ASA config file')
    group = ap.add_mutually_exclusive_group()
    group.add_argument('--old', help='Old IP, network (CIDR), or object name for comparison')
    group.add_argument('--inspect', help='IP, network (CIDR), or object name for inspection')
    ap.add_argument('--new', help='New IP, network (CIDR), or object name for comparison')
    # Optional service/proto filters
    ap.add_argument('--proto', choices=['ip', 'tcp', 'udp', 'icmp'], help='Filter by protocol for matching')
    ap.add_argument('--dport', type=int, action='append', help='Filter by destination port (repeatable)')
    # Parser/vendor + config dirs
    ap.add_argument('--vendor', choices=['asa', 'fortigate'], default='asa', help='Firewall vendor (default: asa)')
    ap.add_argument('--configs-cisco', default='configs/cisco', help='Directory containing ASA configs')
    ap.add_argument('--configs-fortigate', default='configs/fortigate', help='Directory containing FortiGate configs')
    # Web UI
    ap.add_argument('--web', action='store_true', help='Start the rudimentary web UI')
    ap.add_argument('--host', default='127.0.0.1', help='Web UI bind host')
    ap.add_argument('--port', type=int, default=8080, help='Web UI port')
    # Examples
    ap.add_argument('--examples', action='store_true', help='Print example usage and exit')

    args = ap.parse_args()

    if args.examples:
        print_examples()
        return

    # Web UI mode uses config directories; ignore --config and interactive args
    if args.web:
        server = HTTPServer((args.host, args.port), WebHandler)
        server.config_dirs = {
            'asa': args.configs_cisco,
            'fortigate': args.configs_fortigate,
        }
        print(f"Web UI running at http://{args.host}:{args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
        return

    # Validate CLI mode inputs now that we're not in web/examples
    if not args.config:
        ap.error('--config is required unless using --web or --examples')
    if not (args.old or args.inspect):
        ap.error('either --old (with --new) or --inspect is required')
    if args.old and not args.new:
        ap.error('--new is required when --old is provided')

    try:
        with open(args.config, 'r') as f:
            cfg_text = f.read()
    except FileNotFoundError:
        print(f"Error: Config file not found at {args.config}", file=sys.stderr)
        sys.exit(1)

    svc_filter = None
    if args.proto or args.dport:
        svc_filter = {
            'proto': args.proto,
            'dports': set(args.dport or []),
        }

    if args.inspect:
        report = inspect_host(cfg_text, args.inspect, service_filter=svc_filter)
        print(f"--- Inspection Report for Target: {args.inspect} ---")
        print(f"Resolved to: {', '.join(str(n) for n in report['target_nets'])}")
        print(f"Found {len(report['hits'])} matching ACL entries.")
        
        print("\n--- Matched Rules (Raw) ---")
        for e in report['hits']:
            print(f"  {e['raw']}")

        print("\n--- Matched Rules (Flattened) ---")
        for e in report['hits']:
            print(f"  {format_flat_rule(e)}")

        if report.get('aliases'):
            print("\n--- Other objects mapping to the same address/network ---")
            for addr, names in sorted(report['aliases'].items(), key=lambda x: str(x[0])):
                print(f"  {addr}: {', '.join(sorted(names))}")

    else: # Comparison mode
        diff = compare_old_new(cfg_text, args.old, args.new, service_filter=svc_filter)

        print(f"ACL entries affecting old target ({args.old}): {len(diff['old_hits'])}")
        print(f"ACL entries affecting new target ({args.new}): {len(diff['new_hits'])}")
        print(f"Added to new target: {len(diff['added_to_new'])}")
        print(f"Removed from old target: {len(diff['removed_from_old'])}")

        if diff['added_to_new']:
            print('\n--- Rules Added to New Target ---')
            for e in diff['added_to_new'][:20]:
                print(f" + {e['raw']}")
                print(f"   -> {format_flat_rule(e)}")
                
        if diff['removed_from_old']:
            print('\n--- Rules Removed from Old Target ---')
            for e in diff['removed_from_old'][:20]:
                print(f" - {e['raw']}")
                print(f"   -> {format_flat_rule(e)}")

if __name__ == '__main__':
    main()
