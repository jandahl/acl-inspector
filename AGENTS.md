Agent Guidelines
================

Migration Plan
--------------
- Factor the web UI into modular packages (`webui/server.py`, `webui/handlers`, `webui/templates`, `webui/themes`, `webui/indexer`, `webui/state`, `webui/settings`) to keep responsibilities focused and tests targeted.
- Add a JSON settings loader that feeds both local CLI runs and Docker builds while allowing CLI/env overrides.
- Ship experimental features as opt-in modules under `webui/beta/`, controlled via the settings file.
- Remove the monolithic `cli/access-list-web.py` once the refactor lands; the new, slimmer entrypoint will simply bootstrap the modular server.

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
- TUI (Terminal User Interface): Full-featured interactive terminal UI with fuzzy search, drill-down tabs, export functionality (JSON/CSV/TXT), protocol/port filters, interactive settings screen, path check simulation, and theme toggle. Settings persist to ~/.config/acl-inspector/tui-settings.json

Quality and linting
-------------------
- Always run a quick syntax check: `python3 -m py_compile cli/access-list-inspector.py parsers/cisco/asa.py parsers/fortigate/fortigate.py`
- If Python linters (ruff/flake8) are available locally, run them; otherwise rely on unit tests and compilation
- For shell scripts (if any), run `shellcheck` as appropriate

Tests
-----
- Use the standard library `unittest`
- Place new tests under `tests/` and prefer `python3 -m unittest discover -s tests`
- Do not modify the legacy `legacy/test_ASA-ACL-inspector.py`; it targets an older version and may not pass

Future abstractions and goals
-----------------------------
- Web wrapper page with a simple UI for inspect/compare flows (separate script)
- Simplified "V2" GUI concept: a full-screen, single entry form with large typography and a predictive search experience. Suggestions should surface object name/IP (or group) on the left and context/firewall on the right, preferring the object's primary owner. After selection, preload the relevant data server-side and reveal modal/segmented controls that guide the user through the available analysis paths on demand.
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
- Path check prototype (ASA + FortiGate)
  - CLI tool and web tab to evaluate a 5‑tuple across one device, applying NAT and ACL checks stepwise.
- Config to YAML export
  - Extend the IR/CLI output pipeline to emit YAML alongside JSON, keeping dependencies optional.
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
- `Dockerfile` and `podman-compose.yaml` are in `Dockersetup/`. Both `docker-compose` and `podman-compose` are supported; the Makefile auto-detects which is installed.
- **Entry point**: `python aclinspector.py web --port 8083 --addr 0.0.0.0`
  (the `aclinspector.py` dispatcher replaced the old `cli/access-list-web.py` entrypoint)
- **Runtime user**: `appuser` (uid/gid 1000) — container never runs as root.
- **Security properties** applied in `podman-compose.yaml`:
  - `security_opt: no-new-privileges:true` — blocks privilege escalation via setuid
  - `cap_drop: [ALL]` — no Linux capabilities needed (port 8083 > 1024, non-root)
  - `networks: internal: true` — egress-blocked bridge; no outbound internet from the container
  - `../configs:/app/configs:ro` — config volume is read-only
  - `read_only: true` — rootfs is immutable at runtime; only `/app/cache` (named volume) and `/tmp` (tmpfs) are writable
  - `tmpfs: /tmp` — 64 MiB size cap, mode 1777; provided via long-form volumes entry
  - `pids_limit: 50` — caps process count; prevents resource exhaustion
  - `stop_grace_period: 5s` — SIGTERM window before SIGKILL
- **Dockerfile ENV**: `PYTHONDONTWRITEBYTECODE=1` suppresses runtime `.pyc` write attempts (bytecode pre-compiled at build time); `PYTHONUNBUFFERED=1` flushes stdout/stderr immediately.
- **Healthcheck**: `GET /healthz` → 200 OK, interval 30 s, start grace 60 s, 5 s timeout, 3 retries.
- **OCI labels**: image carries `org.opencontainers.image.*` metadata. Inject at build time with `--build-arg VERSION=... VCS_REF=... BUILD_DATE=...`; defaults are sensible for local builds.
- **Cache volume**: named volume `aclinspector_cache` mounted at `/app/cache`; set `ACLINSPECTOR_CACHE_DIR=/app/cache` (the compose default).
- **`.env`**: copy `Dockersetup/.env.example` to `Dockersetup/.env` for variable overrides; absence is safe.
- **Convenience targets**: `make container-build`, `make container-run`, `make container-stop`, `make container-prune`, `make container-clean`, `make container-logs`.
- **Prewarming**: `ACLINSPECTOR_PREWARM_ALL=1` builds all suggestion indices at startup (slower start, faster first query).
- **CLI wrapper**: `Dockersetup/aclinspector-container` runs CLI subcommands (`inspect`, `translate`, `optimize`) ephemerally through the built image — mounts `$(pwd)` at `/data:ro`, uses `--network none`, `--read-only`, size-capped tmpfs on `/tmp` and `/app/cache`, inherits the caller's uid/gid.

Config directories
------------------
- Default directories scanned by the web UI and TUI:
  - ASA: `configs/cisco`
  - FortiGate: `configs/fortigate`
- Web UI: Override via CLI flags in `cli/access-list-web.py`: `--configs-cisco`, `--configs-fortigate`.
- TUI: Override via CLI flags in `python3 -m tui`: `--vendor`, `--config` (file or directory).

TUI (Terminal User Interface)
------------------------------
- Launch: `python3 -m tui` or `make tui`
- Architecture:
  - Built with Textual framework (Python TUI library)
  - Modular widget structure: `tui/widgets/` for reusable components
  - Screen system: `tui/screens/` for modal dialogs (settings, export, help, about)
  - State management: `tui/state.py` for settings persistence
  - Analysis core: Shared `analysis_core/` module used by both TUI and Web UI
- Key Components:
  - `tui/app.py`: Main application, search bar, keyboard routing
  - `tui/widgets/search_bar.py`: Fuzzy search input
  - `tui/widgets/suggestion_list.py`: Results list with selection
  - `tui/widgets/detail_view.py`: Tab content display
  - `tui/widgets/action_tabs.py`: Tab navigation (Details, Inspect, Compare, Used in ACLs, Path Check)
  - `tui/widgets/filter_bar.py`: Protocol/port/action filters for Inspect tab
  - `tui/screens/settings_screen.py`: Interactive settings with Select/Switch widgets
  - `tui/screens/export_screen.py`: Export dialog with format selection
  - `tui/utils/export.py`: Export manager for JSON/CSV/TXT formats
- Settings:
  - Persisted to `~/.config/acl-inspector/tui-settings.json`
  - Categories: Display, Search, Config, Advanced
  - Editable via interactive settings screen (Ctrl+Shift+S)
  - Includes: theme, line numbers, results per page, search mode, case sensitivity, max results, logging level, cache settings
- Testing:
  - Tests under `tests/test_tui_*.py`
  - Covers: export, filters, settings, tabs, navigation, multiconfig support
  - Most TUI tests skip in CI (textual framework not available in test environment)
- Documentation:
  - `docs/ROOT_STRUCTURE.md`: Current repository layout and dispatcher usage
  - `docs/SINGULARITY_SMOOTHING_PLAN.md`: Planning-only backlog for Singularity UX improvements
  - `docs/TUI_QUICKSTART_GUIDE.md`: User guide with examples
  - `docs/TUI_FEATURE_PLAN.md`: Roadmap and feature completeness plan
  - `docs/TUI_IMPLEMENTATION_SUMMARY.md`: Technical implementation details
  - `docs/TUI_COMPLETION_SUMMARY.md`: Feature completion summary
  - `docs/INTERACTIVE_SETTINGS_SUMMARY.md`: Settings screen implementation details
CLI output & structured formats
------------------------------
- Text output aims to be explicit and readable:
  - Compare headings: "New-only rules (apply to NEW, not OLD)" and "Old-only rules (apply to OLD, not NEW)"
  - Show flattened entries under each raw rule
- ANSI colors are enabled on TTY by default and can be disabled with `--no-color`
- Structured outputs for automation:
  - `--format json` (preferred for machine use)
  - `--format xml` (available; YAML can be added when a YAML dependency is acceptable)
