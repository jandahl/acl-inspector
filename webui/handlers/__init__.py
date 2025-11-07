"""Route registration helpers for the modular web UI."""

from __future__ import annotations

import json
from typing import Any
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

    def handle_singularity_suggest(request: Request) -> Response:
        q = request.query
        query = _get_param(q, "q", "")
        mode = _get_param(q, "mode", "fuzzy")
        limit_raw = _get_param(q, "limit", "")
        try:
            limit = int(limit_raw) if limit_raw else state.settings.features.predictive_search.limit
        except Exception:
            limit = state.settings.features.predictive_search.limit
        status, payload = api_handlers.singularity_suggestions(
            state,
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

    def handle_cache_flush(request: Request) -> Response:
        if request.state is None:
            return json_response({"error": "Server state unavailable"}, 500)
        include_disk = False
        if request.body:
            try:
                payload = json.loads(request.body.decode("utf-8") or "{}")
            except Exception:
                payload = {}
            include_disk = bool(payload.get("disk"))
        else:
            include_disk = _get_param(request.query, "disk", "0").lower() in {"1", "true", "yes", "on"}
        status, payload = api_handlers.flush_caches(request.state, include_disk=include_disk)
        return json_response(payload, status)

    def handle_probe(request: Request) -> Response:
        if request.state is None:
            return json_response({"error": "Server state unavailable"}, 500)
        data: Dict[str, Any] = {}
        if request.body:
            try:
                data = json.loads(request.body.decode("utf-8") or "{}")
            except Exception:
                data = {}
        vendor = str(data.get("vendor") or _get_param(request.query, "vendor", "asa")).lower()
        filename = str(data.get("config") or _get_param(request.query, "config", ""))
        src = str(data.get("src") or _get_param(request.query, "src", ""))
        dst = str(data.get("dst") or _get_param(request.query, "dst", ""))
        proto = data.get("proto") or _get_param(request.query, "proto", "")
        dports: List[Any] = []
        if "dports" in data:
            dports = data.get("dports") if isinstance(data.get("dports"), list) else [data.get("dports")]
        elif "dport" in data:
            dports = [data.get("dport")]
        else:
            query_dports = _get_param(request.query, "dport", "")
            if query_dports:
                dports = [query_dports]
        include_any = bool(data.get("include_any"))
        if "include_any" not in data:
            include_any = _get_param(request.query, "include_any", "0").lower() in {"1", "true", "yes", "on"}
        status, payload = api_handlers.packet_probe(
            request.state,
            vendor=vendor,
            filename=filename,
            src=src,
            dst=dst,
            proto=proto if proto else None,
            dports=dports,
            include_any=include_any,
        )
        return json_response(payload, status)

    router.add("GET", "/api/objects", handle_objects)
    router.add("GET", "/api/singularity/suggest", handle_singularity_suggest)
    router.add("GET", "/api/meta", handle_meta)
    router.add("GET", "/api/aliases", handle_aliases)
    router.add("GET", "/api/config", handle_config)
    router.add("GET", "/api/index/status", handle_index_status)
    router.add("GET", "/api/history", handle_history)
    router.add("GET", "/healthz", handle_health)
    router.add("POST", "/api/cache/flush", handle_cache_flush)
    router.add("POST", "/api/probe", handle_probe)

    def handle_run(request: Request) -> Response:
        if request.state is None:
            return json_response({"error": "Server state unavailable"}, 500)
        form = request.body.decode("utf-8")
        fields = parse_qs(form, keep_blank_values=True)
        status, payload = action_handlers.process_run(request.state, fields)
        return json_response(payload, status)

    router.add("POST", "/run", handle_run)
