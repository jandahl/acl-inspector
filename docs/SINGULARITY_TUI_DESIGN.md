# Singularity TUI Design Specification

## Overview

The Singularity TUI (Terminal User Interface) mirrors the Singularity web UI concept but adapted for terminal environments. It provides a search-first, progressive disclosure interface for ACL inspection using the `rich` and `textual` Python libraries.

## Design Philosophy

**Search-First Interaction:**
- Single unified search field is the primary interface
- Fuzzy matching with ranked suggestions
- Contextual results based on search query
- Progressive disclosure of details

**Terminal-Native UX:**
- Keyboard-driven navigation (vim-style bindings optional)
- Mouse support for convenience
- Responsive layout that adapts to terminal size
- Rich formatting with colors and boxes

**Performance:**
- Instant search feedback (< 100ms)
- Lazy loading of large result sets
- Background indexing on startup
- Efficient terminal rendering

## Architecture

### Component Structure

```
tui/
├── __init__.py
├── app.py              # Main Textual app class
├── widgets/
│   ├── search_bar.py   # Main search input widget
│   ├── suggestion_list.py  # Fuzzy match suggestions
│   ├── detail_view.py  # Selected item details
│   ├── analysis_panel.py   # Contextual analysis results
│   └── status_bar.py   # Bottom status/help bar
├── screens/
│   ├── main.py         # Main search interface
│   ├── compare.py      # Side-by-side comparison
│   └── settings.py     # Configuration screen
├── search/
│   ├── indexer.py      # Reuse web UI indexer
│   ├── ranker.py       # Fuzzy match ranking
│   └── filters.py      # Search refinement
└── themes/
    ├── default.py      # Default color scheme
    └── loader.py       # Theme management
```

### Dependencies

**Required:**
- `textual` (>= 0.40.0) - Modern TUI framework
- `rich` (>= 13.0.0) - Rich text rendering
- Existing parsers (ASA, FortiGate)

**Optional:**
- `prompt_toolkit` - For advanced input handling
- `pyperclip` - Clipboard integration

## User Interface Flow

### 1. Launch Screen

```
┌────────────────────────────────────────────────────────────────────┐
│ ACL-inspector Singularity TUI                              [v1.0]  │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│   Search:  █                                                       │
│                                                                    │
│   Suggestions (0)                                                  │
│   ┌────────────────────────────────────────────────────────────┐  │
│   │                                                            │  │
│   │  Start typing to search network objects, ACLs, or hosts   │  │
│   │                                                            │  │
│   └────────────────────────────────────────────────────────────┘  │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│ ^C Quit │ ^R Refresh │ ^S Settings │ ^H Help                      │
└────────────────────────────────────────────────────────────────────┘
```

### 2. Search with Suggestions

```
┌────────────────────────────────────────────────────────────────────┐
│ ACL-inspector Singularity TUI                    [ASA fw1.conf]    │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│   Search:  webserver█                                              │
│                                                                    │
│   Suggestions (8)                                                  │
│   ┌────────────────────────────────────────────────────────────┐  │
│   │ ▶ WebServer01               object   10.0.0.10             │  │
│   │   WebServer02               object   10.0.0.11             │  │
│   │   WebServerGroup            group    2 members             │  │
│   │   ACL_WEBSERVER_IN          acl      12 entries            │  │
│   │   webserver-dmz.conf        context  DMZ firewall          │  │
│   │   10.0.0.10                 literal  Referenced 3x         │  │
│   │   ...                                                       │  │
│   └────────────────────────────────────────────────────────────┘  │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│ ↑↓ Select │ Enter View │ Esc Clear │ / Search                     │
└────────────────────────────────────────────────────────────────────┘
```

### 3. Detail View (Split Pane)

```
┌────────────────────────────────────────────────────────────────────┐
│ ACL-inspector Singularity TUI                    [ASA fw1.conf]    │
├──────────────────────────┬─────────────────────────────────────────┤
│ Suggestions (8)          │ Details: WebServer01                    │
│ ┌────────────────────┐   │ ┌───────────────────────────────────┐   │
│ │ ▶ WebServer01      │   │ │ Type: object network              │   │
│ │   WebServer02      │   │ │ IP: 10.0.0.10                     │   │
│ │   WebServerGroup   │   │ │ File: fw1.conf                    │   │
│ │   ACL_WEBSERVER_IN │   │ │                                   │   │
│ │   ...              │   │ │ Referenced by:                    │   │
│ └────────────────────┘   │ │   • WebServerGroup (group)        │   │
│                          │ │   • ACL_OUTSIDE_IN (line 45)      │   │
│                          │ │                                   │   │
│                          │ │ ACL Rules Affecting This Host:    │   │
│                          │ │ ┌─────────────────────────────┐   │   │
│                          │ │ │ permit tcp any host 10.0... │   │   │
│                          │ │ │ deny ip any any             │   │   │
│                          │ │ └─────────────────────────────┘   │   │
│                          │ └───────────────────────────────────┘   │
├──────────────────────────┴─────────────────────────────────────────┤
│ Tab Switch Pane │ A Analyze │ C Compare │ Q Back                   │
└────────────────────────────────────────────────────────────────────┘
```

### 4. Analysis Mode

```
┌────────────────────────────────────────────────────────────────────┐
│ Analysis: WebServer01 (10.0.0.10)                                  │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│ ┌─ Traffic Allowed To ─────────────────────────────────────────┐  │
│ │ Source: any         Protocol: tcp   Dest Port: 80, 443       │  │
│ │ Source: 10.1.0.0/16 Protocol: ssh   Dest Port: 22            │  │
│ └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│ ┌─ Traffic Allowed From ───────────────────────────────────────┐  │
│ │ Dest: any           Protocol: tcp   Src Port: ephemeral      │  │
│ └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│ ┌─ Aliases ─────────────────────────────────────────────────────┐ │
│ │ None found                                                     │ │
│ └────────────────────────────────────────────────────────────────┘ │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│ Q Back │ E Export │ F Filter                                       │
└────────────────────────────────────────────────────────────────────┘
```

## Widget Specifications

### SearchBar Widget

**Purpose:** Primary input for all queries

**Features:**
- Real-time input with debounced search (250ms)
- History navigation (↑/↓ arrows)
- Clear button (Esc or Ctrl+U)
- Input validation with visual feedback
- Fuzzy match preview as you type

**Textual Implementation:**
```python
class SearchBar(Input):
    def on_input_changed(self, event: Input.Changed) -> None:
        # Trigger search with debounce
        self.set_timer(0.25, lambda: self.post_message(SearchRequested(event.value)))

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.clear()
```

### SuggestionList Widget

**Purpose:** Display ranked search results

**Features:**
- Scrollable list with keyboard navigation
- Type badges (object/group/acl/literal)
- Relevance score indicators
- Grouped by type with headers
- Quick preview on hover

**Rendering:**
```
▶ WebServer01     [object]  10.0.0.10           ⭐⭐⭐⭐⭐
  WebServer02     [object]  10.0.0.11           ⭐⭐⭐⭐
  WebServerGroup  [group]   2 members           ⭐⭐⭐
```

### DetailView Widget

**Purpose:** Show comprehensive info about selected item

**Sections:**
- Metadata (type, IP, file, line number)
- References (where used)
- Dependencies (what it uses)
- ACL rules affecting this item
- Routing context (if applicable)

**Tabs:**
- Overview
- ACL Rules
- References
- Raw Config

### AnalysisPanel Widget

**Purpose:** Contextual analysis based on selection

**Modes:**
- **Inspect**: Show ACL rules for selected object
- **Compare**: Side-by-side diff of two items
- **Trace**: Packet flow analysis
- **Graph**: Dependency visualization (ASCII art)

## Search Modes

### 1. Simple Search
- Free text matching
- Fuzzy string matching
- Ranked by relevance

### 2. Filtered Search
```
type:object webserver
vendor:asa ip:10.0.0.0/24
acl:OUTSIDE proto:tcp port:443
```

### 3. Multi-Config Search
- Search across all loaded configs
- Group results by config file
- Highlight differences

## Keyboard Bindings

### Global
- `Ctrl+C` or `Q` - Quit
- `Ctrl+R` - Refresh/Reload
- `Ctrl+S` - Settings
- `Ctrl+H` or `?` - Help overlay
- `/` - Focus search bar
- `Esc` - Clear search / Cancel

### Navigation
- `↑/↓` or `j/k` - Navigate suggestions
- `PgUp/PgDn` - Scroll suggestions page
- `Tab` - Switch between panes
- `Enter` - Select item / View details
- `Space` - Toggle selection (multi-select)

### Actions
- `i` - Inspect selected item
- `c` - Compare mode
- `a` - Analysis mode
- `e` - Export to file
- `f` - Filter results
- `o` - Open config file (external editor)

### Vim Mode (Optional)
- `gg` - Top of list
- `G` - Bottom of list
- `dd` - Delete from history
- `yy` - Copy to clipboard

## Theme System

### Color Scheme

**Default Theme:**
```python
COLORS = {
    "primary": "cyan",
    "secondary": "blue",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "muted": "dim white",
    "background": "black",
    "text": "white",
}
```

**Semantic Colors:**
- `permit` rules: green
- `deny` rules: red
- Objects: cyan
- Groups: blue
- Literals: yellow
- ACL names: magenta

### Box Styles

Using `rich.box` styles:
- `ROUNDED` - Modern look
- `DOUBLE` - Emphasis
- `SIMPLE` - Minimal
- `ASCII` - Maximum compatibility

## Performance Targets

- **Search latency**: < 100ms for 10k objects
- **Rendering**: 60 FPS smooth scrolling
- **Memory**: < 100MB for typical configs
- **Startup**: < 2s with index preload

## Progressive Enhancement

### Phase 1: MVP (Search + Inspect)
- Search bar with fuzzy matching
- Suggestion list
- Basic detail view
- Single config support

### Phase 2: Analysis
- ACL rule inspection
- Multi-config support
- Filtering and sorting
- Export functionality

### Phase 3: Advanced Features
- Compare mode
- Packet trace
- Dependency graph
- Theme customization
- History and favorites

### Phase 4: Integration
- Web UI parity
- Shared indexer
- Config sync
- Remote access (SSH)

## Testing Strategy

### Unit Tests
- Widget behavior
- Search ranking
- Filter parsing
- Theme loading

### Integration Tests
- Full app flow
- Config parsing
- Index building
- Cross-vendor support

### Manual Testing
- Terminal compatibility (iTerm2, Terminal.app, Windows Terminal)
- Screen size adaptation
- Color scheme verification
- Keyboard navigation

## Implementation Checklist

### Core Framework
- [ ] Set up Textual app skeleton
- [ ] Create basic layout with search bar
- [ ] Implement suggestion list widget
- [ ] Add detail view pane
- [ ] Status bar with key bindings

### Search Integration
- [ ] Reuse web UI indexer
- [ ] Fuzzy match ranking
- [ ] Filter parser
- [ ] Result grouping

### Widgets
- [ ] SearchBar with debounce
- [ ] SuggestionList with scrolling
- [ ] DetailView with tabs
- [ ] AnalysisPanel modes
- [ ] StatusBar with help

### Features
- [ ] Config loader (ASA/FortiGate)
- [ ] Multi-config support
- [ ] Export to JSON/CSV
- [ ] Clipboard integration
- [ ] History tracking

### Polish
- [ ] Theme system
- [ ] Keyboard shortcuts
- [ ] Help overlay
- [ ] Error handling
- [ ] Progress indicators

## Example Usage

### Launch
```bash
# Start with ASA config
./acl-inspector-tui --vendor asa --config fw1.conf

# Multi-vendor mode
./acl-inspector-tui --configs-cisco ./asa/ --configs-fortigate ./ftg/

# Load with prebuilt index
./acl-inspector-tui --cache-dir ./cache
```

### Search Examples
```
Search: webserver
  → Find all objects/groups/ACLs matching "webserver"

Search: ip:10.0.0.10
  → Find specific IP address

Search: type:acl proto:tcp
  → Find TCP ACLs

Search: permit tcp 443
  → Find rules allowing HTTPS
```

## Future Enhancements

### Terminal Multiplexing
- Split screen for multi-config comparison
- Tmux/Screen integration
- Session persistence

### Remote Access
- SSH tunnel support
- Remote config loading
- Collaborative analysis

### AI-Assisted Search
- Natural language queries
- Smart suggestions
- Anomaly detection

### Visualization
- ASCII dependency graphs
- Traffic flow diagrams
- Heat maps for rule usage

## References

- Textual Documentation: https://textual.textualize.io/
- Rich Documentation: https://rich.readthedocs.io/
- Singularity Web UI: `webui/v2_singularity/`
- Web UI Indexer: `webui/indexer/`
