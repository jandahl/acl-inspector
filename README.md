Access-List Inspector
=====================

Migration Plan (In Progress)
----------------------------
- Split `access-list-web.py` into modular packages (`webui/server.py`, `webui/handlers`, `webui/templates`, `webui/themes`, `webui/indexer`, `webui/state`, `webui/settings`) so each concern is isolated and testable.
- Introduce a JSON settings loader that feeds both CLI and container builds; CLI/env flags continue to override settings.
- Treat experimental features as opt-in “beta” modules under `webui/beta/`, toggled via the settings file.
- Replace the monolithic entrypoint with a thin bootstrap once the refactor lands; no legacy shim required before production.

Overview
--------
The tool parses firewall configurations (currently Cisco ASA; rudimentary FortiGate) to:
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
- No external packages are required

Setup
-----
- Run `make themes` to download/update the optional iTerm2 color scheme files used by the web UI Preferences tab. The palettes come from the [iTerm2-Color-Schemes](https://github.com/mbadolato/iTerm2-Color-Schemes) project (MIT); see `LICENSE` for attribution.
- Run `make fonts` to fetch libre font families — Inter, Atkinson Hyperlegible, Ubuntu, Ubuntu Mono, Source Sans 3, JetBrains Mono, Fira Code, Source Code Pro — into `fonts/downloaded/`. Set `FORCE=1` to refresh. Add your own fonts by dropping a `manifest.json` + font files under `fonts/custom/` (see inline comments in `fonts/fonts.json`).
- For live development, use `make web-watch` (optionally `POLL=60 make web-watch` to poll once a minute). The helper watches `.py/.html/.css/.js` files and restarts the server when they change.

Quick start (CLI)
-----------------
- Inspect a host/object:
  `./access-list-inspector.py --vendor asa --config <asa.conf> --inspect <ip|cidr|object>`

  - With protocol/port filtering:
    `./access-list-inspector.py --vendor asa --config <asa.conf> --inspect <target> --proto tcp --dport 443 --dport 1433`

- Compare two targets:
  `./access-list-inspector.py --vendor asa --config <asa.conf> --old <ip|cidr|object> --new <ip|cidr|object>`

- Packet path check (NAT + ACL prototype):
  `./access-list-inspector.py --vendor asa --config <asa.conf> --packet --packet-src <ip|object> --packet-dst <ip|object> --proto tcp --dport 443`

- Find host across configs:
  - Directory: `./access-list-inspector.py --vendor asa --config /path/to/configs/cisco --find-host <ip|cidr|object>`
  - Single file: `./access-list-inspector.py --vendor asa --config /path/to/asa.conf --find-host <ip|cidr|object>`

- FortiGate with VDOM:
  - Inspect: `./access-list-inspector.py --vendor fortigate --config <ftg.conf> --vdom root --inspect <ip|object>`
  - Compare: `./access-list-inspector.py --vendor fortigate --config <ftg.conf> --vdom root --old <A> --new <B>`

Reading configs from stdin
--------------------------
When ACL configs are generated dynamically (for example, pulled from an API, unpacked from an archive, or trimmed on the fly),
you can pass them straight to the CLI without creating a temporary file. Supplying `--config -` instructs
`access-list-inspector.py` to read the ASA or FortiGate configuration from standard input. This works for every mode that
normally accepts `--config <path>`:

- Inspect from stdin:
  ```bash
  cat configs/cisco/sample-asa.conf | ./access-list-inspector.py --vendor asa --config - --inspect WebServer01
  ```

- Compare targets using stdin:
  ```bash
  zcat latest-export.asa.gz | ./access-list-inspector.py --vendor asa --config - --old AppSrvA --new AppSrvB
  ```

- Find host in a streamed config:
  ```bash
  curl https://example.com/asa.conf \ 
    | ./access-list-inspector.py --vendor asa --config - --find-host 10.20.30.40
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
  `./access-list-inspector.py --examples`

- Inspect with protocol/port filter:
  `./access-list-inspector.py --vendor asa --config <asa.conf> --inspect <target> --proto tcp --dport 443 --dport 1433`

- Compare with a port filter:
  `./access-list-inspector.py --vendor asa --config <asa.conf> --old <A> --new <B> --proto udp --dport 53`

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

Web UI
------
- Start a simple local UI (default port 8083):
  `./access-list-web.py` or `make web` (use `WEB_PORT=8080 make web` to override)

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

Third-party Notice
------------------
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
- Validate with `python3 -m py_compile access-list-inspector.py parsers/cisco/asa.py parsers/fortigate/fortigate.py`
- Self-test: `./access-list-inspector.py --self-test`

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
