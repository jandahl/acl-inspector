"""Core analysis utilities shared across presentation layers."""

from .index import IndexEntry, IndexManager
from .inspect import inspect_object, InspectResult
from .compare import compare_objects, CompareResult
from .formatters import (
    format_inspect_rich,
    format_compare_rich,
    format_inspect_json,
    format_compare_json,
)

__all__ = [
    "IndexEntry",
    "IndexManager",
    "inspect_object",
    "InspectResult",
    "compare_objects",
    "CompareResult",
    "format_inspect_rich",
    "format_compare_rich",
    "format_inspect_json",
    "format_compare_json",
]
