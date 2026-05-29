#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""ACL-inspector Singularity TUI entry point.

A search-first terminal user interface for firewall configuration analysis.
"""

import sys

# Check for TUI dependencies
try:
    import textual
    import rich
except ImportError:
    print("Error: textual and/or rich are not installed.", file=sys.stderr)
    print("Install them with one of:", file=sys.stderr)
    print("  pip install -e '.[tui]'   # if installed as a package", file=sys.stderr)
    print("  pip install 'textual>=0.60' rich   # if running directly from a clone", file=sys.stderr)
    sys.exit(1)

from tui.app import main

if __name__ == "__main__":
    main()
