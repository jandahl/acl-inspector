#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
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
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from parsers.cisco import asa as cisco_asa
from utils.config import clean_config_text
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


def _serialize_service(svc: Optional[dict]) -> dict:
    if not svc:
        return {
            'proto': None,
            'service_group_at_proto': None,
            'dst_ports': [],
            'dst_ops': [],
            'dst_service_groups': [],
            'dst_service_objects': [],
        }
    dst_ports = [
        {'op': op, 'start': rng[0], 'end': rng[1]}
        for op, rng in svc.get('dst_ports', [])
    ]
    return {
        'proto': svc.get('proto'),
        'service_group_at_proto': svc.get('service_group_at_proto'),
        'dst_ports': dst_ports,
        'dst_ops': sorted(list(svc.get('dst_ops') or [])),
        'dst_service_groups': sorted(list(svc.get('dst_service_groups') or [])),
        'dst_service_objects': sorted(list(svc.get('dst_service_objects') or [])),
    }


def _serialize_entry(e: dict) -> dict:
    return {
        'acl': e.get('acl'),
        'action': e.get('action'),
        'proto': e.get('proto'),
        'src': _to_str_set(e.get('src', [])),
        'dst': _to_str_set(e.get('dst', [])),
        'svc': _serialize_service(e.get('svc')),
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
        "  ./cli/access-list-inspector.py --vendor asa --config asa.conf --inspect Sidzvsql05",
        "Inspect with protocol/port filter:",
        "  ./cli/access-list-inspector.py --vendor asa --config asa.conf --inspect 10.0.0.1 --proto tcp --dport 443 --dport 1433",
        "Compare two targets:",
        "  ./cli/access-list-inspector.py --vendor asa --config asa.conf --old SIDZVPERPAPP01 --new SIDZVPROWEBP1",
        "Compare with service filter:",
        "  ./cli/access-list-inspector.py --vendor asa --config asa.conf --old 10.0.0.1 --new 10.0.0.2 --proto tcp --dport 3389",
    ]
    print("\n".join(examples))


def main() -> None:
    raw_args = sys.argv[1:]
    vendor_flag_used = any(arg == '--vendor' or arg.startswith('--vendor=') for arg in raw_args)

    parser = argparse.ArgumentParser(
        description='Vendor-agnostic access-list inspector (ASA supported).',
        epilog='Use --examples to see example commands.'
    )
    parser.add_argument('--vendor', choices=['asa', 'fortigate', 'all'], default='asa', help='Firewall vendor (default: asa)')
    parser.add_argument('--config', help='Config file for the chosen vendor')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--old', help='Old IP, network (CIDR), or object name for comparison')
    group.add_argument('--inspect', help='IP, network (CIDR), or object name for inspection')
    group.add_argument('--find-host', dest='find_host', help='Find an object/IP across configs (set --config to a file or a directory)')
    group.add_argument('--packet', action='store_true', help='Evaluate a single packet path (requires --packet-src/--packet-dst)')
    group.add_argument('--translate', action='store_true', help='Translate config to another vendor format (requires --target-vendor)')
    parser.add_argument('--new', help='New IP, network (CIDR), or object name for comparison')
    parser.add_argument('--target-vendor', dest='target_vendor', choices=['asa', 'fortigate'], help='Target vendor for translation (use with --translate)')
    parser.add_argument('--device-name', dest='device_name', help='Device name for IR export (optional)')
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
    parser.add_argument('--verify', action='store_true', help='Show live-verification commands (packet-tracer/iprope) for path suggestions')
    parser.add_argument('--singularitty', action='store_true', help='Launch the Singularity TUI interface (alias for the TUI)')

    args = parser.parse_args()

    if args.singularitty:
        from tui.app import main as tui_main

        tui_args = []
        if vendor_flag_used:
            tui_args.extend(['--vendor', args.vendor])
        if args.config:
            tui_args.extend(['--config', args.config])
        if args.vdom:
            tui_args.extend(['--vdom', args.vdom])
        tui_main(argv=tui_args or None)
        return

    if args.vendor == 'all':
        parser.error("--vendor=all can only be used with --singularitty")

    stdin_cache: Optional[str] = None

    def read_config_text(path: str) -> str:
        nonlocal stdin_cache
        if path == '-':
            if stdin_cache is None:
                stdin_cache = clean_config_text(sys.stdin.read())
            return stdin_cache
        with open(path, 'r', encoding='utf-8') as f:
            return clean_config_text(f.read())

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

        sources = []
        if path == '-':
            sources.append(('<stdin>', '-'))
        elif os.path.isdir(path):
            for fname in sorted(os.listdir(path)):
                fpath = os.path.join(path, fname)
                if os.path.isfile(fpath):
                    sources.append((fname, fpath))
        else:
            sources.append((os.path.basename(path), path))
        results = []
        for display_name, source_path in sources:
            try:
                text = read_config_text(source_path)
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
                        results.append({'file': display_name, 'objects': sorted(set(objects)), 'literals': sorted(set(literals))})
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

    if not (args.old or args.inspect or args.packet or args.translate):
        parser.error('either --old (with --new), --inspect, --packet, or --translate is required')
    if args.old and not args.new:
        parser.error('--new is required when --old is provided')
    if args.packet and (not args.packet_src or not args.packet_dst):
        parser.error('--packet-src and --packet-dst are required with --packet')
    if args.translate and not args.target_vendor:
        parser.error('--target-vendor is required with --translate')

    try:
        cfg_text = read_config_text(args.config)
    except FileNotFoundError:
        print(f"Error: Config file not found at {args.config}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"Error reading config {args.config}: {exc}", file=sys.stderr)
        sys.exit(1)

    # Handle translation mode
    if args.translate:
        if args.vendor == args.target_vendor:
            print(f"Error: Source and target vendors are the same ({args.vendor})", file=sys.stderr)
            sys.exit(1)

        # Parse source config and convert to IR
        if args.vendor == 'asa':
            cfg = cisco_asa.ASAConfig(cfg_text)
            from parsers.cisco.asa import ir_export
            ir_device = ir_export.to_ir(cfg, device_name=args.device_name)
        elif args.vendor == 'fortigate':
            from parsers.fortigate.config import FTGConfig
            cfg = FTGConfig(cfg_text, vdom=args.vdom)
            from parsers.fortigate import ir_export
            ir_device = ir_export.to_ir(cfg, device_name=args.device_name)
        else:
            print(f"Error: Unsupported source vendor: {args.vendor}", file=sys.stderr)
            sys.exit(1)

        # Convert IR to target format
        if args.target_vendor == 'asa':
            from parsers.cisco.asa import ir_import
            output = ir_import.from_ir(ir_device, hostname=args.device_name)
        elif args.target_vendor == 'fortigate':
            from parsers.fortigate import ir_import
            vdom_name = args.vdom or 'root'
            output = ir_import.from_ir(ir_device, vdom=vdom_name)
        else:
            print(f"Error: Unsupported target vendor: {args.target_vendor}", file=sys.stderr)
            sys.exit(1)

        # Output translated config
        if args.format == 'json':
            # Output IR as JSON for inspection
            print(json.dumps(ir_device.to_dict(), indent=2))
        else:
            # Output translated config
            print(output)
        return

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

    if args.packet:
        dports = set(args.dport or [])
        if args.vendor == 'asa':
            result = cisco_asa.path_check(
                cfg_text,
                args.packet_src,
                args.packet_dst,
                proto=args.proto,
                dports=dports,
                include_any=args.include_any,
            )
        elif args.vendor == 'fortigate':
            from parsers.fortigate import path_check as fortigate_path_check

            result = fortigate_path_check(
                cfg_text,
                args.packet_src,
                args.packet_dst,
                proto=args.proto,
                dports=dports,
                include_any=args.include_any,
                vdom=args.vdom,
            )
        else:
            parser.error(f"Packet path check not supported for vendor {args.vendor}")

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
        nat_direction = nat.get('direction') or 'n/a'
        print("\nNAT evaluation:")
        if nat.get('applied'):
            rule = nat.get('rule') or {}
            translations = nat.get('translations', {})
            src_tr = translations.get('src', {})
            dst_tr = translations.get('dst', {})
            rule_desc = rule.get('raw') or rule.get('name') or 'unknown'
            print(f"  Matched rule: {rule_desc} (direction={nat_direction})")
            print(f"  Source: {src_tr.get('before')} -> {src_tr.get('after')}")
            if src_tr.get('note'):
                print(f"    note: {src_tr['note']}")
            if dst_tr.get('after') and dst_tr.get('after') != dst_tr.get('before'):
                print(f"  Destination: {dst_tr.get('before')} -> {dst_tr.get('after')}")
                if dst_tr.get('note'):
                    print(f"    note: {dst_tr['note']}")
        else:
            print(f"  No NAT rule matched. (direction={nat_direction})")
        acl = result.get('acl', {})
        print("\nACL evaluation:")
        print(f"  Decision: {acl.get('decision', 'unknown').upper()}")
        context = result.get('context') or {}
        candidates = context.get('acl_candidates') or []
        if candidates:
            print("  Candidate bindings:")
            for cand in candidates:
                iface = cand.get('interface') or 'global'
                cand_dir = cand.get('direction') or '*'
                print(f"    {iface} ({cand_dir})")
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
        suggestion = result.get('suggestion') or {}
        if suggestion.get('needed'):
            reason = suggestion.get('reason', 'deny').replace('-', ' ')
            print(bold(f"\nCorrection Suggestion ({reason}):"))
            for sug in suggestion.get('suggestions', []):
                scenario = (sug.get('scenario') or '').upper()
                print(blue(f"  [{scenario}] {sug.get('rationale', '')}"))
                for cmd in sug.get('commands', []):
                    print(green(f"    {cmd}"))
                if sug.get('note'):
                    print(f"    note: {sug['note']}")
            if args.verify:
                verifications = suggestion.get('verification', [])
                if verifications:
                    print(bold("\nLive Verification (run on the device):"))
                    for ver in verifications:
                        desc = ver.get('description')
                        if desc:
                            print(blue(f"  {desc}"))
                        for line in (ver.get('command') or '').splitlines():
                            print(green(f"    {line}"))
                else:
                    print(blue("\nNo live-verification command available for this vendor."))
        return

    if args.vendor == 'asa':
        if args.inspect:
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
