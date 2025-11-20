# Interface Convergence Plan (CLI / TUI / Singularity)

Goal: Treat the CLI, TUI (`cli/acl-inspector-tui.py` / `--singularitty`), and Singularity (web UI) as three shells over the same capability set, using **progressive disclosure** to reveal complexity only when requested. This enables any future parser (e.g., Palo Alto) to plug into one capability layer without bespoke frontend logic.

## 1. Current Feature Snapshot

| Feature | CLI | TUI | Singularity |
| --- | --- | --- | --- |
| Inspect (ASA) | ✅ | ✅ | ✅ |
| Inspect (Forti) | ✅ | ⚠️ (stub message) | ✅ |
| Compare (ASA) | ✅ | ⚠️ (planned) | ✅ |
| Compare (Forti) | ✅ | ⚠️ (planned) | ✅ |
| Find (ASA) | ✅ | ⚠️ (planned) | ✅ |
| Find (Forti) | ✅ | ⚠️ (planned) | ✅ |
| Packet Check (ASA) | ✅ | ✅ | ✅ |
| Packet Check (Forti) | ✅ | ✅ | ✅ |
| Config viewer | ✅ (`--translate --format`) | ⚠️ (planned) | ✅ |
| Export (JSON/CSV/TXT) | CLI options | ✅ | 🟡 (CSV/TXT planned) |

## 2. Progressive Disclosure Model

1. **Primary action** (Inspect/Compare/Find) → show targeted summary: resolved objects, top matches, next recommended action.
2. **Next complexity** revealed on demand:
   - Expandable sections for alias/group membership, interface bindings, NAT steps.
   - Tabs/panels for heavy views (raw vs flattened rules).
3. **Deeper actions** (packet check, export, cross-vendor compare) linked contextually, not all exposed upfront.

## 3. Capability Layer

Introduce a centralized `vendor_caps` registry (already started for web) describing, per vendor:

```json5
{
  "name": "fortigate",
  "supports": ["inspect", "compare", "find", "packet"],
  "config_field": "config_ftg",
  "requires_vdom": true
}
```

Each surface (CLI/TUI/web) queries this to decide:
- Which tabs/buttons to show.
- Which form fields to render (e.g., VDOM input).
- Which handlers to bind (e.g., `path_check` variant).

## 4. Immediate Convergence Tasks

1. **Web/TUI Inspect parity**:
   - Surface Forti object/group context (addrgrp members, VIP references, zones) just like ASA’s “object detail” block.
   - Use the same `_format_flat_rule` helper so CLI/TUI/web show identical summaries.
2. **Capability-driven UI toggles**:
   - Vendor selection drives tab enablement + config dropdowns automatically (no manual `if vendor ==` checks).
   - History/export state records vendor + VDOM so replay works cross-vendor.
3. **TUI alias / branding**:
   - Add `--singularitty` CLI flag that maps to `python3 -m tui` (implemented via `cli/access-list-inspector.py`).
   - Display vendor/capability hints in the TUI header so users know which modes work per device.
4. **Legacy web entry point** (`cli/access-list-web.py`):
   - Reuse the shared handlers/capability map to avoid ASA-only regressions; acts as a “bridge” for any future vendors.

Delivering these closes most gaps, letting Singularity focus on “prettier progressive disclosure” while TUI + CLI remain lean shells over the same capability core.
