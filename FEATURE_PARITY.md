# Feature Parity Tracking: TUI vs Web UI

This document tracks feature parity between the Terminal UI (TUI) and Web UI to ensure consistent functionality across both interfaces.

## Status Legend
- ✅ **Implemented** - Feature is complete and tested
- 🚧 **In Progress** - Currently being developed
- ❌ **Not Started** - Planned but not yet begun
- 🔄 **Needs Migration** - Exists but needs refactoring to shared code
- N/A - Not applicable for this interface

## Core Features Matrix

| Feature | Web UI | TUI | Shared Backend | Priority | Notes |
|---------|--------|-----|----------------|----------|-------|
| **Search** | | | | | |
| Substring search | ✅ | ✅ | ❌ | HIGH | Each UI has own implementation |
| Fuzzy search | 🚧 V2 | ❌ | ❌ | MEDIUM | Planned for both |
| Search operators (type:, ip:) | ❌ | ❌ | ❌ | LOW | Future enhancement |
| **Object Operations** | | | | | |
| View object details | ✅ | ✅ | ❌ | HIGH | Different formats (HTML vs Rich) |
| Inspect object (ACL rules) | ✅ | ❌ | 🔄 | **HIGH** | **NEXT PRIORITY** |
| Compare two objects | ✅ | ❌ | 🔄 | HIGH | Needs shared compare.py |
| Find object usage in ACLs | ❌ | ❌ | ❌ | MEDIUM | New feature for both |
| **Network Analysis** | | | | | |
| Find host across configs | ✅ | ❌ | 🔄 | MEDIUM | CLI has logic, needs extraction |
| Packet flow simulation | ✅ Beta | ❌ | 🔄 | LOW | ASA-only, complex |
| Packet probe | ✅ Beta | ❌ | 🔄 | LOW | Enhanced packet flow |
| **Configuration** | | | | | |
| View raw config | ✅ | N/A | N/A | N/A | TUI shows in detail view |
| Config syntax highlighting | ✅ | N/A | N/A | N/A | Web-specific |
| Select vendor | ✅ | ✅ CLI | N/A | LOW | TUI uses CLI args |
| Select config file | ✅ | ✅ CLI | N/A | LOW | TUI uses CLI args |
| **UI Customization** | | | | | |
| Theme toggle (dark/light) | ✅ | ✅ | N/A | N/A | UI-specific |
| Font selection | ✅ | N/A | N/A | N/A | Web-only |
| Result limit | ✅ | ✅ | N/A | LOW | Both hardcoded to 20 |
| **Export/Output** | | | | | |
| JSON output | ✅ API | ❌ | ❌ | MEDIUM | Needs shared formatters |
| Copy to clipboard | ✅ | N/A | N/A | N/A | Terminal limitation |
| Export results | ❌ | ❌ | ❌ | LOW | Future enhancement |

## Detailed Status

### ✅ Implemented in Both

1. **Basic Search**
   - Web: Real-time substring search with debouncing
   - TUI: Debounced search (250ms) with substring matching
   - Status: Different implementations, similar behavior
   - Action needed: Extract to shared module for consistency

2. **Object Details**
   - Web: HTML table with object info
   - TUI: Rich Table showing name, type, IPs, members
   - Status: Both work but different formats
   - Action needed: Shared data model in analysis_core

3. **Theme Toggle**
   - Web: Singularity V2 has dark/light modes
   - TUI: Ctrl+T switches textual-dark/light
   - Status: UI-specific, no shared code needed

### 🚧 Next Implementation Priority

**1. Inspect Tab - TUI**
- Web has: `/api/inspect` endpoint, shows ACL rules affecting object
- TUI has: Placeholder tab, needs implementation
- Shared backend: Needs `analysis_core/inspect.py` extraction
- **Action**: This is the top priority to implement

**2. Compare Tab - TUI**
- Web has: Compare mode in rules tab
- TUI has: Placeholder tab
- Shared backend: Needs `analysis_core/compare.py`
- **Action**: Second priority after Inspect

**3. ACL Usage - Both**
- Web has: No dedicated feature
- TUI has: Placeholder "Used in ACLs" tab
- Shared backend: New `analysis_core/acl_usage.py`
- **Action**: New feature for both UIs simultaneously

### 🔄 Migration Needed

These features exist but use duplicate logic:

1. **Inspect Logic**
   - Current: `parsers/cisco/asa/inspect.py` + Web handler
   - Target: `analysis_core/inspect.py`
   - Benefits: Single implementation, easier testing

2. **Compare Logic**
   - Current: Embedded in `access-list-inspector.py` CLI
   - Target: `analysis_core/compare.py`
   - Benefits: Reusable by TUI, Web, CLI

3. **Find Host Logic**
   - Current: CLI `--find-host` implementation
   - Target: `analysis_core/find_host.py`
   - Benefits: Could add to both UIs

## Development Workflow

When adding a new feature:

1. ✅ **Plan**: Update this document with feature status
2. ✅ **Shared Logic**: Implement in `analysis_core/` if applicable
3. ✅ **TUI**: Add tab/functionality using shared code
4. ✅ **Web**: Add endpoint/UI using same shared code
5. ✅ **Test**: Add integration test comparing TUI and Web output
6. ✅ **Document**: Update this file and commit

## Integration Test Strategy

Create `tests/test_ui_parity.py`:

```python
def test_inspect_parity():
    """Ensure TUI and Web produce same inspect results."""
    config = ASAConfig(test_config_text)

    # TUI path
    from analysis_core.inspect import inspect_object
    tui_result = inspect_object(config, "test-object")

    # Web path (same function)
    web_result = inspect_object(config, "test-object")

    assert tui_result == web_result
```

## Current Focus

**Phase 1: Inspect Tab Implementation** (In Progress)

1. [x] Create `analysis_core/` directory
2. [ ] Extract `inspect_object()` from ASA inspect.py
3. [ ] Create `analysis_core/formatters.py` with format_inspect_rich()
4. [ ] Update TUI Inspect tab to use shared function
5. [ ] Update Web to use shared function
6. [ ] Add integration test
7. [ ] Update this document

## Questions & Decisions

### Q: Should analysis_core be vendor-agnostic?
**A**: Yes - functions should work with both ASAConfig and FTGConfig via duck typing.

### Q: How to handle output formatting (Rich vs HTML)?
**A**: Separate formatters in `analysis_core/formatters.py`:
- `format_inspect_rich()` for TUI
- `format_inspect_html()` for Web
- `format_inspect_json()` for API

### Q: Does the CLI also use shared code?
**A**: Yes - `access-list-inspector.py` can import from `analysis_core/` too, becoming a thin wrapper.

### Q: How to track when features fall out of sync?
**A**:
1. This document (manual review during PRs)
2. CI/CD check script (automated)
3. Integration tests (proves parity)

## Maintenance

This document should be updated:
- ✅ Before starting new feature work
- ✅ After completing any feature
- ✅ During code review (reviewer checks parity)
- ✅ At each release (verify all features match)

Last updated: 2025-11-09
