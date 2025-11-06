"""HTML page rendering helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from importlib import resources
from string import Template
import html

from . import api as api_handlers
from ..router import Request, Response, Router
from ..state import AppState
from .. import __version__ as WEBUI_VERSION
from ..design import dot_to_svg, markdown_to_html, DiagramRenderError, read_text_file
from ..themes import build_singularity_palette


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
        "beta_modules": json.dumps(list(state.settings.beta.enabled_modules)),
        "asa_options": _options_for_vendor(state, "asa"),
        "fortigate_options": _options_for_vendor(state, "fortigate"),
        "cwd": os.getcwd(),
        "version": WEBUI_VERSION,
        "theme_preview_speed": str(state.settings.ui.theme_preview_speed),
    }
    partial_map = {
        "tab_rules": "tab_rules.html",
        "tab_find": "tab_find.html",
        "tab_packet": "tab_packet.html",
        "tab_packet_probe": "tab_packet_probe.html",
        "tab_config": "tab_config.html",
        "tab_prefs": "tab_prefs.html",
        "tab_about": "tab_about.html",
    }
    for key, filename in partial_map.items():
        partial = resources.read_text("webui.templates", filename)
        context[key] = Template(partial).substitute(context)
    return Template(template).substitute(context)


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
    theme_payload = _singularity_themes(state)
    payload = {
        "searchLimit": state.settings.features.predictive_search.limit,
        "defaultMode": "fuzzy",
        "initialHint": "Search every config with a single query.",
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


def register_pages(router: Router, state: AppState) -> None:
    """Register HTML page routes."""

    design_docs = {
        "/design/hld": ("High-Level Design", Path("docs/HIGH-LEVEL-DESIGN.md")),
        "/design/api": ("API & Module Notes", Path("docs/AGENTS.md")),
        "/design/about": ("About ACL Inspector", Path("ABOUT.md")),
    }

    design_diagrams = {
        "/design/diagram/api": ("API Flow", Path("docs/diagrams/api.dot")),
        "/design/diagram/packet-flow": ("Packet Flow", Path("docs/diagrams/packet_flow.dot")),
    }

    def handle_root(_request: Request) -> Response:
        body = _render_home(state).encode("utf-8")
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Content-Length": str(len(body)),
        }
        return Response(status=200, headers=headers, body=body)

    def handle_singularity(_request: Request) -> Response:
        body = _render_singularity(state).encode("utf-8")
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Content-Length": str(len(body)),
        }
        return Response(status=200, headers=headers, body=body)

    def render_design_page(title: str, content_html: str) -> Response:
        body = f"""
<!DOCTYPE html>
<html lang='en'>
  <head>
    <meta charset='utf-8'>
    <title>{html.escape(title)} · Design Notes</title>
    <style>
      body {{ background:#0e1116; color:#e6edf3; font-family: 'Inter', system-ui, sans-serif; margin:0; padding:32px; }}
      h1, h2, h3 {{ color:#7aa2f7; margin-top:24px; }}
      a {{ color:#7aa2f7; }}
      .design-pre {{ white-space: pre-wrap; line-height: 1.6; font-family: 'SFMono-Regular', Menlo, monospace; background:#1a1f29; padding:18px; border-radius:12px; border:1px solid #2b3240; }}
      .design-frame {{ background:#1a1f29; border-radius:12px; border:1px solid #2b3240; padding:24px; box-shadow:0 16px 40px rgba(0,0,0,0.35); }}
      .diagram {{ background:#1a1f29; padding:16px; border-radius:12px; border:1px solid #2b3240; overflow:auto; }}
      .diagram svg {{ width:100%; height:auto; }}
      .nav {{ margin-bottom:24px; font-size:0.9rem; }}
      .nav a {{ margin-right:18px; text-decoration:none; }}
    </style>
  </head>
  <body>
    <div class='nav'>
      <a href='/'>&larr; Main UI</a>
      <a href='/design'>Design index</a>
      <a href='/design/hld'>HLD</a>
      <a href='/design/api'>API Notes</a>
      <a href='/design/diagram/api'>API Diagram</a>
      <a href='/design/diagram/packet-flow'>Packet Flow</a>
    </div>
    <div class='design-frame'>
      <h1>{html.escape(title)}</h1>
      {content_html}
    </div>
  </body>
</html>
""".strip()
        payload = body.encode("utf-8")
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Content-Length": str(len(payload)),
        }
        return Response(status=200, headers=headers, body=payload)

    def handle_design_doc(request: Request) -> Response:
        info = design_docs.get(request.path)
        if not info:
            raise FileNotFoundError(request.path)
        title, doc_path = info
        try:
            raw = read_text_file(doc_path)
        except FileNotFoundError:
            content = f"<p>Document missing: {html.escape(str(doc_path))}</p>"
            return render_design_page(title, content)
        content = markdown_to_html(raw)
        return render_design_page(title, content)

    def handle_design_diagram(request: Request) -> Response:
        info = design_diagrams.get(request.path)
        if not info:
            raise FileNotFoundError(request.path)
        title, dot_path = info
        try:
            svg = dot_to_svg(dot_path)
            content = f"<div class='diagram'>{svg}</div>"
        except FileNotFoundError:
            content = f"<p>Diagram missing: {html.escape(str(dot_path))}</p>"
        except DiagramRenderError as exc:
            content = f"<p>Unable to render diagram: {html.escape(str(exc))}</p>"
        return render_design_page(title, content)

    def handle_design_index(_request: Request) -> Response:
        doc_links = "".join(
            f"<li><a href='{html.escape(path)}'>{html.escape(title)}</a></li>"
            for path, (title, _doc) in design_docs.items()
        )
        diag_links = "".join(
            f"<li><a href='{html.escape(path)}'>{html.escape(title)} (diagram)</a></li>"
            for path, (title, _dot) in design_diagrams.items()
        )
        content = (
            "<p>Internal design documents and diagrams. These pages are intentionally unlinked from the main navigation.</p>"
            "<h2>Documents</h2><ul>"
            f"{doc_links or '<li>None</li>'}</ul>"
            "<h2>Diagrams</h2><ul>"
            f"{diag_links or '<li>None</li>'}</ul>"
        )
        return render_design_page("Design Index", content)

    router.add("GET", "/", handle_root)
    router.add("GET", "/singularity", handle_singularity)
    router.add("GET", "/singularity/", handle_singularity)
    router.add("GET", "/design", handle_design_index)
    for path in design_docs:
        router.add("GET", path, handle_design_doc)
    for path in design_diagrams:
        router.add("GET", path, handle_design_diagram)
