# API Overview

This document outlines the primary Web API endpoints and capability gates that back the ACL-inspector frontends.

## Packet/Path Probe
- **Handler**: `packet_probe` in `webui/handlers/api.py`
- **Purpose**: Simulate a packet/path through a config (ASA/FortiGate).
- **Gating**: Uses vendor caps (`common.vendor_caps`) and `analysis_core.path_caps.path_check_supported` before invoking vendor path-check.
- **Inputs**:
  - `vendor`: `asa` or `fortigate`
  - `file`: config filename
  - `src`: source IP/object
  - `dst`: destination IP/object
  - `proto`: optional protocol (e.g., `tcp`)
  - `dports`: list of destination ports (strings)
  - `include_any`: boolean
  - `vdom`: FortiGate VDOM (optional)
- **Errors**:
  - `400 {"error": "packet_not_supported"}` when capability is disabled
  - `400 {"error": "invalid_config"}` when config not found
  - `400 {"error": "vendor_not_supported"}` on unknown vendor
- **Notes**: Raw config text is allowed by the capability helper so callers do not need to re-parse configs client-side.

## Compare (Web UI internal)
- Uses `analysis_core.compare.compare_objects` for both ASA and FortiGate (FTG path selected when config is an `FTGConfig`).
- Returns normalized `CompareResult` with `old_only_rules`, `new_only_rules`, `common_rules`.

## Usage / “Used in ACLs”
- Uses `analysis_core.acl_usage.find_object_usage`.
- FortiGate support includes:
  - Direct policy references
  - Addrgrp memberships (with nested recursion)
  - VIP/VIPGRP memberships
  - Indirect ACL references via group membership

## Capability helpers
- `analysis_core.path_caps.path_check_supported(config|text)`:
  - True for ASA/Forti parsed configs; True for raw config text (caller-known vendor); False for unknown objects.
- `common.vendor_caps`: registry of vendor feature flags (inspect/compare/find/packet) shared by CLI/TUI/Web.
- CLI capability flags:
  - `--list-capabilities`: prints vendor → features and exits.
  - `--default-vendor`: overrides the default vendor for a launch (propagated via `ACLINSPECTOR_DEFAULT_VENDOR` to subcommands).

## Fixtures for testing
- ASA compare/usage: `configs/fixtures/asa-compare-sample.conf`
- Forti compare/usage: `configs/fixtures/forti-compare-sample.conf`
- Forti multi-VDOM + zones: `configs/fixtures/forti-multivdom-zones.conf`
