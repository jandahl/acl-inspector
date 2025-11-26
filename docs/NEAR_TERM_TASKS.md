# Near-term Task Tracker

This tracker lists actionable items pulled from the current strategy docs. It
focuses on work we can push forward immediately without large cross-team
coordination. Status is intentionally lightweight so we can adjust priorities
as new discoveries surface.

## FortiGate Support Plan (`docs/FORTIGATE_SUPPORT_PLAN.md`)

| Task | Status | Notes / Next action |
| --- | --- | --- |
| Additional fixture covering multi-VDOM + zones | ✅ Done | Added `configs/fixtures/forti-multivdom-zones.conf` with tests for VDOMs/zones flattening. |
| Parser stack refactor | Planned | Build stack-based parser per `fortigate-expert` brief to keep VDOM context; break into incremental PRs (e.g., `config firewall address`, then policies, etc.). |
| NAT + interface semantics in path-check | Planned | Thread per-policy `set srcintf/dstintf`, VIP references, and `central-snat-map` into packet simulator; expose warnings in UI once parser emits the metadata. |

## Interface Convergence Plan (`docs/INTERFACE_CONVERGENCE_PLAN.md`)

| Task | Status | Notes / Next action |
| --- | --- | --- |
| Capability-driven UI toggles across all surfaces | In progress | Web + TUI use `vendor_caps` + `path_check_supported`; CLI now has `--list-capabilities` and `--default-vendor` (capability summary embedded in help). |
| History/export metadata parity | Planned | Ensure TUI + Singularity persist vendor/vdom info in history entries so replay behaves like CLI. |
| Web Inspect parity (Forti context blocks) | Planned | Surface Forti object membership (addrgrp, VIP, zones) in the Inspect tab similar to ASA detail cards. |

## TUI Feature Plan (`docs/TUI_FEATURE_PLAN.md`)

| Task | Status | Notes / Next action |
| --- | --- | --- |
| Vendor hint banner under title | ✅ Complete (Nov 2025) | Shows vendor label + capabilities pulled from `common.vendor_caps`. |
| Details tab enhancements | In progress | Next slices: NAT/interface binding info + “copy to clipboard” piping. Needs data from parser. |
| Inspect tab quick filters | Planned | Add protocol/port/action quick toggles plus CSV/JSON export buttons. |
| Compare tab diff table | Planned | Render old/new/status columns and export diff; reuse `_format_flat_rule`. |

## Singularity Smoothing Plan (`docs/SINGULARITY_SMOOTHING_PLAN.md`)

| Task | Status | Notes / Next action |
| --- | --- | --- |
| Preload + cache plan | Planned | Add lightweight preload script and query caching to reduce first-keystroke latency (planning only for now). |
| Keyboard affordances | Planned | Track shortcuts (Ctrl+K launcher, consistent arrow behaviour) in the backlog to implement after preload work. |
| Inline filters | Planned | Design mock for protocol/port filters directly under the search field; ensure parity with CLI/TUI filters. |

This file will evolve as we chip away at each slice; update status and notes as soon as a task is completed or reprioritized.
