"""Lightweight logging configuration helpers."""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

_ATTACHED = False


def setup_logging(log_dir: Optional[str]) -> Optional[Path]:
    """Install a rotating file handler writing into ``log_dir/web.log``."""

    global _ATTACHED
    if not log_dir or _ATTACHED:
        return Path(log_dir) / "web.log" if log_dir else None

    target = Path(log_dir).expanduser()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None

    log_path = target / "web.log"
    handler = TimedRotatingFileHandler(
        log_path, when="midnight", backupCount=7, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _ATTACHED = True
    return log_path
