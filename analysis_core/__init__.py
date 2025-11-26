"""Core analysis utilities shared across presentation layers."""

from .index import IndexEntry, IndexManager
from .inspect import inspect_object, InspectResult
from .compare import compare_objects, CompareResult
from .acl_usage import find_object_usage, UsageResult
from .path_caps import path_check_supported

# Formatters require rich/textual - import conditionally
try:
    from .formatters import (
        format_inspect_rich,
        format_compare_rich,
        format_inspect_json,
        format_compare_json,
        format_usage_rich,
        format_usage_json,
    )
    _FORMATTERS_AVAILABLE = True
except ImportError:
    _FORMATTERS_AVAILABLE = False
    # Provide stub functions if rich is not available
    def format_inspect_rich(result):
        raise ImportError("rich module required for format_inspect_rich")
    def format_compare_rich(result):
        raise ImportError("rich module required for format_compare_rich")
    def format_inspect_json(result):
        raise ImportError("rich module required for format_inspect_json")
    def format_compare_json(result):
        raise ImportError("rich module required for format_compare_json")
    def format_usage_rich(result):
        raise ImportError("rich module required for format_usage_rich")
    def format_usage_json(result):
        raise ImportError("rich module required for format_usage_json")

__all__ = [
    "IndexEntry",
    "IndexManager",
    "inspect_object",
    "InspectResult",
    "compare_objects",
    "CompareResult",
    "find_object_usage",
    "UsageResult",
    "path_check_supported",
    "format_inspect_rich",
    "format_compare_rich",
    "format_inspect_json",
    "format_compare_json",
    "format_usage_rich",
    "format_usage_json",
]
