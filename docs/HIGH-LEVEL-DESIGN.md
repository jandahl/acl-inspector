# High-Level Design

## Overview

Access-List Inspector parses firewall configuration files (Cisco ASA today, FortiGate in progress) and exposes both CLI and web workflows for:

- Inspecting the flattened ACL entries that affect a target object/IP.
- Comparing the delta between two targets (`old` → `new` mappings).
- Evaluating a single packet path (NAT + ACL) via the beta “packet probe”.
- Providing a Rosetta-stone reference between ASA and FortiGate examples.

The repository is being refactored into modular packages under `webui/`, with the aim of isolating parsing, state management, HTTP routing, and presentation logic.

## Parser Pipeline

Each vendor parser follows the same coarse stages:

1. **Raw ingest** – split the configuration text into lines and isolate the scope (e.g. VDOM subsection on FortiGate).
2. **Block parsing** – populate in-memory structures (`ASAConfig`, `FTGConfig`) describing objects, services, policies/ACLs, NAT, etc. The core implementations now live in `parsers/cisco/asa/parser.py` and `parsers/fortigate/config.py`.
3. **Flattening** – derive a pure data representation of ACL/policy entries. For ASA this occurs in `ASAConfig.flatten_acl()`, for FortiGate in `FTGConfig.flatten_policies()`. Flattened entries always retain the original text in the `raw` field plus structured fields such as `src`, `dst`, `svc`.
4. **Resolution helpers** – functions like `inspect_host`, `compare_old_new`, and `path_check` resolve tokens to concrete addresses, filter flattened entries, and return JSON-friendly dictionaries. These helpers are split into dedicated modules (`parsers.cisco.asa.inspect`, `parsers.cisco.asa.path`, `parsers.fortigate.inspect`).

### Public Parser APIs

- `parsers.cisco.asa.inspect_host(cfg_text, target, service_filter=None, include_any=False)` → dict with `target_nets`, `hits`, `aliases`.
- `parsers.cisco.asa.compare_old_new(cfg_text, old_target, new_target, service_filter=None, include_any=False)` → dict with `old_hits`, `new_hits`, `added_to_new`, `removed_from_old`.
- `parsers.cisco.asa.path_check(cfg_text, src, dst, proto=None, dports=None, include_any=True)` → dict describing NAT + ACL decision (`result['nat']`, `result['acl'].matches` kept flattened).
- `parsers.fortigate.fortigate.inspect_host(cfg_text, target, service_filter=None, vdom=None)` → dict equivalent to the ASA inspect helper.

All helpers now include docstrings that describe inputs, outputs, and the flattened entry shape.

## Web UI Architecture

```
client (app.js) → HTTP server (`webui/server.py`) → router (`webui/router.py`)
                                         ↓
                                 handlers/api.py    handlers/pages.py
                                         ↓
                                    `AppState` (webui/state.py)
```

- `webui/server.py` bootstraps a small `HTTPServer` that uses legacy handlers as fallback.
- `webui/router.Router` performs method/path dispatch.
- `webui/handlers/pages.py` renders the main HTML layout + partials.
- `webui/handlers/api.py` exposes JSON endpoints (`/api/objects`, `/api/meta`, `/api/probe`, `/api/cache/flush`, etc.).
- `webui/handlers/actions.py` processes form posts from the Inspect/Compare tab (legacy POST `/run`).
- `webui/static/app.js` manages UI state (localStorage persistence, tab switching, typeahead, history, beta module gating, debug tools, packet probe fetch).

### State & Caching

`webui/state.AppState` aggregates:

- Parsed settings (`webui/settings.py`), including beta module toggles.
- `DiskCache`: optional JSON cache of predictive search indices.
- `SearchIndex`: in-memory index keyed by config path.
- `IndexManager`: orchestrates fetching/invalidating indexes.
- `HistoryTracker`: captures recent form submissions for the history sidebar.

`AppState.flush_caches(include_disk=False)` is surfaced via `/api/cache/flush` (Preferences → Debug → “Flush server caches”).

### Packet Probe Flow

1. Packet Probe tab collects inputs (`probe_src`, `probe_dst`, protocol, ports, include-any).
2. Client issues `POST /api/probe` with JSON payload.
3. API validates vendor/config, invokes `asa.path_check(...)`, and returns the result.
4. UI renders NAT evaluation, flattened ACL matches, candidate bindings, and the raw JSON structure; history entry is recorded under `packet-probe`.

## Example Configurations

- `configs/cisco/cisco-asa-example` and `configs/fortigate/fortigate7-4-example` are maintained in tandem, representing the same logical flows (HTTP/HTTPS, DNS/NTP, etc.) in ASA and FortiGate syntax. Unit tests (`tests/test_examples_cross_vendor.py`) assert parity.

## Future Work / Refactor Plan

- **Parser modularisation**: split `parsers/cisco/asa.py` and `parsers/fortigate/fortigate.py` into finer-grained modules (`tokens`, `objects`, `services`, `nat`, `flatten`, `inspect`). Docstrings in this repository highlight current public I/O to guide the split.
- **Intermediate representation (IR)**: gradually move towards vendor-agnostic dataclasses (`Device`, `ACL`, `NAT`, etc.) so CLI/UI work off a shared schema.
- **Enhanced documentation**: extend this high-level design with sequence diagrams or data structure schemas as the IR stabilises.

## References

- `README.md` – user-facing overview, roadmap, environment hints.
- `docs/HIGH-LEVEL-DESIGN.md` (this document) – architecture summary.
- Parser docstrings (see above) for precise function contracts.
