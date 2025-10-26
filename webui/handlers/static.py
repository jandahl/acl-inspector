"""Static asset handler registration."""

from __future__ import annotations

import mimetypes
from importlib import resources

from ..router import Request, Response, Router


def register_static(router: Router) -> None:
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
