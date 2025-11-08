"""Page rendering for the legacy (v1) web UI."""

from __future__ import annotations

import html
import json
import os
from importlib import resources
from pathlib import Path
from string import Template

from webui.handlers import api as api_handlers
from webui.router import Request, Response, Router
from webui.shared.state import AppState
from webui.design import DiagramRenderError, dot_to_svg, markdown_to_html, read_text_file
from webui import __version__ as WEBUI_VERSION


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


def register_routes(router: Router, state: AppState) -> None:
    """Register routes for the legacy UI."""

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
"""
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Content-Length": str(len(body)),
        }
        return Response(status=200, headers=headers, body=body.encode("utf-8"))

    def handle_design_docs(request: Request) -> Response:
        entry = design_docs.get(request.path)
        if not entry:
            return Response(status=404, headers={}, body=b"")
        title, path = entry
        try:
            text = read_text_file(path)
        except FileNotFoundError:
            return Response(status=404, headers={}, body=b"")
        try:
            html_body = markdown_to_html(text)
        except Exception:
            html_body = f"<pre class='design-pre'>{html.escape(text)}</pre>"
        return render_design_page(title, html_body)

    def handle_design_diagram(request: Request) -> Response:
        entry = design_diagrams.get(request.path)
        if not entry:
            return Response(status=404, headers={}, body=b"")
        title, path = entry
        try:
            svg = dot_to_svg(path)
        except DiagramRenderError as exc:
            html_body = f"<pre class='design-pre'>Failed to render diagram: {html.escape(str(exc))}</pre>"
        else:
            html_body = f"<div class='diagram'>{svg}</div>"
        return render_design_page(title, html_body)

    router.add("GET", "/", handle_root)
    for route in design_docs:
        router.add("GET", route, handle_design_docs)
    for route in design_diagrams:
        router.add("GET", route, handle_design_diagram)
