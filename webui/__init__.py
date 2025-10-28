"""Web UI package scaffold."""

from typing import Optional, Sequence

__version__ = "0.9.0"

from . import server  # noqa: E402  (import after version constant)

__all__ = ["run", "create_app", "__version__"]


def run(argv: Optional[Sequence[str]] = None) -> None:
    """Parse arguments and run the HTTP server."""

    server.run(argv)


def create_app(*_args, **_kwargs):  # pragma: no cover - placeholder
    """Placeholder for future modular app factory."""
    raise NotImplementedError("webui.create_app() not yet implemented")
