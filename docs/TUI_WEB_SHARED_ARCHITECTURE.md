# TUI/Web Shared Architecture Plan

## Objective
Maintain feature parity between TUI and Web UI by extracting shared business logic into reusable modules.

## Current State

### Web UI Tabs (V1)
Located in `webui/handlers/api.py` and `webui/templates/`:
- **Inspect/Compare** (`tab_rules`): Inspect single object or compare two objects
- **Find Host** (`tab_find`): Find which configs contain a host/object
- **Packet Check** (`tab_packet`): Simulate packet flow through NAT+ACL (Beta)
- **Packet Probe** (`tab_packet_probe`): Enhanced packet flow analysis (Beta)
- **Config Viewer** (`tab_config`): View raw config with syntax highlighting
- **Preferences** (`tab_prefs`): Theme/UI settings
- **About** (`tab_about`): Version and credits

### TUI Tabs (Current)
Located in `tui/widgets/action_tabs.py`:
- **Details**: Object information (IMPLEMENTED)
- **Inspect**: ACL rules affecting object (PLACEHOLDER)
- **Compare**: Compare with another object (PLACEHOLDER)
- **Used in ACLs**: Show ACL references (PLACEHOLDER)

### Backend Logic
Located in:
- `parsers/cisco/asa/inspect.py`: Object resolution and ACL inspection
- `parsers/cisco/asa/parser.py`: ASAConfig class with network_objects, ACLs
- `cli/access-list-inspector.py`: CLI for inspect/compare/find-host

## Shared Library Architecture

### Phase 1: Extract Core Analysis Logic

Create `analysis_core/` module with vendor-agnostic analysis functions:

```
analysis_core/
├── __init__.py
├── inspect.py          # Inspect object in ACLs
├── compare.py          # Compare two objects
├── find_host.py        # Find host across configs
├── acl_usage.py        # Find where object is used
├── packet_flow.py      # Packet path simulation
└── formatters.py       # Output formatting (text/JSON/rich)
```

#### `analysis_core/inspect.py`
```python
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class InspectResult:
    """Results from inspecting an object."""
    object_name: str
    resolved_addresses: List[str]
    matching_rules: List[Dict[str, Any]]
    duplicates: List[str]  # Other objects with same IPs
    acl_bindings: Dict[str, str]  # ACL -> interface

def inspect_object(
    config,  # ASAConfig or FTGConfig
    target: str,
    protocol: Optional[str] = None,
    dport: Optional[int] = None,
    include_any: bool = False
) -> InspectResult:
    """
    Inspect an object across all ACLs.

    Vendor-agnostic function that works with any parsed config.
    """
    # Extract from parsers/cisco/asa/inspect.py logic
    pass
```

#### `analysis_core/compare.py`
```python
@dataclass
class CompareResult:
    """Results from comparing two objects."""
    old_name: str
    new_name: str
    old_only_rules: List[Dict[str, Any]]
    new_only_rules: List[Dict[str, Any]]
    common_rules: List[Dict[str, Any]]

def compare_objects(
    config,
    old_target: str,
    new_target: str,
    protocol: Optional[str] = None,
    dport: Optional[int] = None
) -> CompareResult:
    """Compare two objects to see rule differences."""
    pass
```

#### `analysis_core/acl_usage.py`
```python
@dataclass
class UsageResult:
    """Where an object is referenced."""
    object_name: str
    direct_references: List[Dict[str, Any]]  # ACL name, line, rule
    group_memberships: List[str]  # Object groups containing this
    acl_bindings: Dict[str, str]  # Which ACLs reference it

def find_object_usage(config, object_name: str) -> UsageResult:
    """Find all places where an object is used."""
    pass
```

#### `analysis_core/formatters.py`
```python
from rich.table import Table
from rich.text import Text

def format_inspect_rich(result: InspectResult) -> Table:
    """Format InspectResult as Rich Table for TUI."""
    pass

def format_inspect_html(result: InspectResult) -> str:
    """Format InspectResult as HTML for Web UI."""
    pass

def format_inspect_json(result: InspectResult) -> dict:
    """Format InspectResult as JSON for API."""
    pass
```

### Phase 2: Update TUI to Use Shared Logic

Modify `tui/app.py` and `tui/widgets/detail_view.py`:

```python
# In tui/app.py
from analysis_core.inspect import inspect_object
from analysis_core.compare import compare_objects
from analysis_core.acl_usage import find_object_usage
from analysis_core.formatters import format_inspect_rich

def on_action_tabs_tab_selected(self, message):
    if message.tab_id == "inspect":
        result = inspect_object(
            self.parsed_config,
            self.selected_object['name']
        )
        rich_table = format_inspect_rich(result)
        detail_view.show_content(rich_table)

    elif message.tab_id == "used_in":
        result = find_object_usage(
            self.parsed_config,
            self.selected_object['name']
        )
        # ... format and display
```

### Phase 3: Update Web UI to Use Shared Logic

Modify `webui/handlers/api.py`:

```python
# In webui/handlers/api.py
from analysis_core.inspect import inspect_object
from analysis_core.formatters import format_inspect_html, format_inspect_json

@app.route('/api/inspect', methods=['POST'])
def api_inspect():
    config = get_parsed_config(vendor, config_file)
    result = inspect_object(
        config,
        target=request.form['target'],
        protocol=request.form.get('proto'),
        dport=request.form.get('dport')
    )

    if request.headers.get('Accept') == 'application/json':
        return jsonify(format_inspect_json(result))
    else:
        return format_inspect_html(result)
```

## Feature Parity Tracking

### Documentation Strategy

1. **FEATURE_PARITY.md** (new file)
   - Matrix showing TUI vs Web feature status
   - Checklist for each feature
   - Migration status

2. **Shared Function Registry**
   - `analysis_core/__init__.py` exports all public functions
   - Both TUI and Web import from same place
   - Ensures both UIs call same backend logic

3. **Integration Tests**
   - Test that TUI and Web produce same results for same input
   - Located in `tests/test_ui_parity.py`

### Example FEATURE_PARITY.md Structure

```markdown
# Feature Parity Matrix

| Feature | Web UI | TUI | Shared Backend | Notes |
|---------|--------|-----|----------------|-------|
| Inspect Object | ✅ | ✅ | ✅ analysis_core.inspect | - |
| Compare Objects | ✅ | 🚧 | ✅ analysis_core.compare | TUI in progress |
| Find Host | ✅ | ❌ | ❌ | Needs extraction |
| Packet Check | ✅ Beta | ❌ | ❌ | ASA-only, complex |
| ACL Usage | ❌ | 🚧 | 🚧 analysis_core.acl_usage | New feature |
| Config Viewer | ✅ | ❌ | N/A | TUI shows in detail view |

Legend:
- ✅ Implemented
- 🚧 In Progress
- ❌ Not Started
```

### CI/CD Checks

Add to GitHub Actions:

```yaml
# .github/workflows/feature-parity-check.yml
name: Feature Parity Check

on: [pull_request]

jobs:
  check-parity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Check for new analysis functions
        run: |
          # Ensure any new function in analysis_core/ is used by both UIs
          python3 scripts/check_feature_parity.py
```

### Migration Plan

#### Milestone 1: Extract Inspect Logic
- [x] Create `analysis_core/` module
- [x] Extract `inspect_object()` from ASA inspect.py
- [x] Create formatters for TUI/Web/JSON
- [x] Update TUI Inspect tab to use shared function
- [x] Update Web /api/inspect to use shared function
- [x] Add integration test

#### Milestone 2: Extract Compare Logic
- [ ] Extract `compare_objects()`
- [ ] Update TUI Compare tab
- [ ] Update Web compare endpoint
- [ ] Add integration test

#### Milestone 3: Extract ACL Usage
- [ ] Implement `find_object_usage()`
- [ ] Add TUI "Used in ACLs" tab
- [ ] Add Web API endpoint
- [ ] Add integration test

#### Milestone 4: Find Host
- [ ] Extract find_host logic from CLI
- [ ] Add TUI tab (or global search mode)
- [ ] Ensure Web UI has same capability

#### Milestone 5: Packet Flow (Advanced)
- [ ] Extract packet_flow from ASA path.py
- [ ] Add TUI tab (Beta)
- [ ] Ensure Web UI parity

## Benefits of Shared Architecture

1. **Single Source of Truth**: One implementation, no drift
2. **Easier Testing**: Test business logic once, use everywhere
3. **Faster Development**: Add feature to analysis_core, auto-available to both UIs
4. **Consistency**: Same results regardless of UI choice
5. **Vendor Abstraction**: analysis_core works with ASAConfig or FTGConfig

## Next Steps

1. Create `analysis_core/` directory structure
2. Extract `inspect_object()` from `parsers/cisco/asa/inspect.py`
3. Create formatters for Rich (TUI) and HTML (Web)
4. Update TUI Inspect tab to use shared function
5. Test and validate output matches current behavior
6. Create FEATURE_PARITY.md tracking document
7. Repeat for Compare, ACL Usage, etc.

## Open Questions

1. **Vendor differences**: How to handle ASA vs FortiGate specifics?
   - Answer: Use duck typing - functions check hasattr() for vendor features

2. **Output formatting**: TUI uses Rich, Web uses HTML - too different?
   - Answer: Separate formatters in analysis_core.formatters

3. **Performance**: Does adding abstraction layer slow things down?
   - Answer: Minimal - business logic is the bottleneck, not function calls

4. **Backwards compatibility**: Can we keep old CLI working?
   - Answer: Yes - CLI can import from analysis_core too
