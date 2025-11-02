"""Static asset handler registration."""

from __future__ import annotations

import mimetypes
from importlib import resources
from pathlib import Path
from typing import Optional, Set

from ..router import Request, Response, Router
from ..state import AppState


def register_static(router: Router, state: Optional[AppState] = None) -> None:
    package = "webui.static"
    files = []
    try:
        for name in resources.contents(package):
            if resources.is_resource(package, name):
                files.append(name)
    except (FileNotFoundError, ModuleNotFoundError):
        files = ["app.css", "app.js", "themes.css"]

    for name in files:
        try:
            data = resources.read_binary(package, name)
        except FileNotFoundError:
            continue
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"

        def handler(_request: Request, *, data=data, mime=mime) -> Response:
            headers = {
                "Content-Type": mime,
                "Cache-Control": "max-age=300, public",
                "Content-Length": str(len(data)),
            }
            return Response(status=200, headers=headers, body=data)

        router.add("GET", f"/static/{name}", handler)

    if state is None:
        return

    css_bytes = (state.font_css or "/* no local fonts configured */\n").encode("utf-8")

    def fonts_css_handler(_request: Request, *, body=css_bytes) -> Response:
        headers = {
            "Content-Type": "text/css; charset=utf-8",
            "Cache-Control": "max-age=60, must-revalidate",
            "Content-Length": str(len(body)),
        }
        return Response(status=200, headers=headers, body=body)

    router.add("GET", "/static/fonts/local.css", fonts_css_handler)

    seen: Set[str] = set()
    for font in state.font_files:
        url_path = font.url_path
        file_path = Path(font.file_path)
        if url_path in seen:
            continue
        if not file_path.exists():
            continue
        try:
            data = file_path.read_bytes()
        except Exception:
            continue
        seen.add(url_path)
        mime = mimetypes.guess_type(str(file_path))[0] or "font/ttf"

        def font_handler(_request: Request, *, payload=data, content_type=mime) -> Response:
            headers = {
                "Content-Type": content_type,
                "Cache-Control": "public, max-age=604800",
                "Content-Length": str(len(payload)),
            }
            return Response(status=200, headers=headers, body=payload)

        router.add("GET", url_path, font_handler)
