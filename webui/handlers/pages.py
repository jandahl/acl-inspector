"""HTML page rendering helpers."""

from __future__ import annotations

import json
import os
from importlib import resources
from string import Template

from . import api as api_handlers
from ..router import Request, Response, Router
from ..state import AppState


def _options_for_vendor(state: AppState, vendor: str) -> str:
    listing = api_handlers.config_listing(state, vendor=vendor)
    options = []
    for name in sorted(listing.keys()):
        options.append(f"<option value='{name}'>{name}</option>")
    if not options:
        options.append("<option value='' disabled>(no configs found)</option>")
    return "\n".join(options)


def _render_home(state: AppState) -> str:
    template = resources.read_text("webui.templates", "layout.html")
    themes_json = json.dumps(state.themes).replace("</", "<\\/")
    config_options = {
        "asa": sorted(api_handlers.config_listing(state, vendor="asa").keys()),
        "fortigate": sorted(api_handlers.config_listing(state, vendor="fortigate").keys()),
    }
    context = {
        "themes_json": themes_json,
        "config_options": json.dumps(config_options),
        "history_enabled": "true" if state.settings.features.history_tracking else "false",
        "search_limit": str(state.settings.features.predictive_search.limit),
        "asa_options": _options_for_vendor(state, "asa"),
        "fortigate_options": _options_for_vendor(state, "fortigate"),
        "cwd": os.getcwd(),
    }
    partial_map = {
        "tab_rules": "tab_rules.html",
        "tab_find": "tab_find.html",
        "tab_packet": "tab_packet.html",
        "tab_config": "tab_config.html",
        "tab_prefs": "tab_prefs.html",
        "tab_about": "tab_about.html",
    }
    for key, filename in partial_map.items():
        partial = resources.read_text("webui.templates", filename)
        context[key] = Template(partial).substitute(context)
    return Template(template).substitute(context)


def register_pages(router: Router, state: AppState) -> None:
    """Register HTML page routes."""

    def handle_root(_request: Request) -> Response:
        body = _render_home(state).encode("utf-8")
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Content-Length": str(len(body)),
        }
        return Response(status=200, headers=headers, body=body)

    router.add("GET", "/", handle_root)
