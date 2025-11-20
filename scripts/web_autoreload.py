#!/usr/bin/env python3
"""Simple auto-reloader for the ACL Inspector web UI."""

from __future__ import annotations

import argparse
import fnmatch
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATTERNS = ["*.py", "*.html", "*.css", "*.js"]
DEFAULT_PATHS = [
    ROOT / "cli" / "cli/access-list-web.py",
    ROOT / "webui",
    ROOT / "templates",
]


def iter_files(paths: Iterable[Path], patterns: Sequence[str]) -> Iterable[Path]:
    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            if any(fnmatch.fnmatch(path.name, pat) for pat in patterns):
                yield path
            continue
        for candidate in path.rglob("*"):
            if candidate.is_dir():
                continue
            if candidate.name.startswith("."):
                continue
            if "__pycache__" in candidate.parts:
                continue
            if any(fnmatch.fnmatch(candidate.name, pat) for pat in patterns):
                yield candidate


def fingerprint(paths: Iterable[Path], patterns: Sequence[str]) -> Dict[Path, int]:
    data: Dict[Path, int] = {}
    for file in iter_files(paths, patterns):
        try:
            data[file] = int(file.stat().st_mtime_ns)
        except FileNotFoundError:
            continue
    return data


def changes_since(previous: Dict[Path, int], paths: Iterable[Path], patterns: Sequence[str]) -> bool:
    current = fingerprint(paths, patterns)
    if previous.keys() != current.keys():
        previous.clear()
        previous.update(current)
        return True
    for path, stamp in current.items():
        if previous[path] != stamp:
            previous.clear()
            previous.update(current)
            return True
    return False


def launch(args: argparse.Namespace) -> subprocess.Popen:
    env = os.environ.copy()
    if args.configs_cisco:
        env["ACLINSPECTOR_CONFIGS_CISCO"] = args.configs_cisco
    if args.configs_fortigate:
        env["ACLINSPECTOR_CONFIGS_FORTIGATE"] = args.configs_fortigate
    cmd = [sys.executable, str(ROOT / "cli" / "cli/access-list-web.py"), "--addr", args.addr, "--port", str(args.port)]
    if args.prewarm:
        cmd.append("--prewarm-all-configs")
    return subprocess.Popen(cmd, cwd=ROOT, env=env)


def terminate(proc: subprocess.Popen, timeout: float = 5.0) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-reload wrapper around make web.")
    parser.add_argument("--addr", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8083, help="TCP port (default 8083)")
    parser.add_argument("--configs-cisco", help="Override ASA configs directory")
    parser.add_argument("--configs-fortigate", help="Override FortiGate configs directory")
    parser.add_argument("--poll", type=float, default=1.0, help="Polling interval in seconds (default 1s)")
    parser.add_argument("--prewarm", action="store_true", help="Enable --prewarm-all-configs when launching")
    parser.add_argument(
        "--patterns",
        default=",".join(DEFAULT_PATTERNS),
        help="Comma-separated glob patterns to watch (default: *.py,*.html,*.css,*.js)",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Additional files or directories to watch",
    )
    args = parser.parse_args()

    patterns = [pat.strip() for pat in args.patterns.split(",") if pat.strip()]
    watch_paths: List[Path] = DEFAULT_PATHS.copy()
    for extra in args.paths:
        watch_paths.append((ROOT / extra).resolve())

    snapshot = fingerprint(watch_paths, patterns)
    if not snapshot:
        print("warning: no files matched watch patterns", file=sys.stderr)

    proc = launch(args)
    print(f"Web UI running at http://{args.addr}:{args.port} (pid {proc.pid}); watching for changes...")

    try:
        while True:
            time.sleep(args.poll)
            if proc.poll() is not None:
                print("Server exited; restarting...")
                proc = launch(args)
                continue
            if changes_since(snapshot, watch_paths, patterns):
                print("Changes detected; restarting server...")
                terminate(proc)
                proc = launch(args)
    except KeyboardInterrupt:
        print("Stopping auto-reloader...")
    finally:
        terminate(proc)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI utility
    raise SystemExit(main())
