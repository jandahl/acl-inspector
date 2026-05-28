#!/usr/bin/env bash
set -euo pipefail

# Create and initialize a local virtual environment for this project.
# Usage: scripts/setup_venv.sh

if [ -d .venv ]; then
  echo ".venv already exists; skipping creation" >&2
else
  python3 -m venv .venv
  echo "Created .venv" >&2
fi

echo "Activating .venv and upgrading pip..." >&2
source .venv/bin/activate
python -m pip install --upgrade pip

# Install the package in editable mode so the aclinspector command is on PATH
# and all sub-packages (parsers, common, etc.) are importable from anywhere.
pip install -e .

# Optional extras — uncomment what you need:
# pip install -e ".[tui]"          # TUI: textual + rich
# pip install -e ".[dev]"          # Linters: ruff + flake8 (matches make lint)
# pip install -e ".[test]"         # E2E tests: playwright (also run: playwright install chromium)
# pip install -e ".[dev,test]"     # All of the above

echo "Done. Activate later with: source .venv/bin/activate" >&2
