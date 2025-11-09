# TUI Roadmap

## Completed Features ✅

### Core Functionality
- ✅ Search-first interface with bordered input field
- ✅ Real-time debounced search (250ms delay)
- ✅ Substring matching against network objects and groups
- ✅ Visual focus indicators (different border colors for focused widgets)
- ✅ Proper config parsing (ASA network_objects and network_object_groups)
- ✅ File logging to `./logs/TUI.log` (INFO and above)

### UX/UI
- ✅ Footer with key bindings display
- ✅ Ctrl+Q to quit
- ✅ Ctrl+M for menu/help popup
- ✅ Ctrl+T for theme toggle (dark/light)
- ✅ Tab navigation between widgets
- ✅ Focus-aware border colors (primary → accent when focused)
- ✅ Error notifications with 10-second timeout and log file reference

### Theme System
- ✅ Built-in Textual theme support (textual-dark/textual-light)
- ✅ Runtime theme switching with Ctrl+T
- ✅ Theme state shown in menu
- ✅ All colors use Textual's design tokens ($primary, $accent, $warning, etc.)
- ✅ Automatic color adaptation for light/dark modes

## Next Steps 🚀

### 1. Drill-Down / Detail View
**Priority: HIGH**

When user presses Enter on a selected result, show detailed view:

#### Design Options:
- **Option A: Split pane** - Search on left, detail on right
- **Option B: Modal overlay** - Full-screen detail with ESC to close
- **Option C: Accordion expand** - Inline expansion below selected item

#### What to show in detail view:
- **Network Objects:**
  - Name
  - All IP addresses/networks
  - Where used (which ACLs reference it)
  - Line numbers in config

- **Object Groups:**
  - Name
  - All members (recursively resolved)
  - Member count
  - Where used
  - Line numbers

- **ACLs (future):**
  - All entries
  - Bound interfaces
  - Direction (in/out)
  - Statistics (rule count, permit/deny ratio)

#### Implementation:
```python
# tui/widgets/detail_view.py
class DetailView(Container):
    """Detail panel showing object/group information."""

    def update_object(self, obj_name: str, config: ASAConfig):
        # Fetch full details
        # Render with Rich formatting
        # Show copyable text
```

### 2. Enhanced Modal Menu System
**Priority: MEDIUM**

Replace notification-based menu with proper modal screens:

#### Menu Structure:
```
┌─ Main Menu ────────────┐
│ 1. Help                │
│ 2. About               │
│ 3. Settings            │
│ 4. Export Results      │
│                        │
│ [ESC] Close            │
└────────────────────────┘
```

#### Submenus:

**Help Screen:**
- Key bindings table
- Search tips
- Feature overview
- Link to docs

**About Screen:**
- Version info
- Flag animation (from user's Python script)
- Credits
- License

**Settings:**
- Theme selection (dark/light/auto)
- Search mode (prefix/substring/fuzzy)
- Result limit
- Log level
- Config defaults

#### Implementation:
```python
# tui/modals/menu.py
from textual.screen import ModalScreen

class MainMenuScreen(ModalScreen):
    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("1", "show_help", "Help"),
        ("2", "show_about", "About"),
        ("3", "show_settings", "Settings"),
    ]
```

### 3. Selection and Navigation
**Priority: HIGH**

Currently Tab changes focus but no way to select items in results list:

#### Keyboard Navigation:
- **Up/Down arrows**: Navigate result list
- **Enter**: Open detail view for selected item
- **Space**: Toggle selection (for multi-select operations)
- **j/k**: Vim-style navigation (optional)
- **Ctrl+A**: Select all results

#### Visual Indicators:
- Highlight selected item (different background color)
- Show selection count in status line
- Cursor/arrow indicator for current item

#### Implementation:
```python
# tui/widgets/suggestion_list.py
class SuggestionList(VerticalScroll):
    selected_index = reactive(0)

    def on_key(self, event: Key) -> None:
        if event.key == "up":
            self.selected_index = max(0, self.selected_index - 1)
        elif event.key == "down":
            self.selected_index = min(len(self.results) - 1, self.selected_index + 1)
        elif event.key == "enter":
            self.post_message(self.ItemSelected(self.results[self.selected_index]))
```

### 4. Advanced Search Features
**Priority: MEDIUM**

#### Fuzzy Search:
- Use RapidFuzz or similar
- Score and rank results
- Highlight matched characters

#### Search Modes:
- **Prefix**: Current behavior (match start of name)
- **Substring**: Match anywhere (current default)
- **Fuzzy**: Intelligent matching
- **Regex**: Power user mode

#### Search Operators:
- `type:object alpha` - Filter by type
- `ip:10.0.1.0/24` - Search by IP range
- `in:acl_name` - Objects used in specific ACL

### 5. Compare Mode
**Priority: LOW**

Allow comparing two objects/groups:

```
┌─ Compare ────────────────┐
│ Left: alpha_lobby_net    │
│ Right: bravo_lobby_net   │
│                          │
│ Differences:             │
│ - IP ranges differ       │
│ - Left has 5 IPs        │
│ - Right has 8 IPs       │
└──────────────────────────┘
```

### 6. Export Functionality
**Priority: LOW**

Export search results or details:

- JSON format
- CSV format
- Markdown table
- Copy to clipboard

### 7. Live Config Reload
**Priority: LOW**

Watch config file for changes and auto-reload:

```python
from watchdog.observers import Observer

def watch_config(path, callback):
    # Monitor file changes
    # Trigger reload on modification
```

### 8. Multi-Config Support
**Priority: LOW**

Load and search across multiple configs:

- Config selector dropdown
- Search across all configs
- Aggregate results
- Show which config contains each result

## Technical Debt

### Code Organization
- [ ] Move detail view logic to separate widget
- [ ] Create modal screen classes
- [ ] Extract search logic to separate module
- [ ] Add type hints throughout
- [ ] Document all public APIs

### Testing
- [ ] Add TUI-specific unit tests
- [ ] Test keyboard navigation
- [ ] Test theme switching
- [ ] Test error handling
- [ ] Mock config parsing in tests

### Performance
- [ ] Cache parsed configs
- [ ] Lazy load large object lists
- [ ] Paginate results for huge configs
- [ ] Profile search performance

## Future Ideas

### Visualization
- Network topology view (ASCII art or graphical)
- ACL flowchart
- Object dependency graph

### Integration
- Sync with web UI session
- Export to web UI
- Import from RANCID
- Git integration for config history

### Advanced Features
- ACL simulation (packet path testing)
- Conflict detection (overlapping rules)
- Optimization suggestions
- Security audit mode

## Design Principles

1. **Search-First**: Primary interaction should be typing to search
2. **Progressive Disclosure**: Don't overwhelm with info upfront
3. **Keyboard-Driven**: Everything should be accessible via keyboard
4. **Responsive**: Instant feedback on all actions
5. **Accessible**: Clear focus indicators, good contrast
6. **Logged**: All errors and key events logged for debugging
7. **Themeable**: Respect user's light/dark preference
8. **Extensible**: Easy to add new features without breaking existing ones
