# Getting Started with ACL Inspector

ACL Inspector can be run in several ways depending on your use case. The OCI container is the easiest path for day-to-day use via the web UI. Direct invocation from a clone suits CLI and development workflows. Installing as a Python package is mainly useful when embedding the parsers or analysis modules into your own scripts.

---

## Option 1: OCI container (web UI — easiest)

The container bundles everything and exposes the web UI on port 8083. You only need Docker or Podman.

```bash
cd Dockersetup
podman-compose -p aclinspector up --build -d
# or
docker-compose -p aclinspector up --build -d
```

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
ACLINSPECTOR_CONFIGS_CISCO=/data/asa      # replace with your host path to ASA configs
ACLINSPECTOR_CONFIGS_FORTIGATE=/data/fortigate
ACLINSPECTOR_CACHE_DIR=/cache             # enables disk cache for the search index
ACLINSPECTOR_PREWARM_ALL=1               # build all indices at startup
ACLINSPECTOR_SEARCH_LIMIT=100            # suggestion limit (default 50)
```

Place these in `Dockersetup/.env` for automatic expansion by Compose.

---

## Option 2: Run directly from a clone (CLI, web UI, or TUI)

No install step required — just clone and run.

```bash
git clone https://github.com/jandahl/acl-inspector.git
cd acl-inspector

# Optional but recommended: isolated dependencies
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\Activate.ps1      # Windows (PowerShell)
# .venv\Scripts\activate.bat      # Windows (cmd.exe)

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

> **Editable install required.** The project's modules use generic top-level names (`parsers`, `common`, `utils`, …) and the CLI dispatcher locates tools by file path. A regular `pip install .` can cause namespace collisions with other packages and will break the console script in non-source layouts. Always use `pip install -e .` inside a dedicated virtual environment.

```bash
git clone https://github.com/jandahl/acl-inspector.git
cd acl-inspector

python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\Activate.ps1      # Windows (PowerShell)

# Editable install — source tree is used directly, no copying to site-packages
pip install -e .

# Also want the TUI?
pip install -e ".[tui]"
```

This also puts the `aclinspector` command on your `PATH`:

```bash
aclinspector inspect --help
```

### Importing the library

```python
from parsers.cisco.asa.parser import ASAConfig

with open("my-firewall.conf") as fh:
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
| TUI (terminal interface) | Direct clone + `pip install textual rich` |
| Embedding parsers in your own scripts | pip install -e . (Option 3) |
