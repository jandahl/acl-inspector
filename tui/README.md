## Singularity TUI

Terminal User Interface for ACL-inspector with search-first interaction.

### Requirements

```bash
pip install textual rich
```

### Quick Start

```bash
# Launch TUI with ASA config
./aclinspector.py tui --vendor asa --config path/to/firewall.conf

# Launch with FortiGate config
./aclinspector.py tui --vendor fortigate --config path/to/fortigate.conf --vdom root
```

### Highlights

- Fuzzy search with keyboard navigation (Up/Down/j/k) and instant filtering.
- Drill-down tabs for Details, Inspect, Compare, Used in ACLs, and Path Check.
- Config-aware vendor hints directly under the title show which actions (Inspect/Compare/Find/Packet) are available for the active vendor and whether a VDOM is required.
- Export manager (Ctrl+E) for JSON/CSV/TXT plus theme toggle (Ctrl+T) and interactive settings (Ctrl+Shift+S).

### Status

**Current Implementation:** MVP skeleton (Phase 1)

**Working:**
- Basic UI layout with header/footer
- Search bar with debounced input
- Placeholder suggestion list
- Status bar with key bindings
- Keyboard navigation

**In Progress:**
- Search integration with existing indexer
- Actual result rendering
- Detail view pane
- Config loading

**Planned:**
- Analysis modes (inspect, compare, trace)
- Export functionality
- Theme customization
- History tracking

See `docs/SINGULARITY_TUI_DESIGN.md` for complete architecture specification.

### Key Bindings

- `/` - Focus search
- `↑/↓` - Navigate suggestions
- `Enter` - Select item
- `ESC` - Clear search
- `Q` or `Ctrl+C` - Quit
- `?` - Help

### Architecture

```
tui/
├── app.py              # Main Textual application
├── widgets/            # UI components
│   ├── search_bar.py   # Search input with debounce
│   ├── suggestion_list.py  # Result list widget
│   └── status_bar.py   # Bottom status/help bar
├── screens/            # (Planned) Screen views
├── search/             # (Planned) Search integration
└── themes/             # (Planned) Color schemes
```

### Development

The TUI is built with [Textual](https://textual.textualize.io/), a modern Python framework for rich terminal UIs.

To run in development mode with live reload:
```bash
textual run --dev tui/app.py
```

To explore the widget tree:
```bash
textual console
# Then run the app in another terminal
```
