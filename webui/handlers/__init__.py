"""Route registration helpers for the modular web UI."""

from __future__ import annotations

import json
from typing import Dict, List
from urllib.parse import parse_qs

from . import actions as action_handlers
from . import api as api_handlers
from .pages import register_pages  # re-export for server wiring
from ..router import Request, Response, Router
from ..state import AppState

__all__ = ["register_api", "register_pages"]


def register_api(router: Router, state: AppState) -> None:
    """Register JSON API endpoints."""

    def json_response(payload, status: int = 200) -> Response:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store, no-cache, must-revalidate",
        }
        headers["Content-Length"] = str(len(body))
        return Response(status=status, headers=headers, body=body)

    def _get_param(query, key, default=""):
        return (query.get(key, [default])[0] or default)

    def handle_objects(request: Request) -> Response:
        q = request.query
        vendor = _get_param(q, "vendor", "asa").lower()
        os_tag = _get_param(q, "os", vendor.upper())
        version = _get_param(q, "version", "auto")
        filename = _get_param(q, "config", "")
        query = _get_param(q, "q", "")
        mode = _get_param(q, "mode", "fuzzy")
        try:
            limit = int(_get_param(q, "limit", str(state.settings.features.predictive_search.limit)))
        except Exception:
            limit = state.settings.features.predictive_search.limit
        status, payload = api_handlers.objects(
            state,
            vendor=vendor,
            os_tag=os_tag,
            version=version,
            filename=filename,
            query=query,
            mode=mode,
            limit=limit,
        )
        return json_response(payload, status)

    def handle_meta(request: Request) -> Response:
        q = request.query
        vendor = _get_param(q, "vendor", "asa").lower()
        filename = _get_param(q, "config", "")
        status, payload = api_handlers.meta(state, vendor=vendor, filename=filename)
        return json_response(payload, status)

    def handle_aliases(request: Request) -> Response:
        q = request.query
        vendor = _get_param(q, "vendor", "asa").lower()
        filename = _get_param(q, "config", "")
        target = _get_param(q, "target", "")
        status, payload = api_handlers.aliases(
            state, vendor=vendor, filename=filename, target=target
        )
        return json_response(payload, status)

    def handle_config(request: Request) -> Response:
        q = request.query
        vendor = _get_param(q, "vendor", "asa").lower()
        filename = _get_param(q, "config", "")
        status, payload = api_handlers.config_text(
            state, vendor=vendor, filename=filename
        )
        return json_response(payload, status)

    def handle_index_status(_request: Request) -> Response:
        status, payload = api_handlers.index_status(state)
        return json_response(payload, status)

    def handle_history(_request: Request) -> Response:
        status, payload = api_handlers.history(state)
        return json_response(payload, status)

    def handle_health(_request: Request) -> Response:
        body = b"ok"
        headers = {"Content-Type": "text/plain; charset=utf-8", "Content-Length": "2"}
        return Response(status=200, headers=headers, body=body)

    router.add("GET", "/api/objects", handle_objects)
    router.add("GET", "/api/meta", handle_meta)
    router.add("GET", "/api/aliases", handle_aliases)
    router.add("GET", "/api/config", handle_config)
    router.add("GET", "/api/index/status", handle_index_status)
    router.add("GET", "/api/history", handle_history)
    router.add("GET", "/healthz", handle_health)

    def handle_run(request: Request) -> Response:
        if request.state is None:
            return json_response({"error": "Server state unavailable"}, 500)
        form = request.body.decode("utf-8")
        fields = parse_qs(form, keep_blank_values=True)
        status, payload = action_handlers.process_run(request.state, fields)
        return json_response(payload, status)

    router.add("POST", "/run", handle_run)
