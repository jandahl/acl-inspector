"""Lightweight logging configuration helpers."""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

_LOG_HANDLER_ATTACHED = False


def setup_logging(log_dir: Optional[str]) -> Optional[Path]:
    """Configure root logging to emit to ``log_dir/web.log``.

    Returns the resolved log file path if logging was enabled.
    """

    global _LOG_HANDLER_ATTACHED
    if _LOG_HANDLER_ATTACHED:
        return Path(log_dir) / "web.log" if log_dir else None

    if not log_dir:
        return None

    target_dir = Path(log_dir).expanduser()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None

    log_path = target_dir / "web.log"
    handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        backupCount=7,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _LOG_HANDLER_ATTACHED = True
    return log_path
