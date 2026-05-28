# ACL Inspector

## Project Overview
ACL Inspector is a Python-based tool that parses firewall configurations (specifically Cisco ASA and FortiGate) for impact analysis. It allows users to resolve network objects to concrete addresses, flatten ACL entries for better visibility, inspect ACL rules affecting specific IPs or objects, compare configurations, and detect duplicate network objects mapping to the same IP/network. 

The project provides three primary interfaces:
- **CLI**: A command-line interface for scripting and quick automated inspections.
- **TUI**: A Textual-based interactive terminal UI for navigating results.
- **Web UI**: A browser-based interface running a local webserver.

## Directory Architecture
- `aclinspector.py`: The single dispatcher entry point used to launch various tools (e.g., `./aclinspector.py inspect`, `./aclinspector.py web`).
- `cli/`: Production entry-point scripts.
- `parsers/`: Contains parsing logic specific to Cisco ASA and FortiGate configurations.
- `analysis_core/`: Core analytical logic and processing operations.
- `webui/`: Modular packages handling the web server (handlers, templates, themes, indexer).
- `tui/`: Components for the Terminal User Interface.
- `tests/`: Automated unit and end-to-end test suites.
- `docs/`: Comprehensive project documentation, including feature parity plans, architectures, and quickstarts.
- `configs/`: Sample firewall configurations (Cisco/FortiGate) and fixtures.

## Building and Running
The core application requires Python 3.9+ and uses no external packages for its primary functionalities. Make targets handle common workflows:

- **Setup Virtual Environment:** `make venv`
- **Run Unit Tests:** `make unit`
- **Run CLI Self-Test:** `make test`
- **Show CLI Examples:** `make examples`
- **Start Web UI:** `make web` (or `./aclinspector.py web`). Runs on port 8083 by default. 
- **Start Web UI (Auto-reload for dev):** `make web-watch`
- **Start TUI:** `make tui` (or `./aclinspector.py tui`)
- **Containers:** Podman and Docker Compose support is provided (e.g., `make container-build`, `make container-run`).
- **Assets:** Run `make themes` and `make fonts` to download external assets used by the UI.

## Development Conventions
- **Entry Points**: Always use `./aclinspector.py <command>` instead of directly running scripts within `cli/`. This ensures the environment and `PYTHONPATH` are correctly set up.
- **Testing**: Python's built-in `unittest` framework is used. Run `make unit` for tests. UI E2E tests are available via `make web-e2e` (requires Playwright).
- **Code Linting**: Use `ruff` and `flake8` for linting. You can execute this with `make lint`.
- **Dependencies**: For broad compatibility, avoid adding third-party packages for core analysis functions.
- **Documentation**: Updates to architectures and behaviors should be documented in `docs/` and tracked in related session summaries.
