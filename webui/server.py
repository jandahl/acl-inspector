"""Initial HTTP server bootstrap for the modular web UI.

At this stage we still rely on the legacy WebHandler implementation from
``access-list-web.py`` while the modular handlers are developed. The goal is to
centralise CLI parsing and server construction so future refactors can replace
the handler without disturbing entrypoints.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from http.server import HTTPServer
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
from urllib.parse import parse_qs, urlparse

from . import settings as settings_mod
from .state import AppState
from .router import Request, RouteNotFound, Router
from .handlers import register_api, register_pages
from .handlers.static import register_static

# Importing the legacy module lazily keeps top-level side effects contained.
_legacy = import_module("access-list-web")


@dataclass
class ServerConfig:
    """Runtime configuration for the HTTP server."""

    addr: str
    port: int
    configs_cisco: str
    configs_fortigate: str
    cache_dir: Optional[str]
    search_limit: int
    theme_dir: str
    prewarm_all_configs: bool
    settings_path: Optional[str]


def parse_args(argv: Optional[Sequence[str]] = None) -> ServerConfig:
    """Parse CLI arguments, mirroring the legacy entrypoint defaults."""

    parser = argparse.ArgumentParser(
        description="Web UI for access-list inspection/comparison"
    )
    parser.add_argument(
        "--addr", default="127.0.0.1", help="Bind address (default 127.0.0.1)"
    )
    parser.add_argument("--port", type=int, default=8083, help="TCP port (default 8083)")
    parser.add_argument(
        "--settings",
        dest="settings_path",
        default=None,
        help="Path to settings JSON file (default ./settings.json)",
    )

    env = _legacy.os.environ  # reuse the already imported module
    env_configs_cisco = env.get("ACLINSPECTOR_CONFIGS_CISCO", "configs/cisco")
    env_configs_fortigate = env.get("ACLINSPECTOR_CONFIGS_FORTIGATE", "configs/fortigate")
    parser.add_argument(
        "--configs-cisco",
        default=env_configs_cisco,
        help="Directory with ASA configs (env ACLINSPECTOR_CONFIGS_CISCO)",
    )
    parser.add_argument(
        "--configs-fortigate",
        default=env_configs_fortigate,
        help="Directory with FortiGate configs (env ACLINSPECTOR_CONFIGS_FORTIGATE)",
    )

    env_cache_dir = env.get("ACLINSPECTOR_CACHE_DIR", "")
    env_theme_dir = env.get("ACLINSPECTOR_THEME_DIR", "themes")
    try:
        env_search_limit = int(env.get("ACLINSPECTOR_SEARCH_LIMIT", "").strip() or "50")
    except Exception:
        env_search_limit = 50
    env_prewarm = env.get("ACLINSPECTOR_PREWARM_ALL", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    parser.add_argument(
        "--cache-dir",
        default=env_cache_dir,
        help="Disk cache directory (optional; enable by setting a path)",
    )
    parser.add_argument(
        "--search-limit",
        type=int,
        default=env_search_limit,
        help="Default suggestion limit (can be overridden via query)",
    )
    parser.add_argument(
        "--theme-dir",
        default=env_theme_dir,
        help="Directory with iTerm2 theme files (env ACLINSPECTOR_THEME_DIR)",
    )
    parser.add_argument(
        "--prewarm-all-configs",
        action="store_true",
        default=env_prewarm,
        help="Pre-build index cache for all configs on startup (env ACLINSPECTOR_PREWARM_ALL)",
    )

    args = parser.parse_args(argv)
    return ServerConfig(
        addr=args.addr,
        port=args.port,
        configs_cisco=args.configs_cisco,
        configs_fortigate=args.configs_fortigate,
        cache_dir=args.cache_dir or None,
        search_limit=args.search_limit,
        theme_dir=args.theme_dir,
        prewarm_all_configs=args.prewarm_all_configs,
        settings_path=args.settings_path,
    )


def _make_handler(router: Router):
    base_cls = _legacy.WebHandler

    class ModularHandler(base_cls):  # type: ignore

        def _dispatch(self, method: str, body: bytes = b"") -> bool:
            router = getattr(self.server, "router", None)
            if router is None:
                return False
            parsed = urlparse(self.path)
            request = Request(
                method=method,
                path=parsed.path or "/",
                query=parse_qs(parsed.query),
                headers={k.lower(): v for k, v in self.headers.items()},
                body=body,
                state=getattr(self.server, "app_state", None),
            )
            try:
                response = router.dispatch(request)
            except RouteNotFound:
                return False
            self.send_response(response.status)
            for key, value in response.headers.items():
                self.send_header(key, value)
            if "content-length" not in {k.lower() for k in response.headers.keys()}:
                self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            if response.body:
                self.wfile.write(response.body)
            return True

        def do_GET(self):  # noqa: N802
            if self._dispatch("GET"):
                return
            super().do_GET()

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length) if length > 0 else b""
            if self._dispatch("POST", body):
                return
            super().do_POST()

    return ModularHandler


def build_httpd(settings: settings_mod.Settings, state: AppState, router: Router) -> HTTPServer:
    """Construct an `HTTPServer` instance with modular routing and legacy fallback."""

    handler_cls = _make_handler(router)
    server = HTTPServer((settings.server.host, settings.server.port), handler_cls)
    server.config_dirs = dict(settings.paths.configs)
    server.index_cache = {}
    server.cache_dir = settings.paths.cache_dir
    server.search_limit = settings.features.predictive_search.limit
    server.theme_dir = settings.paths.themes_dir
    server.themes = state.themes
    server.app_state = state
    server.router = router
    return server


def run_server(settings: settings_mod.Settings) -> None:
    """Launch the HTTP server, mirroring the legacy main behaviour."""

    state = AppState.create(settings)
    router = Router()
    register_api(router, state)
    register_pages(router, state)
    register_static(router, state)
    server = build_httpd(settings, state, router)
    if settings.server.prewarm_all and hasattr(_legacy, "prewarm_all_configs"):
        count = _legacy.prewarm_all_configs(server)
        print(f"Prewarmed indices for {count} config(s).")
    print(f"Web UI running at http://{settings.server.host}:{settings.server.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")


def run(argv: Optional[Sequence[str]] = None) -> None:
    """Convenience wrapper to parse args and run the server."""

    cli = parse_args(argv)
    overrides: Dict[str, Any] = {
        "server": {
            "host": cli.addr,
            "port": cli.port,
            "prewarm_all": cli.prewarm_all_configs,
        },
        "paths": {
            "configs": {
                "asa": cli.configs_cisco,
                "fortigate": cli.configs_fortigate,
            },
            "themes_dir": cli.theme_dir,
            "cache_dir": cli.cache_dir,
        },
        "features": {
            "predictive_search": {
                "limit": cli.search_limit,
            }
        },
    }
    settings = settings_mod.load_settings(
        Path(cli.settings_path) if cli.settings_path else None,
        cli_overrides=overrides,
    )
    run_server(settings)
