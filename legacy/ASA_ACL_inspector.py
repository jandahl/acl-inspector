#!/usr/bin/env python3
"""Deprecated entry point.

Use ./aclinspector.py inspect for the CLI and ./aclinspector.py web for the web UI.
Vendor-specific ASA parsing has moved into parsers/asa.py.
"""

import sys


def main() -> None:
    print("This script is deprecated. Use ./aclinspector.py inspect instead.")
    sys.exit(2)


if __name__ == '__main__':
    main()

