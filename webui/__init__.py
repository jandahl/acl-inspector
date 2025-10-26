"""Web UI package scaffold."""

from typing import Optional, Sequence

from . import server


def run(argv: Optional[Sequence[str]] = None) -> None:
    """Parse arguments and run the HTTP server."""

    server.run(argv)


def create_app(*_args, **_kwargs):  # pragma: no cover - placeholder
    """Placeholder for future modular app factory."""
    raise NotImplementedError("webui.create_app() not yet implemented")
