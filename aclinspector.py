#!/usr/bin/env python3
"""Unified CLI dispatcher for ACL Inspector tools."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import List

from common.project_paths import ensure_pythonpath_env, project_root

ROOT = project_root()
TOOLS = {
    "inspect": "cli/access-list-inspector.py",
    "web": "cli/access-list-web.py",
    "tui": "cli/acl-inspector-tui.py",
    "translate": "cli/acl-ir-translate.py",
    "optimize": "cli/acl-optimize.py",
}


def run_tool(tool: str, extra_args: List[str], default_vendor: str | None = None) -> int:
    script = ROOT / TOOLS[tool]
    if not script.exists():
        raise FileNotFoundError(f"Tool script '{script}' is missing.")
    cmd = [sys.executable, str(script), *extra_args]
    env = ensure_pythonpath_env()
    if default_vendor:
        env["ACLINSPECTOR_DEFAULT_VENDOR"] = default_vendor
    proc = subprocess.Popen(cmd, env=env, cwd=str(ROOT))
    try:
        return proc.wait()
    except KeyboardInterrupt:
        try:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        return proc.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ACL Inspector multi-tool dispatcher.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Show a capability summary inline in --help
    caps_lines = []
    from common.vendor_caps import all_caps

    for name, cap in sorted(all_caps().items()):
        feats = []
        if cap.supports_inspect:
            feats.append("inspect")
        if cap.supports_compare:
            feats.append("compare")
        if cap.supports_find:
            feats.append("find")
        if cap.supports_packet:
            feats.append("packet")
        caps_lines.append(f"  - {name.upper()}: {', '.join(feats) or 'none'}")
    caps_help = "Vendor capabilities:\n" + "\n".join(caps_lines)

    parser.description = parser.description + "\n\n" + caps_help
    parser.add_argument(
        "--list-capabilities",
        action="store_true",
        help="Show available vendor capabilities and exit.",
    )
    parser.add_argument(
        "--default-vendor",
        choices=["asa", "fortigate", "all"],
        help="Override default vendor for this launch (passed to subcommand when supported).",
    )
    parser.add_argument(
        "tool",
        nargs="?",
        choices=sorted(TOOLS.keys()),
        help="Tool to run (inspect/web/tui/translate/optimize).",
    )
    parser.add_argument(
        "tool_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed through to the selected tool.",
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)

    if ns.list_capabilities:
        from common.vendor_caps import all_caps

        caps = all_caps()
        lines = []
        lines.append("Vendor capabilities:")
        for name, cap in sorted(caps.items()):
            features = []
            if cap.supports_inspect:
                features.append("inspect")
            if cap.supports_compare:
                features.append("compare")
            if cap.supports_find:
                features.append("find")
            if cap.supports_packet:
                features.append("packet")
            lines.append(f"- {name.upper()}: {', '.join(features) or 'none'}")
        print("\n".join(lines))
        return 0

    if not ns.tool:
        parser.error("the following arguments are required: tool")

    return run_tool(ns.tool, ns.tool_args or [], default_vendor=ns.default_vendor)


if __name__ == "__main__":
    raise SystemExit(main())
