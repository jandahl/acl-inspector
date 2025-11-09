"""Singularity TUI - Terminal User Interface for ACL-inspector.

A search-first, progressive disclosure terminal interface mirroring the
Singularity web UI concept but adapted for terminal environments.
"""

__version__ = "0.1.0"
__all__ = ["SingularityApp"]

from .app import SingularityApp
