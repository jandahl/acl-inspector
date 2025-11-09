#!/usr/bin/env python3
"""ACL-inspector Singularity TUI entry point.

A search-first terminal user interface for firewall configuration analysis.
"""

import sys

# Check for textual dependency
try:
    import textual
except ImportError:
    print("Error: textual library not installed.", file=sys.stderr)
    print("Install with: pip install textual", file=sys.stderr)
    sys.exit(1)

from tui.app import main

if __name__ == "__main__":
    main()
