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

# Optional: install developer tools (uncomment as needed)
# pip install ruff flake8

echo "Done. Activate later with: source .venv/bin/activate" >&2

