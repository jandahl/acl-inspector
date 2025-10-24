ASA ACL Inspector
==================

Overview
--------
ASA_ACL_inspector.py parses Cisco ASA configurations to:
- Resolve network objects and object-groups to concrete addresses/networks
- Flatten ACL entries (source/destination) for impact analysis
- Inspect a single IP/object to list all ACL entries affecting it
- Compare two targets (old/new) to show rules added/removed
- Detect duplicate network-objects mapping to the same IP/network

Why it exists
-------------
Firewall changes often involve swapping an object or moving workloads. This tool answers:
- What ACL rules currently hit a host/object?
- If I replace object A with object B, what changes in rule impact?
- Are there duplicate objects mapping to the same address that might surprise us?

Requirements
------------
- Python 3.9+
- No external packages are required

Quick start
-----------
- Inspect a host/object:
  `./ASA_ACL_inspector.py --config <asa.conf> --inspect <ip|cidr|object>`

- Compare two targets:
  `./ASA_ACL_inspector.py --config <asa.conf> --old <ip|cidr|object> --new <ip|cidr|object>`

Outputs
-------
- Inspection prints:
  - Resolved target addresses
  - Matched ACL lines (raw)
  - Matched ACL entries (flattened src/dst)
  - Other objects mapping to the same address/network (duplicates)

Notes on parsing
----------------
- The tool focuses on IP impact; port/service tokens are currently ignored for matching
- ASA tokens `any`, `any4` and `any6` are supported
- Service object(-group) names at the protocol position are consumed to prevent token spillover

Duplicate object detection
--------------------------
When inspecting a target (IP or object name), the tool looks up other network-objects that resolve to the same exact IP address or network and prints them. This helps find duplicate host objects like:

```
object network HOST_A
 host 10.1.1.1
object network HOST_B
 host 10.1.1.1
```

Testing
-------
- Run unit tests in the `tests` directory:
  `python3 -m unittest discover -s tests`

- A legacy test file (`test_ASA-ACL-inspector.py`) exists; it targets an older version and may not pass. Prefer the tests under `tests/`.

Development
-----------
- Keep changes minimal and focused
- Add or update tests alongside code changes
- Validate with `python3 -m py_compile ASA_ACL_inspector.py`

Future goals
------------
- Web wrapper UI for inspection/compare
- Support FortiGate configs (including VDOMs) and cross-vendor compare
- Port-aware matching and reporting
- Pluggable parser architecture to support additional vendors

