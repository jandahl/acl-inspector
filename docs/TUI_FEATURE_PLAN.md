# TUI Feature Completeness Plan

## Current State

### Implemented Features
1. **Search & Discovery**
   - ✅ Fuzzy search across all objects
   - ✅ Real-time filtering of results
   - ✅ Keyboard navigation (up/down, j/k)
   - ✅ Multi-config directory support
   - ✅ Source file tracking and display

2. **Drill-Down Mode (Tabs)**
   - ✅ Details tab - Object information display
   - ✅ Inspect tab - ACL rules affecting object
   - ✅ Compare tab - Compare two objects
   - ✅ Used in ACLs tab - Where object is referenced

3. **Menu System**
   - ✅ Main menu (Ctrl+O)
   - ✅ Help screen (F1)
   - ✅ About screen
   - ✅ Theme toggle (Ctrl+T)
   - ⚠️  Settings (placeholder only)

4. **Navigation**
   - ✅ Arrow keys for menu navigation
   - ✅ Tab switching with left/right
   - ✅ ESC to back out of drill-down
   - ✅ Compare mode with suggestions

---

## Feature Completeness Plan

### Phase 1: Settings System (HIGH PRIORITY)

#### Settings Menu Structure
```
Settings
├── Display Settings
│   ├── Theme: [Dark | Light]
│   ├── Show line numbers: [Yes | No]
│   ├── Results per page: [10 | 20 | 50 | 100]
│   └── Source file display: [Always | Multi-config only | Never]
│
├── Search Settings
│   ├── Search mode: [Fuzzy | Prefix | Exact]
│   ├── Case sensitive: [Yes | No]
│   └── Max results: [20 | 50 | 100 | 500]
│
├── Config Settings
│   ├── Current config: [display path]
│   ├── Reload config: [action]
│   └── Switch vendor: [ASA | FortiGate]
│
└── Advanced
    ├── Enable logging: [Yes | No]
    ├── Log level: [INFO | DEBUG | WARNING]
    └── Cache settings: [view/clear]
```

#### Implementation Plan
1. Create `tui/screens/settings_screen.py` with navigable option list
2. Add `tui/state.py` for persistent settings (JSON file in ~/.config/acl-inspector/)
3. Implement setting categories with sub-screens
4. Add Apply/Cancel/Reset to Defaults buttons

---

### Phase 2: Tab Feature Completeness

#### Details Tab
**Current**: Shows basic object info (name, type, source, summary)
**Enhancements Needed**:
- [ ] Show all IP addresses (not just first 3)
- [ ] Show NAT rules affecting this object (if any)
- [ ] Show interface bindings (if applicable)
- [ ] Show object metadata (created from which config section)
- [ ] Add "Copy to clipboard" action for IPs
- [ ] Show object dependencies (what other objects reference this)

#### Inspect Tab
**Current**: Shows ACL rules where object appears in src/dst
**Enhancements Needed**:
- [ ] Filter by direction (inbound/outbound)
- [ ] Filter by interface
- [ ] Show only permit / only deny rules
- [ ] Export results to CSV/JSON
- [ ] Show rule hit counts (if available)
- [ ] Group by ACL name
- [ ] Add protocol/port quick filters

#### Compare Tab
**Current**: Basic comparison with typed input
**Enhancements Needed**:
- [ ] Show diff in table format (old | new | status)
- [ ] Highlight differences visually
- [ ] Show "same" rules collapsed/expanded toggle
- [ ] Add "swap" button to reverse comparison
- [ ] Export diff to file
- [ ] Compare groups (not just objects)
- [ ] Compare ACLs (not just objects)

#### Used in ACLs Tab
**Current**: Shows where object is referenced in ACLs
**Enhancements Needed**:
- [ ] Show object-groups that contain this object
- [ ] Show NAT rules using this object
- [ ] Show static routes using this object (future)
- [ ] Tree view: Object → Groups → ACLs → Interfaces
- [ ] Count of total references
- [ ] Click-through to view the ACL rule details

---

### Phase 3: New Tabs (Future)

#### 5. Path Check Tab
**Purpose**: Simulate packet flow through firewall
**Features**:
- [ ] Input: src IP, dst IP, protocol, port
- [ ] Show: NAT translation, ACL verdict (permit/deny)
- [ ] Display hop-by-hop trace
- [ ] Highlight matching rules
- [ ] Support multi-interface routing

#### 6. Duplicates Tab
**Purpose**: Find duplicate/overlapping objects
**Features**:
- [ ] List objects with same IP/network
- [ ] Show overlapping subnets
- [ ] Suggest consolidation opportunities
- [ ] Highlight naming inconsistencies

#### 7. Graph Tab (Advanced)
**Purpose**: Visual object relationships
**Features**:
- [ ] ASCII art dependency graph
- [ ] Object → Group → ACL → Interface
- [ ] Highlight critical paths
- [ ] Export graph to DOT format

---

### Phase 4: Global Actions

#### Quick Actions Bar (below tabs)
Add a context-aware action bar:
```
[Export] [Filter] [Refresh] [More...]
```

**Export Options**:
- Export current view to JSON
- Export to CSV
- Export to Markdown report
- Copy to clipboard

**Filter Options**:
- By protocol (TCP, UDP, ICMP, any)
- By port range
- By IP range
- By ACL name pattern

#### Batch Operations
- [ ] Compare multiple objects side-by-side
- [ ] Search across multiple configs simultaneously
- [ ] Bulk export selected objects

---

### Phase 5: Advanced Features

#### History & Favorites
- [ ] Recent searches (up/down in search field)
- [ ] Bookmark frequently accessed objects
- [ ] Quick switch between bookmarked configs

#### Config Diff Mode
- [ ] Load two configs and compare all objects
- [ ] Show objects only in config A
- [ ] Show objects only in config B
- [ ] Show objects with different definitions

#### Search Enhancements
- [ ] Regex search support
- [ ] Search by IP (find all objects containing 10.1.1.1)
- [ ] Search by protocol/port
- [ ] Search filters (type:object, source:fw1.conf)
- [ ] Saved search queries

#### CLI Integration
- [ ] Launch TUI from CLI with pre-filled search
- [ ] Export TUI results to stdout (for piping)
- [ ] Batch mode: run queries non-interactively

---

## Settings Screen Implementation Priority

### Immediate (Week 1)
1. Basic settings screen with categories
2. Theme toggle (move from global to settings)
3. Display settings (results per page, line numbers)
4. Save/load from ~/.config/acl-inspector/tui-settings.json

### Short-term (Week 2-3)
1. Search settings (mode, case sensitivity, max results)
2. Config reload/switch functionality
3. Logging settings

### Medium-term (Month 1)
1. Advanced settings (cache management)
2. Keyboard shortcut customization
3. Export format preferences

---

## Tab Priority Matrix

| Tab | Current State | Priority | Complexity | Impact |
|-----|--------------|----------|------------|--------|
| Details | Basic | Medium | Low | Medium |
| Inspect | Complete | Low | - | - |
| Compare | Basic | High | Medium | High |
| Used in ACLs | Complete | Low | - | - |
| Path Check | Missing | Medium | High | High |
| Duplicates | Missing | Low | Medium | Medium |
| Graph | Missing | Low | Very High | Low |

---

## Next Steps (Ordered)

1. **Settings Screen** - Build basic settings UI with categories
2. **Settings Persistence** - JSON config file with load/save
3. **Compare Tab Enhancements** - Diff view, visual highlights
4. **Details Tab Enhancements** - Full IP list, dependencies
5. **Export Functionality** - Add to all tabs
6. **Path Check Tab** - New tab for packet simulation
7. **Search Enhancements** - Regex, IP search, filters
8. **History & Favorites** - Recent searches, bookmarks

---

## Technical Debt to Address

1. **Error Handling**: Add graceful error messages for malformed configs
2. **Performance**: Optimize search for 1000+ object configs
3. **Testing**: Add integration tests for tab workflows
4. **Documentation**: User guide for TUI navigation
5. **Accessibility**: Ensure screen reader compatibility (if possible)

---

## Open Questions

1. Should settings be per-config or global?
2. How to handle FortiGate VDOM selection in TUI?
3. Should we support multiple configs loaded simultaneously?
4. Export format preferences - per-export or global setting?
5. Should Path Check be a tab or a modal dialog?

---

## Notes

- Focus on keyboard-driven UX (minimize mouse dependence)
- Keep layout clean and information dense
- Prioritize features that complement web UI (not duplicate)
- TUI should excel at quick lookups and comparisons
- Settings should be minimal but powerful
