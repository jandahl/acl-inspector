# Code Review Tasks

This document breaks down the code review tasks requested in Issue #14.
Each section represents a subtask that should be assigned to @copilot for review.

---

## 1. Documentation Review

**Scope:** Review all documentation for accuracy, completeness, and consistency.

**Files to review:**
- `README.md` - Main project documentation
- `CLAUDE.md` - AI assistant guidance
- `AGENTS.md` - Development guidelines
- `docs/` directory:
  - `ABOUT.md` - Project overview
  - `API_OVERVIEW.md` - API documentation
  - `API_PATH_CHECK.md` - Path check API specifics
  - `TUI_QUICKSTART_GUIDE.md` - TUI user guide
  - `TUI_FEATURE_PLAN.md` - TUI roadmap
  - `TUI_IMPLEMENTATION_SUMMARY.md` - TUI technical details
  - `HIGH-LEVEL-DESIGN.md` - Architecture overview
  - `ROOT_STRUCTURE.md` - Repository structure
  - `IR_VERSIONING.md` - IR schema documentation
  - `FORTIGATE_SUPPORT_PLAN.md` - FortiGate parser plans
  - Session summary documents

**Review criteria:**
- [ ] Documentation accurately reflects current code behavior
- [ ] Code examples are correct and runnable
- [ ] Installation/setup instructions are complete
- [ ] API documentation matches actual endpoints
- [ ] Architecture diagrams are up to date
- [ ] No broken links or references
- [ ] Consistent formatting and style

---

## 2. Backend Code Review

**Scope:** Review core parsing and analysis logic.

**Files to review:**
- `parsers/` directory:
  - `parsers/base.py` - Base dataclasses (`FlatRule`, `Endpoint`, `ServiceSpec`)
  - `parsers/model.py` - IR dataclasses (`Device`, `Interface`, `Object`, `ACL`, `NAT`)
  - `parsers/loader.py` - Config loading utilities
  - `parsers/cisco/asa/` - ASA parser modules:
    - `parser.py` - Main parsing logic
    - `services.py` - Service object-group handling
    - `nat.py` - NAT rule parsing
    - `path.py` - Packet path evaluation
    - `inspect.py` - Object resolution
  - `parsers/fortigate/fortigate.py` - FortiGate parser
- `analysis/` directory:
  - `analysis/optimizer.py` - ACL optimization logic
- `analysis_core/` directory:
  - `analysis_core/index.py` - Search index management
  - `analysis_core/compare.py` - Comparison logic
  - `analysis_core/inspect.py` - Inspection logic
  - `analysis_core/adapters/` - Vendor-specific adapters

**Review criteria:**
- [ ] Code follows Python best practices
- [ ] Error handling is appropriate
- [ ] No security vulnerabilities
- [ ] Performance considerations addressed
- [ ] Type hints used consistently
- [ ] Docstrings are comprehensive for parser internals
- [ ] Unit test coverage is adequate
- [ ] No code duplication
- [ ] IR schema is stable and versioned

---

## 3. API Review

**Scope:** Review web API endpoints for correctness, security, and consistency.

**Files to review:**
- `webui/router.py` - Request routing
- `webui/handlers/` directory:
  - `api.py` - JSON API endpoints
  - `pages.py` - HTML page handlers
  - `static.py` - Static asset serving
  - `actions.py` - Form submission handlers
- `webui/state.py` - Application state management
- `webui/settings.py` - Settings management

**API endpoints to review:**
- `/api/objects` - Object search/suggestions
- `/api/meta` - Config metadata
- `/api/aliases` - Alias lookup
- `/api/inspect` - Inspection results
- `/api/compare` - Comparison results
- `/api/path` - Path check evaluation
- `/api/index/status` - Index status
- `/api/probe` (beta) - Packet probe

**Review criteria:**
- [ ] Input validation is thorough
- [ ] Output format is consistent (JSON structure)
- [ ] Error responses are informative
- [ ] No sensitive data exposure
- [ ] Rate limiting considerations
- [ ] CORS handling if needed
- [ ] Authentication/authorization (if applicable)
- [ ] Query parameter handling is robust
- [ ] Response codes are appropriate

---

## 4. CLI Code Review

**Scope:** Review command-line interface implementation.

**Files to review:**
- `aclinspector.py` - Main entry point dispatcher
- `cli/access-list-inspector.py` - Core CLI implementation
- `cli/acl-ir-translate.py` - IR translation CLI
- `cli/acl-optimize.py` - ACL optimization CLI

**Review criteria:**
- [ ] Argument parsing is intuitive
- [ ] Help text is comprehensive
- [ ] Error messages are user-friendly
- [ ] Exit codes are meaningful
- [ ] stdin support works correctly (`--config -`)
- [ ] Output formats (text/JSON/XML) are consistent
- [ ] Color output respects TTY detection
- [ ] `--no-color` flag works correctly
- [ ] Self-test mode (`--self-test`) is comprehensive
- [ ] Examples (`--examples`) are accurate

---

## 5. TUI Code Review

**Scope:** Review Terminal User Interface implementation.

**Files to review:**
- `tui/__init__.py` - Package initialization
- `tui/__main__.py` - Entry point
- `tui/app.py` - Main Textual application
- `tui/state.py` - Settings persistence
- `tui/widgets/` directory:
  - `search_bar.py` - Search input widget
  - `suggestion_list.py` - Results list
  - `detail_view.py` - Tab content display
  - `action_tabs.py` - Tab navigation
  - `filter_bar.py` - Protocol/port filters
- `tui/screens/` directory:
  - `settings_screen.py` - Settings dialog
  - `export_screen.py` - Export dialog
- `tui/utils/export.py` - Export functionality
- `tui/README.md` - TUI documentation
- `tui/ROADMAP.md` - TUI roadmap

**Review criteria:**
- [ ] Keyboard shortcuts are intuitive and consistent
- [ ] UI responds smoothly (< 100ms for search)
- [ ] Settings persistence works correctly
- [ ] Export functionality (JSON/CSV/TXT) works
- [ ] Theme toggle works correctly
- [ ] Multi-config support is functional
- [ ] Filter functionality is correct
- [ ] Error handling for missing dependencies
- [ ] Accessibility considerations

---

## 6. Legacy Front End Code Review

**Scope:** Review legacy code for potential deprecation or migration.

**Files to review:**
- `legacy/ASA_ACL_inspector.py` - Legacy inspector
- `legacy/README.md` - Legacy documentation
- `legacy/test_ASA-ACL-inspector.py` - Legacy tests (do not modify)

**Review criteria:**
- [ ] Identify functionality that should be preserved
- [ ] Document any unique features not in new code
- [ ] Assess migration path to current implementation
- [ ] Note any bugs or issues for reference
- [ ] Determine deprecation timeline

---

## 7. Singularity Code Review

**Scope:** Review Singularity (V2 UI concept) implementation.

**Files to review:**
- `webui/static/singularity.css` - Singularity styles
- `webui/static/singularity.js` - Singularity JavaScript
- `webui/templates/singularity.html` - Singularity HTML template
- `webui/beta/` - Beta/experimental features:
  - `webui/beta/__init__.py`
  - `webui/beta/packet_probe.py`
- `docs/SINGULARITY_SMOOTHING_PLAN.md` - UX improvement plans
- `docs/SINGULARITY_TUI_DESIGN.md` - TUI design spec

**Review criteria:**
- [ ] Search-first UX is implemented correctly
- [ ] Fuzzy matching works as expected
- [ ] Performance targets are met (< 100ms search)
- [ ] Progressive disclosure is intuitive
- [ ] Keyboard navigation works
- [ ] Theme consistency with main UI
- [ ] Cache/preload strategies are effective
- [ ] Error handling is graceful

---

## 8. Singularity Web Front End Architecture Redesign

**Scope:** Architectural review and redesign planning for Singularity web UI.

**Areas to address:**
- Current state assessment
- Target architecture definition
- Migration strategy
- Performance optimization plan
- Component structure review
- State management approach
- Theme system consolidation
- API integration patterns

**Deliverables:**
- [ ] Architecture diagram (current vs proposed)
- [ ] Component hierarchy documentation
- [ ] API contract specification
- [ ] Performance benchmarks
- [ ] Migration roadmap
- [ ] Risk assessment
- [ ] Resource requirements

**Key design considerations from `SINGULARITY_SMOOTHING_PLAN.md`:**
- Preload bundle + critical data
- Cache last query in localStorage
- Progress indicators (skeleton UI)
- Multi-column suggestion list
- Keyboard affordances (Ctrl+K launcher)
- Inline filters under search
- Adaptive density for viewport
- Shared theme tokens (TUI/Web/Singularity)
- Error banners (non-blocking toast)
- Health endpoint (`/singularity/health`)
- Search telemetry (anonymized)

---

## Task Summary Table

| # | Task | Area | Priority | Assignee |
|---|------|------|----------|----------|
| 1 | Documentation review | docs/ | High | @copilot |
| 2 | Backend code review | parsers/, analysis/, analysis_core/ | High | @copilot |
| 3 | API review | webui/handlers/, webui/router.py | High | @copilot |
| 4 | CLI code review | cli/, aclinspector.py | Medium | @copilot |
| 5 | TUI code review | tui/ | Medium | @copilot |
| 6 | Legacy front end code review | legacy/ | Low | @copilot |
| 7 | Singularity code review | webui/static/singularity.*, webui/beta/ | Medium | @copilot |
| 8 | Singularity web front end architecture redesign | webui/ | High | @copilot |

---

## Creating GitHub Issues

To create these as GitHub issues, use the following template for each task:

```markdown
## [Task Name] (e.g., "Documentation Review")

**Scope:** [Brief description from above]

**Files to review:**
[List from above]

**Review criteria:**
[Checklist from above]

**Assignee:** @copilot
**Labels:** `code-review`, `[area]` (e.g., `documentation`, `backend`, `api`, etc.)
**Parent issue:** #14
```

---

*This document was generated to support Issue #14: Full code review*
