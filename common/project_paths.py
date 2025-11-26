"""Shared helpers for resolving project root and key entrypoints."""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """Return the absolute path to the repository root (two levels up from this file)."""

    return Path(__file__).resolve().parent.parent


def cli_path(relative: str) -> Path:
    """Return an absolute path under the cli/ directory."""

    return project_root() / "cli" / relative


def ensure_pythonpath_env(env: dict | None = None) -> dict:
    """Return a copy of the environment with PYTHONPATH including the repo root."""

    payload = dict(env or os.environ)
    root = str(project_root())
    existing = payload.get("PYTHONPATH", "")
    parts = [root]
    if existing:
        parts.append(existing)
    payload["PYTHONPATH"] = os.pathsep.join(parts)
    return payload
