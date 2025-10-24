Agent Guidelines
================

Scope
-----
This repository contains a Python tool to inspect and compare ACLs. Current vendor support focuses on Cisco ASA. The tool parses configs, resolves objects, reports ACL impacts, and is structured to accommodate other vendors and a separate web UI.

Coding conventions
------------------
- Python 3.9+ only; standard library preferred
- Keep changes minimal and focused to the task
- Match the project’s direct, concise coding style
- Add tests for new behavior under `tests/`
- Prefer verbose docstrings for parser internals to aid future refactors

Parsing rules
-------------
- Parse ASA `object network` and `object-group network`
- Record network-objects as exact IPv4Address or IPv4Network
- For ACL lines, extract protocol/service token and parse exactly two endpoints (src, dst), then parse trailing service/port tokens
- Recognize ASA tokens `any`, `any4`, `any6`
- Parse basic service-groups: `service-object tcp|udp` with `eq/lt/gt/neq/range`, and nested `group-object`
- Time-range and service-objects referenced by name are not resolved yet

New features in this iteration
------------------------------
- Duplicate object detection: For a given target, report other network-objects that resolve to the same IP/network
- Robust tokenization for ACL parsing: consume service object(-group) names appearing in protocol position to prevent token bleed into src/dst parsing

Quality and linting
-------------------
- Always run a quick syntax check: `python3 -m py_compile access-list-inspector.py parsers/cisco/asa.py parsers/fortigate/fortigate.py`
- If Python linters (ruff/flake8) are available locally, run them; otherwise rely on unit tests and compilation
- For shell scripts (if any), run `shellcheck` as appropriate

Tests
-----
- Use the standard library `unittest`
- Place new tests under `tests/` and prefer `python3 -m unittest discover -s tests`
- Do not modify the legacy `test_ASA-ACL-inspector.py`; it targets an older version and may not pass

Future abstractions and goals
-----------------------------
- Web wrapper page with a simple UI for inspect/compare flows (separate script)
- Nicer CSS
- Vendor abstraction: introduce a pluggable parser layer to support FortiGate (with VDOMs) and others
- Cross-vendor diff: normalize flattened entries to a common model for comparison
- Port-aware matching and richer rule reporting (service/ports) [in progress: basic filtering via --proto/--dport]

Docker notes
------------
- Containerization plan:
  - Base image with Python 3.11+; copy repo; optional install of linters
  - Entrypoints: CLI (`access-list-inspector.py`) and web UI (`access-list-web.py`)
  - Expose a port for web UI; mount `configs/` from host for UAT files
  - Optionally place Nginx in front of the web UI for TLS/headers, or run UI directly
  - Local testing will be using `podman`, production will be using `docker`
- Current setup for web UI:
  - `Dockerfile` and `podman-compose.yaml` are located in `Dockersetup/`.
  - The web UI listens on port `8083`.
  - To build and run the container using `podman-compose` (from the project root):
    ```bash
    cd Dockersetup && podman-compose -p aclinspector up --build -d
    ```
    Access the web UI at `http://localhost:8083`.

Config directories
------------------
- Default directories scanned by the web UI:
  - ASA: `configs/cisco`
  - FortiGate: `configs/fortigate`
- These can be overridden via CLI flags in `access-list-web.py`: `--configs-cisco`, `--configs-fortigate`.
CLI output & structured formats
------------------------------
- Text output aims to be explicit and readable:
  - Compare headings: "New-only rules (apply to NEW, not OLD)" and "Old-only rules (apply to OLD, not NEW)"
  - Show flattened entries under each raw rule
- ANSI colors are enabled on TTY by default and can be disabled with `--no-color`
- Structured outputs for automation:
  - `--format json` (preferred for machine use)
  - `--format xml` (available; YAML can be added when a YAML dependency is acceptable)
