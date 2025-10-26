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
- Web UI: predictive search (prefix) via JSON API; UI structured with CSS classes and default dark mode with a switch; mode tabs (Inspect/Compare, Find host, Packet check, Preferences); duplicates shown in a dedicated box; optional disk cache for indices

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
 - Fuzzy predictive search (UI toggle) and a minimal repo indexer (`scripts/index_repo.py`) to prebuild indices for production repos (e.g., RANCID)

Near-term roadmap (execution order)
-----------------------------------
- ASA NAT parsing and normalization
  - Support object/auto NAT, manual NAT (sections 1/2/3), dynamic/static PAT, and policy NAT.
  - Establish matching order and rule precedence; add unit tests with sample snippets.
- Interface and ACL mapping (ASA)
  - Bind ACLs to interfaces/direction; capture global policy placement when possible.
- Path check prototype (ASA only to start)
  - CLI tool and web tab to evaluate a 5‑tuple across one device, applying NAT and ACL checks stepwise.
- Repository indexing improvements
  - Enhance vendor detection; add a cache manifest and `/api/index/status` endpoint for visibility.
- FortiGate next
  - Parse policy/NAT basics and annotate FortiOS version differences.

Intermediate Representation (IR)
--------------------------------
- Create a versioned IR module (e.g., `parsers/model.py`) with dataclasses for: `Device`, `Interface`, `Object`, `Group`, `ServiceGroup`, `ACL`, `NAT`, and `Route`.
- Vendors parse into the IR; CLI/UI consume IR only. Keep it JSON-friendly and stable.
- Guard IR evolution with unit tests to pin the schema shape and avoid regressions.

Optional syntax highlighting (web UI)
------------------------------------
- If vendoring a highlighter (Prism.js or highlight.js, MIT/BSD), copy the license into a new `LICENSE.md` under a "Third‑party" section.
- Keep highlighting off by default with a UI toggle; ship static assets to avoid runtime network fetches.

ASA parsing (current subset)
----------------------------
- Interfaces: `interface`, `nameif`, `ip address`, `security-level`
- ACLs and bindings: `access-list ... extended`, `access-group <ACL> in interface <IF>`
- Object network and object-group network
- Service object-groups (basic forms)
- NAT (subset): object (auto) NAT in `object network`, and common manual NAT `nat (IF,IF) source ... [destination ...]` and dynamic PAT to `interface`.

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
- Optional persistent cache volume for predictive index: see `Dockersetup/podman-compose.yaml` and set `ACLINSPECTOR_CACHE_DIR=/app/cache` (default) and `ACLINSPECTOR_SEARCH_LIMIT`.
- `.env` is optional. Compose will read `Dockersetup/.env` if present for variable expansion (e.g., `ACLINSPECTOR_SEARCH_LIMIT=100`); absence will not cause failures.
  - Convenience targets:
    - `make container-stop` to halt the running container.
    - `make container-prune` to remove the container while keeping the cached image layers for faster rebuilds.
    - `make container-clean` for a full reset (removes containers, volumes, and cached images).
- Startup options: `--prewarm-all-configs` (or env `ACLINSPECTOR_PREWARM_ALL=1`) builds all suggestion indexes eagerly so the UI responds instantly even on first query.

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
