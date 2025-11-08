"""Singularity (v2) page rendering."""

from __future__ import annotations

import json
from importlib import resources
from string import Template
from typing import Dict, List

from webui.handlers import api as api_handlers
from webui.router import Request, Response, Router
from webui.shared.state import AppState
from webui.shared.themes import build_singularity_palette


def _collect_vendor_options(state: AppState) -> Dict[str, List[str]]:
    vendors = ("asa", "fortigate")
    options: Dict[str, List[str]] = {}
    for vendor in vendors:
        listing = api_handlers.config_listing(state, vendor=vendor)
        options[vendor] = sorted(list(listing.keys()))
    return options


def _default_vendor_selection(options: Dict[str, List[str]]) -> tuple[str, str]:
    priority = ("asa", "fortigate")
    for vendor in priority:
        entries = options.get(vendor) or []
        if entries:
            return vendor, entries[0]
    for vendor, entries in options.items():
        if entries:
            return vendor, entries[0]
    return priority[0], ""


def _singularity_themes(state: AppState) -> Dict[str, object]:
    palettes: Dict[str, Dict[str, str]] = {}
    names: Dict[str, str] = {}
    for theme in state.themes:
        kind = str(theme.get("kind", "")).lower()
        if kind not in ("dark", "light"):
            continue
        if kind in palettes:
            continue
        palettes[kind] = build_singularity_palette(theme)
        names[kind] = str(theme.get("name", kind))
    if "dark" not in palettes and state.themes:
        fallback = state.themes[0]
        palettes["dark"] = build_singularity_palette(fallback)
        names.setdefault("dark", str(fallback.get("name", "Default")))
    if "light" not in palettes and len(state.themes) > 1:
        for theme in state.themes:
            kind = str(theme.get("kind", "")).lower()
            if kind == "light":
                palettes["light"] = build_singularity_palette(theme)
                names.setdefault("light", str(theme.get("name", "Light")))
                break
    default_kind = "dark" if "dark" in palettes else next(iter(palettes), "dark")
    return {"palettes": palettes, "names": names, "default": default_kind}


def _render_singularity(state: AppState) -> str:
    template = resources.read_text("webui.templates", "singularity.html")
    config_options = _collect_vendor_options(state)
    default_vendor, default_config = _default_vendor_selection(config_options)
    theme_payload = _singularity_themes(state)
    payload = {
        "configOptions": config_options,
        "searchLimit": state.settings.features.predictive_search.limit,
        "defaultVendor": default_vendor,
        "defaultConfig": default_config,
        "defaultMode": "fuzzy",
        "initialHint": "Type to search every cached config instantly.",
        "themes": theme_payload["palettes"],
        "themeNames": theme_payload["names"],
        "defaultTheme": theme_payload["default"],
        "themeStorageKey": "acl.singularity.theme",
    }
    context = {
        "singularity_payload": json.dumps(payload).replace("</", "<\\/"),
        "singularity_default_theme": theme_payload["default"],
    }
    return Template(template).substitute(context)


def register_routes(router: Router, state: AppState) -> None:
    """Register Singularity-specific routes."""

    def handle_singularity(_request: Request) -> Response:
        body = _render_singularity(state).encode("utf-8")
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Content-Length": str(len(body)),
        }
        return Response(status=200, headers=headers, body=body)

    router.add("GET", "/singularity", handle_singularity)
    router.add("GET", "/singularity/", handle_singularity)
