#!/usr/bin/env python3
"""Deprecated entry point.

Use ./access-list-inspector.py for the CLI and ./access-list-web.py for the web UI.
Vendor-specific ASA parsing has moved into parsers/asa.py.
"""

import sys


def main() -> None:
    print("This script is deprecated. Use ./access-list-inspector.py instead.")
    sys.exit(2)


if __name__ == '__main__':
    main()

