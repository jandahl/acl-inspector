"""Static assets bundled with the legacy web UI."""

# This file intentionally left minimal. Its presence ensures `importlib.resources`
# can treat `webui.static` as a regular package so the HTTP server can read
# bundled assets (CSS/JS) and serve them via `/static/...` routes.
