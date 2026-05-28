# Installing ACL Inspector as a Python Package

ACL Inspector can be installed as a regular Python package, either into a virtual environment or system-wide. This gives you the `aclinspector` command on your `PATH` and lets you import the parsers and analysis modules from your own scripts.

## Requirements

- Python 3.9 or newer
- `pip` 21+ (ships with Python 3.9+)

## Recommended: install into a virtual environment

```bash
# Clone the repository
git clone https://github.com/jandahl/acl-inspector.git
cd acl-inspector

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows (PowerShell)

# Install in editable mode so your local checkout is live
pip install -e .
```

After activation the `aclinspector` command is available in your shell:

```bash
aclinspector inspect --help
aclinspector web
```

Deactivate the environment when you are done:

```bash
deactivate
```

## Install without editable mode (stable snapshot)

If you want a fixed installation that is not tied to the source tree:

```bash
pip install .
```

## Importing the library from your own scripts

Once installed, the parsers and analysis modules are importable directly:

```python
from parsers.cisco.asa.parser import ASAParser
from parsers.model import Device
from analysis_core.index import IndexManager

# Parse a config file
with open("my-firewall.conf") as fh:
    raw = fh.read()

parser = ASAParser()
device = parser.parse(raw)
print(device.hostname)
```

The public surface of each sub-package is documented in the corresponding module docstrings.

## Uninstalling

```bash
pip uninstall acl-inspector
```

## Troubleshooting

**`aclinspector: command not found` after install**
Make sure the virtual environment is activated (`source .venv/bin/activate`) or that the Python `bin/` directory is on your `PATH`.

**`ModuleNotFoundError` when importing without installing**
Running scripts directly from the repo root without installing requires `PYTHONPATH` to point at the repo root. The `aclinspector.py` dispatcher handles this automatically; standalone scripts do not. Installing the package (even in editable mode) is the recommended solution.
