#!/usr/bin/env python3
"""CLI tool for analyzing and optimizing firewall ACL policies.

Detects:
- Redundant rules (exact duplicates)
- Shadowed rules (unreachable due to earlier rules)
- Overly permissive rules (any/any permits)
- Consolidation opportunities (rules that could be combined)
"""

import argparse
import sys
from pathlib import Path

from parsers.loader import load_config_to_ir, ConfigLoadError
from analysis.optimizer import PolicyOptimizer


def main():
    parser = argparse.ArgumentParser(
        description="Analyze and optimize firewall ACL policies",
        epilog="Examples:\n"
               "  %(prog)s --config firewall.conf\n"
               "  %(prog)s --config fw.conf --format markdown --output report.md\n"
               "  %(prog)s --config fw.conf --vendor asa --severity critical\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--config', required=True,
                        help='Path to config file (use - for stdin)')
    parser.add_argument('--vendor', choices=['asa', 'fortigate'],
                        help='Firewall vendor (auto-detected if not specified)')
    parser.add_argument('--vdom', default='',
                        help='FortiGate VDOM (if applicable)')
    parser.add_argument('--format', choices=['text', 'json', 'markdown'],
                        default='text',
                        help='Output format (default: text)')
    parser.add_argument('--output', default='-',
                        help='Output file (default: stdout)')
    parser.add_argument('--severity', choices=['critical', 'warning', 'info'],
                        help='Only show issues of this severity or higher')
    parser.add_argument('--category',
                        choices=['redundant', 'shadowed', 'permissive', 'consolidation'],
                        help='Only show issues of this category')

    args = parser.parse_args()

    try:
        # Load config and convert to IR
        device = load_config_to_ir(
            source=args.config,
            vendor=args.vendor,
            vdom=args.vdom,
            strict=False
        )

        # Extract ACL entries from IR
        acl_entries = []
        for acl in device.acls:
            for entry in acl.entries:
                # Convert IR entry to dict for optimizer
                acl_entries.append({
                    'action': entry.action,
                    'proto': entry.proto,
                    'src': entry.src,
                    'dst': entry.dst,
                    'svc': entry.svc,
                    'raw': entry.raw,
                    'acl': acl.name,
                })

        if not acl_entries:
            print("No ACL entries found in configuration", file=sys.stderr)
            sys.exit(1)

        # Run optimization analysis
        optimizer = PolicyOptimizer(acl_entries)
        issues = optimizer.analyze()

        # Filter by severity if requested
        if args.severity:
            severity_levels = {'info': 0, 'warning': 1, 'critical': 2}
            min_level = severity_levels[args.severity]
            issues = [i for i in issues if severity_levels[i.severity] >= min_level]

        # Filter by category if requested
        if args.category:
            issues = [i for i in issues if i.category == args.category]

        # Update optimizer with filtered issues
        optimizer.issues = issues

        # Generate report
        report = optimizer.generate_report(format=args.format)

        # Write output
        if args.output == '-':
            print(report)
        else:
            Path(args.output).write_text(report)
            print(f"Optimization report written to {args.output}", file=sys.stderr)
            print(f"Found {len(issues)} issues", file=sys.stderr)

        # Exit code based on severity
        if any(i.severity == 'critical' for i in issues):
            sys.exit(2)  # Critical issues found
        elif any(i.severity == 'warning' for i in issues):
            sys.exit(1)  # Warnings found
        else:
            sys.exit(0)  # Clean or info only

    except ConfigLoadError as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(3)


if __name__ == '__main__':
    main()
