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

from parsers.cisco import asa as cisco_asa
from parsers.fortigate import fortigate as fortigate_parser


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
    return f"{rule['action']}{(' ' + rule['proto']) if rule.get('proto') else ''}{svc_str} src=[{src_str}] dst=[{dst_str}]"


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
    parser.add_argument('--new', help='New IP, network (CIDR), or object name for comparison')
    parser.add_argument('--proto', choices=['ip', 'tcp', 'udp', 'icmp'], help='Filter by protocol for matching (optional)')
    parser.add_argument('--dport', type=int, action='append', help='Filter by destination port (repeatable, optional)')
    parser.add_argument('--examples', action='store_true', help='Print example usage and exit')
    parser.add_argument('--self-test', action='store_true', help='Run the built-in unit tests and exit')

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
    if not (args.old or args.inspect):
        parser.error('either --old (with --new) or --inspect is required')
    if args.old and not args.new:
        parser.error('--new is required when --old is provided')

    try:
        with open(args.config, 'r') as f:
            cfg_text = f.read()
    except FileNotFoundError:
        print(f"Error: Config file not found at {args.config}", file=sys.stderr)
        sys.exit(1)

    svc_filter = None
    if args.proto or args.dport:
        svc_filter = {'proto': args.proto, 'dports': set(args.dport or [])}

    if args.vendor == 'asa':
        if args.inspect:
            report = cisco_asa.inspect_host(cfg_text, args.inspect, service_filter=svc_filter)
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
        else:
            diff = cisco_asa.compare_old_new(cfg_text, args.old, args.new, service_filter=svc_filter)
    elif args.vendor == 'fortigate':
        if args.inspect:
            report = fortigate_parser.inspect_host(cfg_text, args.inspect, service_filter=svc_filter)
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
        else:
            diff = fortigate_parser.compare_old_new(cfg_text, args.old, args.new, service_filter=svc_filter)
            print(f"ACL entries affecting old target ({args.old}): {len(diff['old_hits'])}")
            print(f"ACL entries affecting new target ({args.new}): {len(diff['new_hits'])}")
            print(f"Added to new target: {len(diff['added_to_new'])}")
            print(f"Removed from old target: {len(diff['removed_from_old'])}")
            if diff['added_to_new']:
                print('\n--- Rules Added to New Target ---')
                for e in diff['added_to_new'][:50]:
                    print(f" + {e['raw']}")
                    print(f"   -> {format_flat_rule(e)}")
            if diff['removed_from_old']:
                print('\n--- Rules Removed from Old Target ---')
                for e in diff['removed_from_old'][:50]:
                    print(f" - {e['raw']}")
                    print(f"   -> {format_flat_rule(e)}")


if __name__ == '__main__':
    main()
