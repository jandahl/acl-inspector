# Getting Started with ACL Inspector

ACL Inspector can be run in several ways depending on your use case. The OCI container is the easiest path for day-to-day use via the web UI. Direct invocation from a clone suits CLI and development workflows. Installing as a Python package is mainly useful when embedding the parsers or analysis modules into your own scripts.

---

## Option 1: OCI container (web UI — easiest)

The container bundles everything and exposes the web UI on port 8083. You only need Docker or Podman.

```bash
cd Dockersetup
podman-compose -f podman-compose.yaml -p aclinspector up --build -d
# or
docker-compose -f podman-compose.yaml -p aclinspector up --build -d
```

Alternatively, use the `make` shortcuts from the repo root (they pass the correct `-f` flag automatically).

Mount your configs and open `http://localhost:8083` in a browser.

Useful `make` shortcuts:

| Command | Effect |
|---|---|
| `make container-run` | Build and start |
| `make container-stop` | Stop, keep filesystem |
| `make container-prune` | Remove container, keep image |
| `make container-clean` | Full reset (container + volumes + images) |
| `make container-logs` | Tail logs |

Environment variables accepted by the container:

```
# Replace with the host paths where your configs live
ACLINSPECTOR_CONFIGS_CISCO=/data/asa
ACLINSPECTOR_CONFIGS_FORTIGATE=/data/fortigate
# Enables disk cache for the predictive search index
ACLINSPECTOR_CACHE_DIR=/cache
# Build all indices at startup (slower start, faster first query)
ACLINSPECTOR_PREWARM_ALL=1
# Suggestion limit (default 50)
ACLINSPECTOR_SEARCH_LIMIT=100
```

Place these in `Dockersetup/.env` for automatic expansion by Compose. Note: `.env` files do not support inline comments — comments must be on their own lines as shown above.

---

## Option 2: Run directly from a clone (CLI, web UI, or TUI)

No install step required — just clone and run.

```bash
git clone https://github.com/jandahl/acl-inspector.git
cd acl-inspector

# Optional but recommended: isolated dependencies
python3 -m venv .venv
source .venv/bin/activate           # macOS / Linux
# .\.venv\Scripts\Activate.ps1   # Windows (PowerShell)
# .\.venv\Scripts\activate.bat   # Windows (cmd.exe)

# CLI
./aclinspector.py inspect --vendor asa --config configs/cisco/fw.conf --inspect 10.1.1.1

# Web UI (default port 8083)
./aclinspector.py web
# or
make web

# TUI (requires textual — install first)
pip install "textual>=0.60" rich
./aclinspector.py tui
```

The `./aclinspector.py` dispatcher sets `PYTHONPATH` automatically, so no install is needed.

---

## Option 3: Install as a Python package (scripting / integration)

Install when you want to import the parsers or analysis modules from your own Python code. The core package has no third-party dependencies.

> **Editable install required** — not a packaging quirk, but a consequence of the project's current structure. The modules use generic top-level names (`parsers`, `common`, `utils`, …) that would collide with other installed packages in a shared environment, and the CLI dispatcher resolves sub-tools by file path on disk. Both constraints disappear once the codebase is reorganised under an `acl_inspector` namespace (tracked for a future refactor). Until then, always use `pip install -e .` inside a dedicated virtual environment.

```bash
git clone https://github.com/jandahl/acl-inspector.git
cd acl-inspector

python3 -m venv .venv
source .venv/bin/activate           # macOS / Linux
# .\.venv\Scripts\Activate.ps1   # Windows (PowerShell)
# .\.venv\Scripts\activate.bat   # Windows (cmd.exe)

# Editable install — source tree is used directly, no copying to site-packages
pip install -e .

# TUI support
pip install -e ".[tui]"

# Linters (ruff, flake8) — matches what `make lint` expects
pip install -e ".[dev]"

# End-to-end tests (Playwright) — also requires a one-time browser install
# Re-run `playwright install chromium` after upgrading the playwright package
pip install -e ".[test]"
playwright install chromium

# Full dev environment (lint + e2e tests)
pip install -e ".[dev,test]"
playwright install chromium
```

This also puts the `aclinspector` command on your `PATH`:

```bash
aclinspector inspect --help
```

### Importing the library

```python
from parsers.cisco.asa.parser import ASAConfig

with open("my-firewall.conf", encoding="utf-8") as fh:
    raw = fh.read()

config = ASAConfig(raw)                          # parses automatically on construction

# Optional: export to the vendor-agnostic IR
device = config.to_ir(device_name="my-firewall")
print(device.name)
```

### Uninstalling

```bash
pip uninstall acl-inspector
```

---

## Choosing the right option

| Situation | Recommended approach |
|---|---|
| Using the web UI regularly | OCI container |
| CLI queries, one-off analysis | Direct clone (Option 2) |
| Contributing to the codebase | Direct clone + venv |
| TUI (terminal interface) | Direct clone + `pip install "textual>=0.60" rich` |
| Embedding parsers in your own scripts | pip install -e . (Option 3) |
