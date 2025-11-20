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

ROOT = Path(__file__).resolve().parent

TOOLS = {
    "inspect": "cli/access-list-inspector.py",
    "web": "cli/access-list-web.py",
    "tui": "cli/acl-inspector-tui.py",
    "translate": "cli/acl-ir-translate.py",
    "optimize": "cli/acl-optimize.py",
}


def run_tool(tool: str, extra_args: List[str]) -> int:
    script = ROOT / TOOLS[tool]
    if not script.exists():
        raise FileNotFoundError(f"Tool script '{script}' is missing.")
    cmd = [sys.executable, str(script), *extra_args]
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    parts = [str(ROOT)]
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)
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
    parser.add_argument(
        "tool",
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
    return run_tool(ns.tool, ns.tool_args or [])


if __name__ == "__main__":
    raise SystemExit(main())
