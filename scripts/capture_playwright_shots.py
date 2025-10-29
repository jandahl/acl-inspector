#!/usr/bin/env python3
"""Capture representative Web UI screenshots using Playwright.

This utility launches the local access-list web server against a temporary
configuration bundle and captures a handful of canonical UI states. It mirrors
the test scaffolding in ``tests/test_ui_playwright.py`` but persists PNGs so
design tweaks (e.g., layout regressions) can be reviewed without running the
browser interactively.

Examples::

    # Use default output directory (playwright_artifacts/<timestamp>/)
    python3 scripts/capture_playwright_shots.py

    # Explicit output directory
    python3 scripts/capture_playwright_shots.py --output ui_shots
"""

from __future__ import annotations

import argparse
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from typing import Callable, Iterable

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover - import guard mirrors unit test behaviour
    PLAYWRIGHT_AVAILABLE = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=None,
        help="Directory to write screenshots (default: playwright_artifacts/<timestamp>/)",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Launch Chromium in headed mode (useful while iterating locally).",
    )
    return parser.parse_args()


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def write_sample_config(target_dir: str) -> str:
    cfg_name = "asa_ui.conf"
    cfg_path = os.path.join(target_dir, cfg_name)
    with open(cfg_path, "w", encoding="utf-8") as fh:
        fh.write(
            "\n".join(
                [
                    "ASA Version 9.14(2)",
                    "object network OBJ_HOST",
                    " host 10.10.10.10",
                    "object network OBJ_WEB",
                    " host 10.10.20.20",
                    "access-list OUT extended permit tcp object OBJ_HOST object OBJ_WEB eq 443",
                    "",
                ]
            )
        )
    return cfg_name


def start_server(config_dir: str, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["ACLINSPECTOR_CONFIGS_CISCO"] = config_dir
    env["ACLINSPECTOR_CONFIGS_FORTIGATE"] = config_dir
    env.setdefault("PYTHONUNBUFFERED", "1")
    proc = subprocess.Popen(
        [
            sys.executable,
            "access-list-web.py",
            "--addr",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def wait_for_server(proc: subprocess.Popen, port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            raise RuntimeError(
                "access-list-web.py exited early:\nSTDOUT:\n{}\nSTDERR:\n{}".format(
                    stdout.decode(),
                    stderr.decode(),
                )
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Timed out waiting for web UI to become available")


def ensure_dir(path: pathlib.Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def capture_screenshots(
    base_url: str,
    config_name: str,
    output_dir: pathlib.Path,
    headful: bool = False,
) -> Iterable[pathlib.Path]:
    saved_paths = []
    with sync_playwright().start() as play:
        browser = play.chromium.launch(headless=not headful)

        def capture(name: str, workflow: Callable):
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            try:
                workflow(page)
                filepath = output_dir / f"{name}.png"
                page.screenshot(path=str(filepath), full_page=True)
                saved_paths.append(filepath)
            finally:
                context.close()

        def goto_root(page):
            page.goto(base_url, wait_until="networkidle")
            page.wait_for_selector("select#config")
            page.select_option("select#config", value=config_name)

        def run_find(page, query: str = "OBJ_HOST"):
            goto_root(page)
            page.click("button[data-tab='find']")
            page.fill("input#findq", query)
            page.wait_for_selector("datalist#targets option")
            page.click("div.actions-run[data-tab='find'] button[type=submit]")
            page.wait_for_selector("div.results[data-tab='find'] pre")

        def wait_for_theme(page, theme: str):
            page.wait_for_function(
                "([theme]) => document.documentElement.dataset.theme === theme",
                arg=[theme],
            )

        capture(
            "find_dark",
            lambda page: (run_find(page)),
        )

        def light_workflow(page):
            run_find(page)
            page.click("#themeToggle")
            wait_for_theme(page, "light")

        capture("find_light", light_workflow)

        def prefs_workflow(page):
            goto_root(page)
            page.click("button[data-tab='prefs']")
            page.wait_for_selector("div.tab-panel.active")

        capture("preferences", prefs_workflow)

        browser.close()
    return saved_paths


def main() -> int:
    if not PLAYWRIGHT_AVAILABLE:
        print("Playwright is not available; install via `pip install playwright`.", file=sys.stderr)
        return 1

    args = parse_args()
    base_output = (
        pathlib.Path(args.output)
        if args.output
        else pathlib.Path("playwright_artifacts") / datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    )
    ensure_dir(base_output)

    with tempfile.TemporaryDirectory(prefix="aclinspector_ui_") as tempdir:
        cfg_name = write_sample_config(tempdir)
        port = find_free_port()
        server = start_server(tempdir, port)
        try:
            wait_for_server(server, port)
            base_url = f"http://127.0.0.1:{port}/"
            saved = capture_screenshots(base_url, cfg_name, base_output, headful=args.headful)
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()

    print("Saved screenshots:")
    for path in saved:
        print(f" - {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - manual utility
    sys.exit(main())
