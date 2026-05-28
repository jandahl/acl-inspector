# Project Layout and Entry Points

This repository now keeps production entry points and developer tooling in
structured subdirectories. Use the following map when navigating the repo or
creating new scripts.

## Top-level entrypoints

* `aclinspector.py` – dispatcher CLI. Run `./aclinspector.py <tool> ...` to
  launch any production mode:
  * `inspect` – CLI inspector (`cli/access-list-inspector.py`)
  * `web` – legacy/modular web UI (`cli/access-list-web.py`)
  * `tui` – Textual-based terminal UI (`cli/acl-inspector-tui.py`)
  * `translate` – IR exporter/translator (`cli/acl-ir-translate.py`)
  * `optimize` – ACL optimization report generator (`cli/acl-optimize.py`)

The dispatcher sets `PYTHONPATH` automatically so all tools can import project
modules even when run outside a virtualenv.

## Directory overview

| Path        | Purpose |
|-------------|---------|
| `cli/`      | Production entry-point scripts. Each file remains executable with `python3 cli/<name>.py` but is typically invoked via `./aclinspector.py`. |
| `common/`   | Shared helper modules (currently `vendor_caps.py`) used by both CLI and UI layers. |
| `dev/`      | Developer utilities/manual harnesses (`test_tabs_manual.py`, `test_tui_simple.py`). These are not part of automated tests but are useful for exploratory work. |
| `docs/`     | All documentation, including summaries, feature plans, and this structure guide. |
| `parsers/`  | Vendor-specific config ingestion (ASA, FortiGate), unified loader, and Intermediate Representation (IR). See `parsers/README.md`. |
| `tests/`    | Automated test suites (the dispatcher tests live in `tests/test_cli_dispatcher.py`). |
| `webui/`, `tui/`, `analysis_core/` | Core packages unchanged by the reorganization. |

## Common workflows

* Run CLI inspect/compare/find: `./aclinspector.py inspect <options>`
* Start the legacy/modular web UI: `make web` (internally calls `./aclinspector.py web ...`)
* Launch the TUI: `./aclinspector.py tui [--vendor ...]`
* Translate configs via the IR pipeline: `./aclinspector.py translate export --vendor ...`
* Generate optimization reports: `./aclinspector.py optimize --config ...`

## Notes

* `make web-watch` and other automation scripts have been updated to run through the dispatcher so they inherit the same environment handling.
* If you need the raw script path (for example, IDE debugging), use the `cli/` versions directly.
* Developer-only tools live in `dev/` and should not be added to CI unless they become proper tests.
