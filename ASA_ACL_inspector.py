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
                    i += 1
                if typ == 'network':
                    self.network_object_groups[name] = members
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
                if proto_tok in ('object-group', 'object', 'service-object') and tokens:
                    # Service object(-group) at protocol position; consume its name
                    svc_name = tokens.pop(0)
                    proto = f"service:{proto_tok}:{svc_name}"
                # Parse exactly two endpoints: src then dst; ignore remaining (ports, etc.)
                srcs = self._consume_endpoint(tokens)
                dsts = self._consume_endpoint(tokens)

                entries.append({'acl': acl_name, 'action': action, 'proto': proto, 'src': srcs, 'dst': dsts, 'raw': ln.strip()})
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

def evaluate_acl(entries, target_nets):
    """Find all ACL entries that affect the target network set."""
    affected = []
    for e in entries:
        if nets_overlap(e['src'], target_nets) or nets_overlap(e['dst'], target_nets):
            affected.append(e)
    return affected

# ------------------- Comparison & Inspection -------------------

def compare_old_new(cfg_text, old_target, new_target):
    cfg = ASAConfig(cfg_text)
    
    old_nets = cfg.resolve_network(old_target)
    new_nets = cfg.resolve_network(new_target)

    entries = cfg.flatten_acl()
    
    old_hits = evaluate_acl(entries, old_nets)
    new_hits = evaluate_acl(entries, new_nets)

    # Create a unique ID for each rule based on its content
    rule_id = lambda e: e['raw']
    
    old_ids = {rule_id(e) for e in old_hits}
    new_ids = {rule_id(e) for e in new_hits}

    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids

    added_to_new = [e for e in new_hits if rule_id(e) in added_ids]
    removed_from_old = [e for e in old_hits if rule_id(e) in removed_ids]

    return {'old_hits': old_hits, 'new_hits': new_hits, 'added_to_new': added_to_new, 'removed_from_old': removed_from_old}

def inspect_host(cfg_text, target):
    cfg = ASAConfig(cfg_text)
    target_nets = cfg.resolve_network(target)
    entries = cfg.flatten_acl()
    hits = evaluate_acl(entries, target_nets)
    aliases = cfg.find_alias_objects(target, target_nets)
    return {'hits': hits, 'target_nets': target_nets, 'aliases': aliases}

def format_flat_rule(rule):
    src_str = ', '.join(sorted([str(s) for s in rule['src']]))
    dst_str = ', '.join(sorted([str(s) for s in rule['dst']]))
    return f"{rule['action']} {rule['proto']} src=[{src_str}] dst=[{dst_str}]"

# ------------------- CLI -------------------

def main():
    ap = argparse.ArgumentParser(
        description='ASA ACL inspector for comparing targets or inspecting a single host.',
        epilog='Examples:\n  Compare: ./ASA-ACL-inspector.py --config asa.conf --old 10.1.1.1 --new 10.2.2.2\n  Inspect: ./ASA-ACL-inspector.py --config asa.conf --inspect 10.1.1.1'
    )
    ap.add_argument('--config', required=True, help='ASA config file')
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--old', help='Old IP, network (CIDR), or object name for comparison')
    group.add_argument('--inspect', help='IP, network (CIDR), or object name for inspection')
    ap.add_argument('--new', help='New IP, network (CIDR), or object name for comparison')

    args = ap.parse_args()

    if args.old and not args.new:
        ap.error('--new is required when --old is provided')

    try:
        with open(args.config, 'r') as f:
            cfg_text = f.read()
    except FileNotFoundError:
        print(f"Error: Config file not found at {args.config}", file=sys.stderr)
        sys.exit(1)

    if args.inspect:
        report = inspect_host(cfg_text, args.inspect)
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
        diff = compare_old_new(cfg_text, args.old, args.new)

        print(f"ACL entries affecting old target ({args.old}): {len(diff['old_hits'])}")
        print(f"ACL entries affecting new target ({args.new}): {len(diff['new_hits'])}")
        print(f"Added to new target: {len(diff['added_to_new'])}")
        print(f"Removed from old target: {len(diff['removed_from_old'])}")

        if diff['added_to_new']:
            print('\n--- Rules Added to New Target ---')
            for e in diff['added_to_new'][:20]:
                print(f" + {e['raw']}")
                
        if diff['removed_from_old']:
            print('\n--- Rules Removed from Old Target ---')
            for e in diff['removed_from_old'][:20]:
                print(f" - {e['raw']}")

if __name__ == '__main__':
    main()
