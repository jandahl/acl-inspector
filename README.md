Access-List Inspector
=====================

Migration Plan (In Progress)
----------------------------
- Split `cli/access-list-web.py` into modular packages (`webui/server.py`, `webui/handlers`, `webui/templates`, `webui/themes`, `webui/indexer`, `webui/state`, `webui/settings`) so each concern is isolated and testable.
- Introduce a JSON settings loader that feeds both CLI and container builds; CLI/env flags continue to override settings.
- Treat experimental features as opt-in “beta” modules under `webui/beta/`, toggled via the settings file.
- Replace the monolithic entrypoint with a thin bootstrap once the refactor lands; no legacy shim required before production.

Overview
--------
The tool parses firewall configurations (currently Cisco ASA and FortiGate with interface/zone-aware policies + NAT metadata) to:
- Resolve network objects and object-groups to concrete addresses/networks
- Flatten ACL entries (source/destination) for impact analysis
- Inspect a single IP/object to list all ACL entries affecting it
- Compare two targets (old/new) to show rules added/removed
- Detect duplicate network-objects mapping to the same IP/network

Why it exists
-------------
Firewall changes often involve swapping an object or moving workloads. This tool answers:
- What ACL rules currently hit a host/object?
- If I replace object A with object B, what changes in rule impact?
- Are there duplicate objects mapping to the same address that might surprise us?

Requirements
------------
- Python 3.9+
- No external packages are required for CLI and web UI use
- TUI requires `textual` and `rich` (install with `pip install -e '.[tui]'` or `pip install 'textual>=0.60' rich`)

Setup
-----
- Run `make themes` to download/update the optional iTerm2 color scheme files used by the web UI Preferences tab. The palettes come from the [iTerm2-Color-Schemes](https://github.com/mbadolato/iTerm2-Color-Schemes) project (MIT); see `THIRD_PARTY_NOTICES.txt` for attribution.
- Run `make fonts` to fetch libre font families — Inter, Atkinson Hyperlegible, Ubuntu, Ubuntu Mono, Source Sans 3, JetBrains Mono, Fira Code, Source Code Pro — into `fonts/downloaded/`. Set `FORCE=1` to refresh. Add your own fonts by dropping a `manifest.json` + font files under `fonts/custom/` (see inline comments in `fonts/fonts.json`).
- For live development, use `make web-watch` (optionally `POLL=60 make web-watch` to poll once a minute). The helper watches `.py/.html/.css/.js` files and restarts the server when they change.

Tool layout
-----------
- `aclinspector.py` – single entry point that dispatches to the production tools below (`./aclinspector.py web …`, `./aclinspector.py translate …`, etc.).
- `cli/` – production scripts (`access-list-inspector.py`, `access-list-web.py`, `acl-inspector-tui.py`, `acl-ir-translate.py`, `acl-optimize.py`). You can run them directly via `python3 cli/<script>.py` if you prefer.
- `parsers/` – vendor-specific config ingestion logic. Designed to be reused independently by other tools via the unified loader or Intermediate Representation (IR). See `parsers/README.md` for integration details.
- `dev/` – developer harnesses (`test_tabs_manual.py`, `test_tui_simple.py`).
- `common/` – shared helpers (`vendor_caps.py` today, future cross-surface modules).
- See `docs/ROOT_STRUCTURE.md` for a full directory map and workflow guide.

Quick start (CLI)
-----------------
- Inspect a host/object:
  `./aclinspector.py inspect --vendor asa --config <asa.conf> --inspect <ip|cidr|object>`

  - With protocol/port filtering:
    `./aclinspector.py inspect --vendor asa --config <asa.conf> --inspect <target> --proto tcp --dport 443 --dport 1433`

- Compare two targets:
  `./aclinspector.py inspect --vendor asa --config <asa.conf> --old <ip|cidr|object> --new <ip|cidr|object>`

- Packet path check (NAT + ACL prototype for ASA and FortiGate):
  - ASA: `./aclinspector.py inspect --vendor asa --config <asa.conf> --packet --packet-src <ip|object> --packet-dst <ip|object> --proto tcp --dport 443`
  - FortiGate: `./aclinspector.py inspect --vendor fortigate --config <ftg.conf> --vdom root --packet --packet-src <ip|object> --packet-dst <ip|object> --proto tcp --dport 443`

- Find host across configs:
  - Directory: `./aclinspector.py inspect --vendor asa --config /path/to/configs/cisco --find-host <ip|cidr|object>`
  - Single file: `./aclinspector.py inspect --vendor asa --config /path/to/asa.conf --find-host <ip|cidr|object>`

- FortiGate with VDOM:
  - Inspect: `./aclinspector.py inspect --vendor fortigate --config <ftg.conf> --vdom root --inspect <ip|object>`
  - Compare: `./aclinspector.py inspect --vendor fortigate --config <ftg.conf> --vdom root --old <A> --new <B>`

Reading configs from stdin
--------------------------
When ACL configs are generated dynamically (for example, pulled from an API, unpacked from an archive, or trimmed on the fly),
you can pass them straight to the CLI without creating a temporary file. Supplying `--config -` instructs
the inspector CLI to read the ASA or FortiGate configuration from standard input. This works for every mode that
normally accepts `--config <path>`:

- Inspect from stdin:
  ```bash
  cat configs/cisco/sample-asa.conf | ./aclinspector.py inspect --vendor asa --config - --inspect WebServer01
  ```

- Compare targets using stdin:
  ```bash
  zcat latest-export.asa.gz | ./aclinspector.py inspect --vendor asa --config - --old AppSrvA --new AppSrvB
  ```

- Find host in a streamed config:
  ```bash
  curl https://example.com/asa.conf \ 
    | ./aclinspector.py inspect --vendor asa --config - --find-host 10.20.30.40
  ```

While reading from stdin the script can still emit human-readable text, JSON (`--format json`), or XML (`--format xml`), and
all protocol/port filters remain available.

Output formats
--------------
- Human-friendly text (default), with clearer section names and optional ANSI colors (auto-enabled on TTY).
- Structured output for automation:
  - JSON: `--format json`
  - XML: `--format xml`
- Disable colors: `--no-color`

Examples
--------
- Print examples and exit:
  `./aclinspector.py inspect --examples`

- Inspect with protocol/port filter:
  `./aclinspector.py inspect --vendor asa --config <asa.conf> --inspect <target> --proto tcp --dport 443 --dport 1433`

- Compare with a port filter:
  `./aclinspector.py inspect --vendor asa --config <asa.conf> --old <A> --new <B> --proto udp --dport 53`

Outputs
-------
- Inspection prints:
  - Resolved target addresses
  - Matched ACL lines (raw)
  - Matched ACL entries (flattened src/dst + proto/ports or service-group)
  - Other objects mapping to the same address/network (duplicates)

Notes on parsing
----------------
- Default comparison includes protocol/port information as part of the rule identity (raw ACL line), so differences reflect service changes, too. Optional `--proto/--dport` can further constrain matches.
- ASA tokens `any`, `any4` and `any6` are supported
- Service object(-group) names at the protocol position are consumed to prevent token spillover
 - Optional port-aware filtering is supported via `--proto` and `--dport`

TUI (Terminal User Interface)
------------------------------
- Launch the interactive terminal UI:
  - `python3 -m tui` (loads ASA + Forti directories by default)
  - `./aclinspector.py tui` (same experience as `python3 -m tui`; optionally add `--vendor fortigate`, `--config <path>`, or `--vdom <name>`)
  - Use `--vendor asa|fortigate|all` and `--config /path/or/file` to override roots

- Features:
  - **Fuzzy search**: Real-time search across all objects with keyboard navigation (up/down/j/k)
  - **Multi-config support**: Load single files or entire directories (per vendor or across vendors)
  - **Drill-down tabs**: Details, Inspect, Compare, Used in ACLs, Path Check (Forti + ASA)
  - **Export functionality**: Export results to JSON/CSV/TXT (Ctrl+E)
  - **Filters**: Protocol/port/action filters in Inspect tab
  - **Interactive settings**: Configure display, search, and advanced options (Ctrl+Shift+S)
  - **Theme toggle**: Switch between dark/light themes (Ctrl+T)
  - **Path check**: Simulate packet flows through NAT and ACLs (ASA + FortiGate)
  - **Vendor hints**: Title banner shows the selected vendor and which modes are supported (Inspect/Compare/Find/Packet)

- Keyboard shortcuts:
  - `Ctrl+O`: Main menu
  - `F1`: Help screen
  - `Ctrl+E`: Export current tab
  - `Ctrl+T`: Toggle theme
  - `Ctrl+Shift+S`: Settings
  - `ESC`: Navigate back
  - `Left/Right`: Switch tabs
  - `Up/Down` or `j/k`: Navigate results

- Settings are persisted to `~/.config/acl-inspector/tui-settings.json`

- See `docs/TUI_QUICKSTART_GUIDE.md` for detailed usage instructions

Web UI
------
- Start a simple local UI (default port 8083):
  `./aclinspector.py web` or `make web` (use `WEB_PORT=8080 make web` to override)

- The UI lists config files from the following directories by default:
  - ASA: `configs/cisco`
  - FortiGate: `configs/fortigate`

- Override directories:
  - `--configs-cisco /path/to/asa/configs`
  - `--configs-fortigate /path/to/fortigate/configs`
  - Or via make: `make web CONFIGS_CISCO=/path/to/asa CONFIGS_FORTIGATE=/path/to/ftg`

- Environment variables (useful for containers/compose):
  - `ACLINSPECTOR_CONFIGS_CISCO=/data/asa` (defaults to `configs/cisco`)
  - `ACLINSPECTOR_CONFIGS_FORTIGATE=/data/fortigate` (defaults to `configs/fortigate`)
  - Both can point to the same directory if production layouts are unified. Vendor detection heuristics can be added later; for now select the vendor in the UI to parse appropriately.
  - `ACLINSPECTOR_PREWARM_ALL=1` eagerly builds the suggestion index for every config at startup (same as `--prewarm-all-configs`).
- Container helper targets:
  - `make container-stop` stops the running container but keeps its filesystem.
  - `make container-prune` removes the container while preserving the built image layers (fast rebuilds).
  - `make container-clean` removes the container, associated volumes, and cached images (full reset).

- Predictive search and metadata:
  - The UI offers prefix-based suggestions for target inputs (objects, groups, literals) using a JSON API.
  - Endpoints (internal):
    - `/api/objects?vendor=asa&os=ASA&version=auto&config=<file>&q=<prefix>&limit=50`
    - `/api/meta?vendor=asa&config=<file>`
    - `/api/aliases?vendor=asa&config=<file>&target=<name|ip|cidr>`
  - Default suggestion limit: 50 (override with `--search-limit` or env `ACLINSPECTOR_SEARCH_LIMIT`).
  - Search modes: checkbox in the UI toggles fuzzy search (default on). When enabled, matching uses case-insensitive subsequence scoring so e.g. `SQL` matches `Sidzvsql05`.
- Modes are organized as tabs: **Inspect / Compare** share a workspace with the rule filters, while **Find host** and **Packet check** get dedicated views. Switching tabs updates the hidden `mode` field that the server expects.
  - Config tab renders the selected ASA config with a live filter; Preferences tab lets you pick dark/light themes from the bundled palette (`make themes`).
  - Packet check tab evaluates a single flow through NAT + ACL (ASA prototype).
  - Packet probe tab (beta) exposes the experimental `/api/probe` endpoint. It reuses the flattened ACL view and current NAT evaluation; expect ASA support first, with richer NAT coverage staged on the roadmap.
- Preferences now include a **Debug** section with buttons to flush server caches (index + history) and reset browser-side settings/local storage.
- Looking ahead: we are exploring a simplified "V2" GUI — centred on one large search field with fuzzy, ranked suggestions (object/IP shown left, context/right-aligned). After selecting a target, the UI would preload the data in the background and reveal the relevant analysis views via bold, segmented toggles instead of the current tab matrix.

License
-------
This project is licensed under the Mozilla Public License Version 2.0 (MPL-2.0). 
See the `LICENSE` file for the full text.

Dual Licensing
~~~~~~~~~~~~~~
As the sole copyright holder, the author retains the right to grant alternative commercial licenses. By contributing to this project, you agree that your contributions are licensed under the MPL-2.0 and that the author retains the right to dual-license the collective work. 

If you require a different license for proprietary integration or other commercial purposes that are incompatible with the MPL-2.0, please see `COMMERCIAL_LICENSE.md` or contact the author at <email@example.com> to negotiate an alternative license.

For contribution guidelines and CLA terms, see `CONTRIBUTING.md`.

Third-party Notices
-------------------
- The optional color schemes under `themes/` are sourced from the [iTerm2-Color-Schemes](https://github.com/mbadolato/iTerm2-Color-Schemes) project (MIT). Use `make themes` or `make themes-refresh` to synchronize with their latest palettes.

- Dark mode and CSS:
  - Dark mode is default; use the switch in the toolbar to toggle.
  - The markup uses CSS classes (e.g., `.section`, `.diff`, `.diff-raw`, `.diff-flattened`, `.diff-added`, `.diff-removed`, `.diff-aliases-*`) so layout can be refined via CSS.

- Optional disk cache for predictive index:
  - Enable with `--cache-dir /app/cache` or set env `ACLINSPECTOR_CACHE_DIR=/app/cache`.
  - Cache is invalidated when the source config file is newer (mtime/size check).
  - Compose uses environment variable expansion; `.env` is optional. If you create `Dockersetup/.env`, values like `ACLINSPECTOR_SEARCH_LIMIT=100` will be picked up automatically by compose. No failure occurs if `.env` is missing.
  - Index status endpoint: `GET /api/index/status` returns a small JSON summary of in-memory and disk cache state.

Repo indexing (pre-warm cache)
------------------------------
- A minimal indexer is provided to scan a repository of configs and prebuild indices compatible with the web UI cache.
- Usage:
  - `python3 scripts/index_repo.py --root /path/to/rancid/checkout --cache-dir ./cache`
  - Optional flags: `--vendors asa,fortigate` to scope indexing, `--max-size 2097152` to skip oversized files.
  - Or via make: `make index ROOT=/path/to/rancid/checkout CACHE=./cache`
- The indexer skips hidden files/dirs, applies improved vendor heuristics (ASA + FortiGate), and records per-file scores/reasons in `manifest.json` along with totals and settings, making `/api/index/status` summaries more informative.

Next steps (roadmap)
--------------------
- ASA NAT parsing and normalization (priority)
  - Parse object/auto NAT and manual NAT (sections 1/2/3), dynamic/static PAT, and policy NAT; codify rule order.
  - Add unit tests covering representative NAT variants and precedence.
- Split vendor parsers into focused modules (tokenisation, object/group resolution, NAT, flattening) to keep files manageable as new vendors are introduced.
- Interface and ACL context mapping (ASA)
  - Associate ACLs to interfaces/direction; capture global policy where feasible.
  - Extend flattened entries with interface context for path evaluation.
- Path check prototype (ASA first)
  - CLI `acl-path --src IP --dst IP --proto tcp --dport 443 --config file` for single‑device evaluation.
  - Web: add a new “Path” tab; return a hop‑by‑hop explanation JSON and a concise verdict.
- Repository indexing enhancements
  - Improve vendor detection; expose `/api/index/status` to summarize cache coverage and staleness.
- FortiGate follow‑up
  - Parse policy/NAT basics and record FortiOS version metadata; document syntax differences across 7.2/7.4/7.6.

Intermediate Representation (IR)
--------------------------------
To support multi-vendor parsing and future transforms ("LLVM style"), we will normalize configs into a stable IR that the CLI/UI consume. Initial scope (ASA):
- Device: id, vendor, os, version
- Interfaces: name, ipv4/ipv6, security-level
- Objects: network objects, network object-groups (resolved and referenced), service object-groups
- ACL entries (flattened): action, proto/service, src/dst endpoint sets, interface context (once mapped)
- NAT rules: type (auto/object/manual), section, original/translated 5‑tuple selectors, order
- Routes (basic): static routes with next-hop

IR goals:
- JSON-serializable; versioned schema; minimal surface required by the app
- Reusable across vendors; FortiGate parser will target the same IR
- Backwards-compatible evolution (additive fields) with tests guarding schema

Optional syntax highlighting (planning)
--------------------------------------
For the web UI, output highlighting is optional and controlled by a toggle (state is remembered in the browser). Current implementation uses a lightweight regex-based highlighter for ASA tokens with no external deps. If we later vendor a library (Prism.js or highlight.js, MIT/BSD), we’ll include their license text in LICENSE.md and keep assets local (no network).

ASA parsing coverage (current subset)
-------------------------------------
- Interfaces: `interface`, `nameif`, `ip address`, `security-level`
- ACLs: `access-list ... extended`, plus `access-group <ACL> in interface <IF>` bindings
- Objects: `object network`, `object-group network`, nested members
- Services: basic `object-group service` with `service-object` tokens
- NAT (initial subset):
  - Auto/Object NAT inside `object network NAME`: `nat (SRC_IF,DST_IF) static|dynamic <target|interface>`
  - Manual NAT (before-auto/after-auto detection): `nat (SRC_IF,DST_IF) source static|dynamic A B [destination static|dynamic C D]`, dynamic PAT to `interface`

These fields enable building a normalized IR next and support early, single-device path evaluations.

Virtual environment
-------------------
- Create and activate a venv:
  - scripts/setup_venv.sh
  - source .venv/bin/activate

Vendor scaffolding
------------------
- Parsers for vendors live under `parsers/`.
- ASA parser resides in `parsers/asa.py`. The CLI selects a vendor and delegates.

Duplicate object detection
--------------------------
When inspecting a target (IP or object name), the tool looks up other network-objects that resolve to the same exact IP address or network and prints them. This helps find duplicate host objects like:

```
object network HOST_A
 host 10.1.1.1
object network HOST_B
 host 10.1.1.1
```

Testing
-------
- Run unit tests in the `tests` directory:
  `python3 -m unittest discover -s tests`

- Web UI smoke tests (headless Playwright):
  `make web-e2e`
  (requires `pip install playwright` and `playwright install chromium`)
- Capture reference UI screenshots:
  `python3 scripts/capture_playwright_shots.py [--output <dir>]`

- A legacy test file (`legacy/test_ASA-ACL-inspector.py`) exists; it targets an older version and may not pass. Prefer the tests under `tests/`.

Development
-----------
- Keep changes minimal and focused
- Add or update tests alongside code changes
- Validate with `python3 -m py_compile cli/access-list-inspector.py parsers/cisco/asa.py parsers/fortigate/fortigate.py`
- Self-test: `./aclinspector.py inspect --self-test`

Future goals
------------
- Web wrapper UI for inspection/compare
- Support FortiGate configs (including VDOMs) and cross-vendor compare
- Port-aware matching and reporting
- Pluggable parser architecture to support additional vendors
- Site-to-site VPN parsing/evaluation (tunnels, crypto maps/policies)
- Dockerization: containerize CLI and web UI; simple Nginx front-end to serve the web UI and reverse proxy to a WSGI app (or keep stdlib HTTPServer for simplicity). Provide read-only mount for `configs/` and export reports.
- Web UI tab autodiscovery so production and beta tabs can be surfaced dynamically from dedicated modules

Architecture (Pluggable Parsers)
--------------------------------
- Goal: support multiple firewall vendors by parsing into a shared, normalized model.
- Approach:
  - Each vendor implements a parser class that outputs flattened rules (src/dst/service).
  - Normalized dataclasses defined under `parsers/base.py` (`FlatRule`, `Endpoint`, `ServiceSpec`).
  - CLI selects the parser (auto-detect or `--vendor asa|fortigate`), then all downstream logic (inspect/compare/evaluate) runs on the normalized model.
  - This enables cross-vendor comparisons (e.g., ASA vs FortiGate) and a web UI that doesn’t care about source syntax.

Future goals
------------
- Web wrapper UI for inspection/compare
- Support FortiGate configs (including VDOMs) and cross-vendor compare
- Port-aware matching and reporting
- Pluggable parser architecture to support additional vendors
- Match scope:
  - By default, rules with `any` endpoints are ignored to reduce noise.
  - CLI: pass `--include-any` to include such rules.
  - Web UI: check “Include rules with 'any'” in the form.
