#!/usr/bin/env python3
"""Access-list Inspector CLI

Vendor-agnostic CLI entry point that delegates to vendor-specific parsers.

Current support:
- Cisco ASA (parsers.asa)

This CLI reads a single configuration file, resolves IP/object targets, and
either inspects a single target or compares two targets. The default behavior
considers full rule identity (including protocol/ports). Optional --proto and
--dport flags further constrain matches to a specific service.
"""

import argparse
import sys
import json
from xml.etree.ElementTree import Element, SubElement, tostring

from parsers.cisco import asa as cisco_asa
from parsers.fortigate import fortigate as fortigate_parser


def _format_binding(binding: dict) -> str:
    if not binding:
        return ''
    scope = (binding.get('scope') or '').lower()
    direction = binding.get('direction')
    interface = binding.get('interface')
    if scope == 'global':
        return 'global'
    if scope == 'control-plane':
        if interface and direction:
            return f"{interface}({direction},control-plane)"
        return 'control-plane'
    if interface:
        if direction:
            return f"{interface}({direction})"
        return interface
    return scope or ''


def format_flat_rule(rule: dict) -> str:
    """Return a concise string form of a flattened rule including service details."""
    src_str = ', '.join(sorted([str(s) for s in rule['src']]))
    dst_str = ', '.join(sorted([str(s) for s in rule['dst']]))
    svc = rule.get('svc') or {}
    parts = []
    if svc.get('proto'):
        parts.append(svc['proto'])
    if svc.get('service_group_at_proto'):
        sg = svc['service_group_at_proto']
        parts.append(f"{sg['kind']}:{sg['name']}")
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
    binding_str = _format_binding(rule.get('binding'))
    binding_suffix = f" bind={binding_str}" if binding_str else ''
    return f"{rule['action']}{(' ' + rule['proto']) if rule.get('proto') else ''}{svc_str} src=[{src_str}] dst=[{dst_str}]{binding_suffix}"


def _to_str_set(values):
    return sorted([str(v) for v in values])


def _serialize_entry(e: dict) -> dict:
    return {
        'acl': e.get('acl'),
        'action': e.get('action'),
        'proto': e.get('proto'),
        'src': _to_str_set(e.get('src', [])),
        'dst': _to_str_set(e.get('dst', [])),
        'svc': e.get('svc'),
        'binding': e.get('binding'),
        'raw': e.get('raw'),
    }


def _serialize_report(report: dict) -> dict:
    return {
        'target_nets': _to_str_set(report.get('target_nets', [])),
        'hits': [_serialize_entry(e) for e in report.get('hits', [])],
        'aliases': {str(k): sorted(list(v)) for k, v in (report.get('aliases') or {}).items()},
    }


def _serialize_diff(diff: dict) -> dict:
    return {
        'old_hits': [_serialize_entry(e) for e in diff.get('old_hits', [])],
        'new_hits': [_serialize_entry(e) for e in diff.get('new_hits', [])],
        'added_to_new': [_serialize_entry(e) for e in diff.get('added_to_new', [])],
        'removed_from_old': [_serialize_entry(e) for e in diff.get('removed_from_old', [])],
    }


def _serialize_path(result: dict) -> dict:
    return result


def _xml_from_dict(name: str, data) -> Element:
    root = Element(name)
    def build(parent, obj, key_name='item'):
        if isinstance(obj, dict):
            for k, v in obj.items():
                child = SubElement(parent, str(k))
                build(child, v, key_name='item')
        elif isinstance(obj, list):
            for v in obj:
                child = SubElement(parent, key_name)
                build(child, v, key_name='item')
        else:
            parent.text = str(obj)
    build(root, data)
    return root


def _use_color(args):
    # Enable ANSI colors for TTY text output unless disabled or using structured formats
    return (args.format == 'text') and (not args.no_color) and sys.stdout.isatty()


def _c(s, code, enabled):
    return f"\x1b[{code}m{s}\x1b[0m" if enabled else s


def print_examples() -> None:
    """Emit example commands for quick reference and exit."""
    examples = [
        "Inspect a host object:",
        "  ./access-list-inspector.py --vendor asa --config asa.conf --inspect Sidzvsql05",
        "Inspect with protocol/port filter:",
        "  ./access-list-inspector.py --vendor asa --config asa.conf --inspect 10.0.0.1 --proto tcp --dport 443 --dport 1433",
        "Compare two targets:",
        "  ./access-list-inspector.py --vendor asa --config asa.conf --old SIDZVPERPAPP01 --new SIDZVPROWEBP1",
        "Compare with service filter:",
        "  ./access-list-inspector.py --vendor asa --config asa.conf --old 10.0.0.1 --new 10.0.0.2 --proto tcp --dport 3389",
    ]
    print("\n".join(examples))


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Vendor-agnostic access-list inspector (ASA supported).',
        epilog='Use --examples to see example commands.'
    )
    parser.add_argument('--vendor', choices=['asa', 'fortigate'], default='asa', help='Firewall vendor (default: asa)')
    parser.add_argument('--config', help='Config file for the chosen vendor')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--old', help='Old IP, network (CIDR), or object name for comparison')
    group.add_argument('--inspect', help='IP, network (CIDR), or object name for inspection')
    group.add_argument('--find-host', dest='find_host', help='Find an object/IP across configs (set --config to a file or a directory)')
    group.add_argument('--packet', action='store_true', help='Evaluate a single packet path (requires --packet-src/--packet-dst)')
    parser.add_argument('--new', help='New IP, network (CIDR), or object name for comparison')
    parser.add_argument('--proto', choices=['ip', 'tcp', 'udp', 'icmp'], help='Filter by protocol for matching (optional)')
    parser.add_argument('--dport', type=int, action='append', help='Filter by destination port (repeatable, optional)')
    parser.add_argument('--examples', action='store_true', help='Print example usage and exit')
    parser.add_argument('--self-test', action='store_true', help='Run the built-in unit tests and exit')
    parser.add_argument('--vdom', help='FortiGate VDOM name (when --vendor fortigate)')
    parser.add_argument('--format', choices=['text', 'json', 'xml'], default='text', help='Output format (default: text)')
    parser.add_argument('--no-color', action='store_true', help='Disable ANSI colors for text output')
    parser.add_argument('--include-any', action='store_true', help="Include rules with 'any' endpoints (default: ignore such rules)")
    parser.add_argument('--packet-src', dest='packet_src', help='Source IP/object for --packet evaluation')
    parser.add_argument('--packet-dst', dest='packet_dst', help='Destination IP/object for --packet evaluation')

    args = parser.parse_args()

    if args.examples:
        print_examples()
        return
    if args.self_test:
        import unittest
        suite = unittest.defaultTestLoader.discover('tests')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)

    if not args.config:
        parser.error('--config is required')
    # Special mode: find-host
    if args.find_host:
        path = args.config
        import os
        files = []
        if os.path.isdir(path):
            for fname in sorted(os.listdir(path)):
                fpath = os.path.join(path, fname)
                if os.path.isfile(fpath):
                    files.append(fpath)
        else:
            files = [path]
        results = []
        for fpath in files:
            try:
                with open(fpath, 'r') as f:
                    text = f.read()
                if args.vendor == 'asa':
                    cfg = cisco_asa.ASAConfig(text)
                    objects = []
                    literals = []
                    q = args.find_host
                    if q in cfg.network_objects:
                        objects.append(q)
                        literals.extend([str(n) for n in cfg.network_objects[q]])
                    try:
                        nets = cfg.resolve_network(q)
                        for n in nets:
                            for name in cfg.ip_to_objects.get(n, set()):
                                objects.append(name)
                                literals.append(str(n))
                    except Exception:
                        pass
                    hit = bool(objects or literals or (q in text))
                    if hit:
                        results.append({'file': os.path.basename(fpath), 'objects': sorted(set(objects)), 'literals': sorted(set(literals))})
                # FortiGate: placeholder for future VDOM-aware search
            except Exception:
                continue
        if args.format == 'json':
            print(json.dumps({'query': args.find_host, 'results': results}, indent=2))
        else:
            print(f"Find host: {args.find_host}")
            for r in results:
                parts = []
                if r['objects']:
                    parts.append('objects: ' + ', '.join(r['objects']))
                if r['literals']:
                    parts.append('literals: ' + ', '.join(r['literals']))
                print(f"  {r['file']} -> {'; '.join(parts) if parts else 'match'}")
        return

    if not (args.old or args.inspect or args.packet):
        parser.error('either --old (with --new), --inspect, or --packet is required')
    if args.old and not args.new:
        parser.error('--new is required when --old is provided')
    if args.packet and (not args.packet_src or not args.packet_dst):
        parser.error('--packet-src and --packet-dst are required with --packet')

    try:
        with open(args.config, 'r') as f:
            cfg_text = f.read()
    except FileNotFoundError:
        print(f"Error: Config file not found at {args.config}", file=sys.stderr)
        sys.exit(1)

    svc_filter = None
    if args.proto or args.dport:
        svc_filter = {'proto': args.proto, 'dports': set(args.dport or [])}

    use_color = _use_color(args)
    def green(s: str) -> str:
        return _c(s, '32;1', use_color)

    def red(s: str) -> str:
        return _c(s, '31;1', use_color)

    def blue(s: str) -> str:
        return _c(s, '34;1', use_color)

    def bold(s: str) -> str:
        return _c(s, '1', use_color)

    if args.vendor == 'asa':
        if args.packet:
            dports = set(args.dport or [])
            result = cisco_asa.path_check(cfg_text, args.packet_src, args.packet_dst, proto=args.proto, dports=dports, include_any=args.include_any)
            if args.format == 'json':
                print(json.dumps(_serialize_path(result), indent=2))
                return
            if args.format == 'xml':
                xml = _xml_from_dict('path', _serialize_path(result))
                print(tostring(xml, encoding='unicode'))
                return
            status = 'ALLOWED' if result.get('allowed') else 'BLOCKED'
            print(bold(f"Packet Path Check ({status})"))
            print(f"Input src={result['input']['src']} dst={result['input']['dst']} proto={result['input']['proto'] or 'any'} dports={result['input']['dports'] or 'any'}")
            print(f"Resolved src={result['resolved']['src']} dst={result['resolved']['dst']}")
            nat = result.get('nat', {})
            direction = nat.get('direction') or 'n/a'
            print("\nNAT evaluation:")
            if nat.get('applied'):
                rule = nat.get('rule') or {}
                translations = nat.get('translations', {})
                src_tr = translations.get('src', {})
                dst_tr = translations.get('dst', {})
                print(f"  Matched rule: {rule.get('raw', 'unknown')} (direction={direction})")
                print(f"  Source: {src_tr.get('before')} -> {src_tr.get('after')}")
                if src_tr.get('note'):
                    print(f"    note: {src_tr['note']}")
                if dst_tr.get('after') and dst_tr.get('after') != dst_tr.get('before'):
                    print(f"  Destination: {dst_tr.get('before')} -> {dst_tr.get('after')}")
                    if dst_tr.get('note'):
                        print(f"    note: {dst_tr['note']}")
            else:
                print(f"  No NAT rule matched. (direction={direction})")
            acl = result.get('acl', {})
            print("\nACL evaluation:")
            print(f"  Decision: {acl.get('decision', 'unknown').upper()}")
            context = result.get('context') or {}
            candidates = context.get('acl_candidates') or []
            if candidates:
                print("  Candidate bindings:")
                for cand in candidates:
                    iface = cand.get('interface') or 'global'
                    direction = cand.get('direction') or '*'
                    print(f"    {iface} ({direction})")
            matches = acl.get('matches', [])
            if matches:
                limit = 5
                for item in matches[:limit]:
                    print(f"  {item['raw']}")
                    print(f"    -> {item['summary']}")
                if len(matches) > limit:
                    print(f"  ... ({len(matches) - limit} more matches)")
            else:
                print("  No ACL entry matched this flow.")
            if acl.get('inspected') is not None:
                print(f"  Entries inspected: {acl['inspected']}")
            return
        elif args.inspect:
            report = cisco_asa.inspect_host(cfg_text, args.inspect, service_filter=svc_filter, include_any=args.include_any)
            if args.format == 'json':
                print(json.dumps(_serialize_report(report), indent=2))
                return
            if args.format == 'xml':
                xml = _xml_from_dict('inspection', _serialize_report(report))
                print(tostring(xml, encoding='unicode'))
                return
            print(bold(f"Inspection: {args.inspect}"))
            print(f"Resolved to: {', '.join(str(n) for n in report['target_nets'])}")
            print(blue(f"Matching ACL entries: {len(report['hits'])}"))
            print("\nDetails (flattened):")
            for e in report['hits']:
                print(f"  {format_flat_rule(e)}")
            if report.get('aliases'):
                print("\nOther objects mapping to same address/network:")
                for addr, names in sorted(report['aliases'].items(), key=lambda x: str(x[0])):
                    print(f"  {addr}: {', '.join(sorted(names))}")
        else:
            diff = cisco_asa.compare_old_new(cfg_text, args.old, args.new, service_filter=svc_filter, include_any=args.include_any)
            if args.format == 'json':
                print(json.dumps(_serialize_diff(diff), indent=2))
                return
            if args.format == 'xml':
                xml = _xml_from_dict('diff', _serialize_diff(diff))
                print(tostring(xml, encoding='unicode'))
                return
            print(bold(f"Compare: OLD={args.old} vs NEW={args.new}"))
            print(f"Old matches: {len(diff['old_hits'])}  |  New matches: {len(diff['new_hits'])}")
            print(green(f"New-only rules (apply to NEW, not OLD): {len(diff['added_to_new'])}"))
            print(red(f"Old-only rules (apply to OLD, not NEW): {len(diff['removed_from_old'])}"))
            if diff['added_to_new']:
                print(green('\nNew-only rules:'))
                for e in diff['added_to_new'][:50]:
                    print(green(f" + {e['raw']}"))
                    print(f"   -> {format_flat_rule(e)}")
            if diff['removed_from_old']:
                print(red('\nOld-only rules:'))
                for e in diff['removed_from_old'][:50]:
                    print(red(f" - {e['raw']}"))
                    print(f"   -> {format_flat_rule(e)}")
    elif args.vendor == 'fortigate':
        if args.inspect:
            report = fortigate_parser.inspect_host(cfg_text, args.inspect, service_filter=svc_filter, vdom=args.vdom)
            if args.format == 'json':
                print(json.dumps(_serialize_report(report), indent=2))
                return
            if args.format == 'xml':
                xml = _xml_from_dict('inspection', _serialize_report(report))
                print(tostring(xml, encoding='unicode'))
                return
            print(bold(f"Inspection: {args.inspect} (VDOM={args.vdom or 'default'})"))
            print(f"Resolved to: {', '.join(str(n) for n in report['target_nets'])}")
            print(blue(f"Matching policy entries: {len(report['hits'])}"))
            print("\nDetails (flattened):")
            for e in report['hits']:
                print(f"  {format_flat_rule(e)}")
            if report.get('aliases'):
                print("\nOther objects mapping to same address/network:")
                for addr, names in sorted(report['aliases'].items(), key=lambda x: str(x[0])):
                    print(f"  {addr}: {', '.join(sorted(names))}")
        else:
            diff = fortigate_parser.compare_old_new(cfg_text, args.old, args.new, service_filter=svc_filter, vdom=args.vdom)
            if args.format == 'json':
                print(json.dumps(_serialize_diff(diff), indent=2))
                return
            if args.format == 'xml':
                xml = _xml_from_dict('diff', _serialize_diff(diff))
                print(tostring(xml, encoding='unicode'))
                return
            print(bold(f"Compare: OLD={args.old} vs NEW={args.new} (VDOM={args.vdom or 'default'})"))
            print(f"Old matches: {len(diff['old_hits'])}  |  New matches: {len(diff['new_hits'])}")
            print(green(f"New-only rules (apply to NEW, not OLD): {len(diff['added_to_new'])}"))
            print(red(f"Old-only rules (apply to OLD, not NEW): {len(diff['removed_from_old'])}"))
            if diff['added_to_new']:
                print(green('\nNew-only rules:'))
                for e in diff['added_to_new'][:50]:
                    print(green(f" + {e['raw']}"))
                    print(f"   -> {format_flat_rule(e)}")
            if diff['removed_from_old']:
                print(red('\nOld-only rules:'))
                for e in diff['removed_from_old'][:50]:
                    print(red(f" - {e['raw']}"))
                    print(f"   -> {format_flat_rule(e)}")


if __name__ == '__main__':
    main()
