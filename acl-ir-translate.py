#!/usr/bin/env python3
"""CLI tool for IR translation between firewall vendors.

Converts firewall configurations to/from the vendor-agnostic Intermediate
Representation (IR) format, enabling cross-vendor analysis and migration.
"""

import argparse
import json
import sys
from pathlib import Path

from parsers.loader import load_config_to_ir, ConfigLoadError
from parsers.cisco.asa import ir_import as asa_import
from parsers.fortigate import ir_import as ftg_import


def export_to_ir(vendor: str, config_path: str, device_name: str = None, vdom: str = "", auto_detect: bool = True) -> dict:
    """Export vendor config to IR format.

    Args:
        vendor: Source vendor ('asa', 'fortigate', or None for auto-detect)
        config_path: Path to config file
        device_name: Optional device name
        vdom: FortiGate VDOM (if applicable)
        auto_detect: Enable vendor auto-detection (default: True)

    Returns:
        IR Device as dict

    Raises:
        ValueError: If vendor not supported or config invalid
        ConfigLoadError: If auto-detection fails
    """
    # Use unified loader with optional auto-detection
    try:
        device = load_config_to_ir(
            source=config_path,
            vendor=vendor if not auto_detect else None,
            device_name=device_name,
            vdom=vdom,
            strict=False  # Allow low confidence detection
        )
        return device.to_dict()
    except ConfigLoadError as e:
        raise ValueError(str(e))


def import_from_ir(vendor: str, ir_dict: dict) -> str:
    """Import IR format to vendor config.

    Args:
        vendor: Target vendor ('asa', 'fortigate')
        ir_dict: IR Device dictionary

    Returns:
        Vendor-specific configuration text

    Raises:
        ValueError: If vendor not supported
    """
    vendor = vendor.lower()

    # Import IR module and reconstruct Device
    from parsers import model as ir
    device = ir.Device(**ir_dict)

    # Generate vendor config
    if vendor == 'asa':
        return asa_import.from_ir(device)
    elif vendor == 'fortigate':
        return ftg_import.from_ir(device)
    else:
        raise ValueError(f"Unsupported vendor: {vendor}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Translate firewall configs via Intermediate Representation (IR)",
        epilog="Examples:\n"
               "  %(prog)s export --vendor asa --config fw.conf --output fw.ir.json\n"
               "  %(prog)s import --vendor fortigate --ir fw.ir.json --output fw.ftg.conf\n"
               "  %(prog)s convert --from asa --to fortigate --config fw.conf --output fw.ftg.conf\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', required=True)

    # Export command
    export_parser = subparsers.add_parser('export', help='Export vendor config to IR')
    export_parser.add_argument('--vendor', choices=['asa', 'fortigate'],
                               help='Source vendor (auto-detected if not specified)')
    export_parser.add_argument('--config', required=True,
                               help='Path to config file (use - for stdin)')
    export_parser.add_argument('--output', default='-',
                               help='Output IR JSON file (default: stdout)')
    export_parser.add_argument('--device-name', default=None,
                               help='Device name (default: from filename)')
    export_parser.add_argument('--vdom', default='',
                               help='FortiGate VDOM (if applicable)')
    export_parser.add_argument('--pretty', action='store_true',
                               help='Pretty-print JSON output')
    export_parser.add_argument('--no-auto-detect', action='store_true',
                               help='Disable auto-detection (require --vendor)')

    # Import command
    import_parser = subparsers.add_parser('import', help='Import IR to vendor config')
    import_parser.add_argument('--vendor', required=True, choices=['asa', 'fortigate'],
                               help='Target vendor')
    import_parser.add_argument('--ir', required=True,
                               help='Path to IR JSON file (use - for stdin)')
    import_parser.add_argument('--output', default='-',
                               help='Output config file (default: stdout)')

    # Convert command (combines export + import)
    convert_parser = subparsers.add_parser('convert', help='Convert between vendors')
    convert_parser.add_argument('--from', dest='from_vendor',
                                choices=['asa', 'fortigate'],
                                help='Source vendor (auto-detected if not specified)')
    convert_parser.add_argument('--to', dest='to_vendor', required=True,
                                choices=['asa', 'fortigate'],
                                help='Target vendor')
    convert_parser.add_argument('--config', required=True,
                                help='Path to source config file (use - for stdin)')
    convert_parser.add_argument('--output', default='-',
                                help='Output config file (default: stdout)')
    convert_parser.add_argument('--vdom', default='',
                                help='FortiGate VDOM (if source is FortiGate)')
    convert_parser.add_argument('--save-ir', default=None,
                                help='Also save intermediate IR to this file')

    args = parser.parse_args()

    try:
        if args.command == 'export':
            # Validate args
            if args.no_auto_detect and not args.vendor:
                print("Error: --vendor required when --no-auto-detect is used", file=sys.stderr)
                sys.exit(1)

            # Export to IR
            ir_dict = export_to_ir(
                vendor=args.vendor,
                config_path=args.config,
                device_name=args.device_name,
                vdom=args.vdom,
                auto_detect=not args.no_auto_detect
            )

            # Write output
            indent = 2 if args.pretty else None
            json_output = json.dumps(ir_dict, indent=indent)

            if args.output == '-':
                print(json_output)
            else:
                Path(args.output).write_text(json_output)
                print(f"Exported to {args.output}", file=sys.stderr)

        elif args.command == 'import':
            # Read IR
            if args.ir == '-':
                ir_dict = json.load(sys.stdin)
            else:
                ir_dict = json.loads(Path(args.ir).read_text())

            # Import from IR
            config_text = import_from_ir(vendor=args.vendor, ir_dict=ir_dict)

            # Write output
            if args.output == '-':
                print(config_text)
            else:
                Path(args.output).write_text(config_text)
                print(f"Imported to {args.output}", file=sys.stderr)

        elif args.command == 'convert':
            # Export to IR (with auto-detection if --from not specified)
            ir_dict = export_to_ir(
                vendor=args.from_vendor,
                config_path=args.config,
                vdom=args.vdom,
                auto_detect=(args.from_vendor is None)
            )

            # Save IR if requested
            if args.save_ir:
                Path(args.save_ir).write_text(json.dumps(ir_dict, indent=2))
                print(f"IR saved to {args.save_ir}", file=sys.stderr)

            # Import to target vendor
            config_text = import_from_ir(vendor=args.to_vendor, ir_dict=ir_dict)

            # Write output
            if args.output == '-':
                print(config_text)
            else:
                Path(args.output).write_text(config_text)
                print(f"Converted to {args.output}", file=sys.stderr)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
