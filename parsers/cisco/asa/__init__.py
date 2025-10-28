"""Cisco ASA parser package.

This package exposes the same public API that previously lived in the monolithic
``parsers.cisco.asa`` module while splitting the implementation into focussed
modules (parser, inspect helpers, path evaluation).
"""

from .parser import ASAConfig  # noqa: F401
from .inspect import evaluate_acl, compare_old_new, inspect_host  # noqa: F401
from .path import path_check  # noqa: F401

__all__ = [
    "ASAConfig",
    "evaluate_acl",
    "compare_old_new",
    "inspect_host",
    "path_check",
]
