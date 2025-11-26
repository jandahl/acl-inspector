# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ACL-inspector is a Python tool that parses firewall configurations (primarily Cisco ASA, with basic FortiGate support) to analyze Access Control Lists. It provides both a CLI and web UI for inspecting, comparing, and finding network objects and ACL rules.

**Key capabilities:**
- Resolve network objects and object-groups to concrete IP addresses/networks
- Flatten ACL entries for impact analysis
- Inspect a single IP/object to list all ACL entries affecting it
- Compare two targets (old/new) to show rules added/removed
- Detect duplicate network-objects mapping to the same IP/network
- Path check prototype: evaluate a 5-tuple flow through NAT + ACL (ASA + FortiGate)

## Essential Commands

### Development
```bash
# Run all unit tests
make unit
# or
python3 -m unittest discover -s tests -v

# Run a single test file
python3 -m unittest tests.test_nat_parsing

# Run CLI self-test
./aclinspector.py inspect --self-test

# Check syntax compilation
python3 -m py_compile cli/access-list-inspector.py parsers/cisco/asa/parser.py parsers/fortigate/fortigate.py
```

### Web UI Development
```bash
# Run web UI (default port 8083)
make web

# Run with auto-reload during development
make web-watch
# Or with custom poll interval
POLL=60 make web-watch

# Run web UI end-to-end tests (requires Playwright)
make web-e2e
```

### Container Development
```bash
# Build and run container (uses podman-compose or docker-compose)
cd Dockersetup && podman-compose -p aclinspector up --build -d

# Or use make targets
make container-run         # Build and start
make container-stop        # Stop container
make container-prune       # Remove container, keep image
make container-clean       # Full cleanup (container + volumes + images)
make container-logs        # Tail logs
```

### Repository Indexing
```bash
# Build predictive search index for a config repository
make index ROOT=/path/to/rancid/checkout CACHE=./cache
```

### Optional Setup
```bash
# Download iTerm2 color themes for web UI preferences
make themes

# Download libre fonts for web UI
make fonts
```

## Architecture

### Multi-Vendor Parser Design

The codebase is structured around a **pluggable parser architecture** that normalizes vendor-specific configs into shared data models:

**Parsing Flow:**
```
Raw Config → Vendor Parser → Intermediate Representation (IR) → CLI/Web UI
```

**Key modules:**
- **`parsers/base.py`**: Defines normalized dataclasses (`FlatRule`, `Endpoint`, `ServiceSpec`) that all vendor parsers target
- **`parsers/model.py`**: Versioned IR module with `Device`, `Interface`, `Object`, `ACL`, `NAT` dataclasses for JSON-friendly representation
- **`parsers/cisco/asa/`**: ASA-specific implementation
  - `parser.py`: Main config parsing (objects, groups, ACLs)
  - `services.py`: Service object-group handling
  - `nat.py`: NAT rule parsing (object/auto NAT, manual NAT sections 1/2/3)
  - `path.py`: Packet path evaluation through NAT + ACL
  - `inspect.py`: Object resolution and inspection logic
- **`parsers/fortigate/`**: FortiGate parser (basic support, VDOM-aware)

**Analysis layer:**
- **`analysis_core/index.py`**: Manages search indices with in-memory and disk caching
- **`analysis_core/adapters/`**: Vendor-specific index builders (`asa.py`, `fortigate.py`)

### Web UI Modular Structure (Migration in Progress)

The web UI is being refactored from a monolithic `cli/access-list-web.py` into modular packages:

**New structure:**
- **`webui/server.py`**: HTTP server bootstrap and CLI parsing
- **`webui/router.py`**: Request routing logic
- **`webui/handlers/`**:
  - `api.py`: JSON API endpoints (`/api/objects`, `/api/inspect`, `/api/compare`, etc.)
  - `pages.py`: HTML page handlers
  - `static.py`: Static asset serving
  - `actions.py`: Form submission handlers
- **`webui/state.py`**: Global app state (config paths, caches, indexer)
- **`webui/settings.py`**: JSON settings loader with CLI/env overrides
- **`webui/indexer/`**: Vendor-specific indexing adapters
- **`webui/templates/`**: Jinja2-style HTML templates
- **`webui/beta/`**: Experimental opt-in features
- **`webui/v1_legacy/`**: Legacy handlers during migration
- **`webui/v2_singularity/`**: Next-gen UI concept (single search field with fuzzy suggestions)

**Theming:**
- **`webui/themes/`**: Theme management
- **`webui/fonts.py`**: Font registry and serving

### Entry Points

- **`cli/access-list-inspector.py`**: CLI for inspect/compare/find-host operations
- **`cli/access-list-web.py`**: Legacy web UI entrypoint (being replaced by `webui/server.py`)

### Data Flow: Inspect vs Compare

**Inspect flow** (`--inspect <target>`):
1. Parse config → resolve target (IP/object/CIDR) → expand to concrete addresses
2. Iterate all ACL entries → match src/dst against target addresses
3. Apply protocol/port filters if specified (`--proto`, `--dport`)
4. Detect duplicate objects (other names resolving to same IP/network)
5. Format output (text/JSON/XML)

**Compare flow** (`--old <A> --new <B>`):
1. Resolve both targets → flatten ACL entries for each
2. Compute set difference (rules in A only, rules in B only, rules in both)
3. Report "New-only" and "Old-only" rules with flattened endpoint details
4. Include service/port information in rule identity by default

**Path check flow** (`--packet --packet-src <A> --packet-dst <B> --proto <P> --dport <N>`):
1. Parse NAT rules and ACLs with interface bindings
2. Simulate packet flow: apply NAT translation → evaluate ACL permit/deny
3. Return hop-by-hop trace with verdict (ASA + FortiGate)

## Important Parsing Details

### ASA Token Handling
- **Service groups in protocol position**: The parser consumes service object(-group) names appearing at the protocol position to prevent token spillover into src/dst parsing
- **Special tokens**: `any`, `any4`, `any6` are recognized as wildcard endpoints
- **Interface bindings**: `access-group <ACL> in interface <IF>` maps ACLs to interfaces/direction

### NAT Coverage (ASA)
Current support includes:
- **Object/Auto NAT**: Inside `object network` blocks
- **Manual NAT**: Sections 1/2/3 with `nat (SRC_IF,DST_IF) source ... [destination ...]`
- **Dynamic PAT to interface**: `nat ... dynamic interface`

### FortiGate Specifics
- Parser is VDOM-aware (use `--vdom <name>` in CLI)
- Basic policy/NAT parsing only; FortiOS version detection is planned

## Configuration & Environment

### Config Directories
- **ASA**: `configs/cisco` (override with `--configs-cisco` or `ACLINSPECTOR_CONFIGS_CISCO`)
- **FortiGate**: `configs/fortigate` (override with `--configs-fortigate` or `ACLINSPECTOR_CONFIGS_FORTIGATE`)

### Environment Variables
- `ACLINSPECTOR_CONFIGS_CISCO`: Default ASA config directory
- `ACLINSPECTOR_CONFIGS_FORTIGATE`: Default FortiGate config directory
- `ACLINSPECTOR_CACHE_DIR`: Enable disk cache for predictive search index
- `ACLINSPECTOR_SEARCH_LIMIT`: Max suggestions returned by API (default 50)
- `ACLINSPECTOR_PREWARM_ALL`: Set to `1` to build all indices at startup

### Settings File
Planned JSON settings loader (see `webui/settings.py`) will provide:
- Centralized config defaults
- Beta feature toggles
- Theme/UI preferences
- CLI/env flags will override file settings

## CLI Examples

```bash
# Inspect a host (ASA)
./aclinspector.py inspect --vendor asa --config configs/cisco/fw1.conf --inspect 10.1.1.50

# Inspect with protocol/port filter
./aclinspector.py inspect --vendor asa --config fw.conf --inspect WebServer01 --proto tcp --dport 443

# Compare two targets
./aclinspector.py inspect --vendor asa --config fw.conf --old AppSrvA --new AppSrvB

# Find host across multiple configs (directory scan)
./aclinspector.py inspect --vendor asa --config configs/cisco --find-host 192.168.1.100

# Read config from stdin
cat fw.conf | ./aclinspector.py inspect --vendor asa --config - --inspect WebServer01

# Packet path check (ASA + FortiGate)
./aclinspector.py inspect --vendor asa --config fw.conf --packet --packet-src 10.1.1.1 --packet-dst 10.2.2.2 --proto tcp --dport 443
./aclinspector.py inspect --vendor fortigate --config ftg.conf --vdom root --packet --packet-src 10.10.10.10 --packet-dst WEB-VIP --proto tcp --dport 443

# Output formats
./aclinspector.py inspect ... --format json
./aclinspector.py inspect ... --format xml
./aclinspector.py inspect ... --no-color
```

## Testing Strategy

### Unit Tests
- Use Python's standard `unittest` framework
- Test files in `tests/` directory cover:
  - NAT parsing (`test_nat_parsing.py`, `test_nat_parse.py`)
  - Path check logic (`test_path_check.py`)
  - Search index management (`test_index_status.py`)
  - IR schema stability (`test_ir_schema.py`)
  - Cross-vendor examples (`test_examples_cross_vendor.py`)
  - Network group cycle detection (`test_network_group_cycles.py`)
- **Do NOT modify** `legacy/test_ASA-ACL-inspector.py` (targets old version)

### Web UI Tests
- **E2E tests**: `tests/test_ui_playwright.py` (requires Playwright + Chromium)
- **Screenshot capture**: `scripts/capture_playwright_shots.py` for visual regression

### Test Fixtures
- Located in `tests/fixtures/`
- Include sample ASA/FortiGate configs for test coverage

## Code Style & Quality

**Conventions:**
- Python 3.9+ required, standard library preferred (no heavy dependencies)
- Keep changes minimal and focused to the task
- Match the project's direct, concise coding style
- Prefer verbose docstrings for parser internals to aid future refactors

**Quality checks:**
```bash
# Syntax compilation (always run before commit)
python3 -m py_compile cli/access-list-inspector.py parsers/cisco/asa/parser.py parsers/fortigate/fortigate.py

# Optional linters (if installed)
make lint   # Runs ruff and flake8 if available
```

## Roadmap Context

Understanding the planned evolution helps maintain architecture alignment:

**Near-term priorities:**
1. ASA NAT parsing enhancements (policy NAT, better precedence handling)
2. Interface and ACL mapping (track global vs interface-bound ACLs)
3. Path check improvements (multi-device, richer NAT coverage)
4. Config to YAML export
5. Repository indexing improvements (vendor detection, cache manifest)
6. FortiGate parser expansion (policy/NAT basics, FortiOS version tracking)

**Future goals:**
- Intermediate Representation (IR) stabilization for cross-vendor comparison
- Pluggable parser architecture formalization
- Web UI V2 ("Singularity"): single search field with fuzzy suggestions and contextual analysis views
- VPN/tunnel parsing (crypto maps, IPSec policies)

## Common Gotchas

1. **Token parsing**: Service object names in protocol position must be consumed early to prevent src/dst misalignment
2. **Interface bindings**: Not all ACLs are interface-bound; global ACLs exist
3. **NAT order**: Manual NAT sections (1/2/3) have precedence over object/auto NAT
4. **VDOM handling**: FortiGate parser requires explicit VDOM selection
5. **Cache invalidation**: Disk cache uses mtime/size checks; stale indices are rebuilt automatically
6. **Search modes**: Web UI supports both prefix and fuzzy search (toggle in UI)

## Utility Scripts

- **`scripts/setup_venv.sh`**: Create virtual environment
- **`scripts/web_autoreload.py`**: Dev server with auto-restart on file changes
- **`scripts/index_repo.py`**: Batch indexer for config repositories
- **`scripts/download_fonts.py`**: Fetch libre fonts for web UI
- **`scripts/capture_playwright_shots.py`**: Capture UI screenshots for visual regression

## Docker Notes

- **Compose file**: `Dockersetup/podman-compose.yaml`
- **Base image**: `python:3.11-slim-bookworm`
- **Exposed port**: 8083
- **Optional `.env`**: Place in `Dockersetup/` for variable expansion (e.g., `ACLINSPECTOR_SEARCH_LIMIT=100`)
- **Volumes**: Mount `configs/` from host for dynamic config updates
- **Prewarming**: Set `ACLINSPECTOR_PREWARM_ALL=1` to build all indices at startup (slower start, faster first query)

## Additional Resources

- **AGENTS.md**: Full development guidelines (migration plan, parsing rules, conventions)
- **README.md**: User-facing documentation (setup, examples, features)
- **docs/ABOUT.md**: Project context and motivation
- Unit testing is important
- This is not in production yet so "backwards compatibility" doesn't matter yet
