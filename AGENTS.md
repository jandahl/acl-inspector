Agent Guidelines
================

Scope
-----
This repository contains a Python tool to inspect and compare Cisco ASA ACLs. The scope includes parsing ASA configs, resolving objects, and reporting ACL impacts. Future scope will broaden to other vendors and a web UI.

Coding conventions
------------------
- Python 3.9+ only; standard library preferred
- Keep changes minimal and focused to the task
- Avoid large refactors unless explicitly requested
- Match the project’s direct, concise coding style
- Add tests for new behavior under `tests/`

Parsing rules
-------------
- Parse ASA `object network` and `object-group network`
- Record network-objects as exact IPv4Address or IPv4Network
- For ACL lines, extract protocol/service token and parse exactly two endpoints (src, dst). Ignore remaining tokens (ports) for now
- Recognize ASA tokens `any`, `any4`, `any6`
- Do not attempt port/time-range matching yet (future work)

New features in this iteration
------------------------------
- Duplicate object detection: For a given target, report other network-objects that resolve to the same IP/network
- Robust tokenization for ACL parsing: consume service object(-group) names appearing in protocol position to prevent token bleed into src/dst parsing

Quality and linting
-------------------
- Always run a quick syntax check: `python3 -m py_compile ASA_ACL_inspector.py`
- If Python linters (ruff/flake8) are available locally, run them; otherwise rely on unit tests and compilation
- For shell scripts (if any), run `shellcheck` as appropriate

Tests
-----
- Use the standard library `unittest`
- Place new tests under `tests/` and prefer `python3 -m unittest discover -s tests`
- Do not modify the legacy `test_ASA-ACL-inspector.py`; it targets an older version and may not pass

Future abstractions and goals
-----------------------------
- Web wrapper page with a simple UI for inspect/compare flows
- Vendor abstraction: introduce a pluggable parser layer to support FortiGate (with VDOMs) and others
- Cross-vendor diff: normalize flattened entries to a common model for comparison
- Port-aware matching and richer rule reporting (service/ports)

