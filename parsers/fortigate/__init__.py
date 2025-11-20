"""FortiGate parser package."""

from .config import FTGConfig  # noqa: F401
from .inspect import evaluate, compare_old_new, inspect_host  # noqa: F401
from .path import path_check  # noqa: F401

__all__ = [
    "FTGConfig",
    "evaluate",
    "compare_old_new",
    "inspect_host",
    "path_check",
]
