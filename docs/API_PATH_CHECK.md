# Path Check API and Capability Gating

This note documents how path/packet check is gated across the shared core and frontends.

## Core helper
- `analysis_core.path_caps.path_check_supported(config: Any) -> bool`:
  - Returns `True` when the vendor/config supports packet/path checking.
  - Accepts parsed configs (ASA/FTG) or raw config text. Raw text is allowed to keep API use simple; unknown objects return `False`.
  - Frontends (TUI/Web) call this before surfacing or executing the Path/Packet Check feature.

## TUI
- Uses `_effective_caps` to disable the Path tab when `path_check_supported` is false for the current config/vendor.
- Headless regression test: `tests/test_tui_tabs.py::test_path_tab_gating`.

## Web API
- Endpoint: `packet_probe` in `webui/handlers/api.py`.
- Before invoking vendor path check, it validates vendor caps and `path_check_supported`.
- Errors:
  - `400 {"error": "packet_not_supported"}` when capability is disabled.
  - Other 400s/500s for invalid config/vendor/read failures.

## Vendor support
- ASA: supported (see `common.vendor_caps`).
- FortiGate: supported (with VDOM handled by caller).
- Unknown vendors/configs: gated off by default.

## Fixtures
- ASA compare/usage fixture: `configs/fixtures/asa-compare-sample.conf`
- Forti compare/usage fixture: `configs/fixtures/forti-compare-sample.conf`

