Legacy Artifacts
================

This directory holds compatibility shims and historical assets that remain in
the repository for reference:

- `ASA_ACL_inspector.py` preserves the legacy CLI entry point and exits with a
  deprecation notice.
- `test_ASA-ACL-inspector.py` targets the pre-refactor toolchain and is kept
  untouched for context; it is *not* part of the active test suite.

Nothing under this directory is expected to evolve. New development should
focus on the modern entry points (`access-list-inspector.py`, `access-list-web.py`)
and the tests in `tests/`.
