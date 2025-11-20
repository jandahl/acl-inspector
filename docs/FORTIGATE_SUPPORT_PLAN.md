# FortiGate Support Plan

Status snapshot (Nov 2025) combining `AGENTS.md`, `HANDOFF_SUMMARY.md`, and the fortigate-expert brief. Focus is on closing the feature gap between the current rudimentary parser in `parsers/fortigate/config.py` and the roadmap item “FortiGate next” (`AGENTS.md:61-76`).

## Coverage Matrix

| Area | Current state | Notes / gaps |
| --- | --- | --- |
| Config scoping / VDOMs | Partial | `_select_vdom_lines` picks the first VDOM but ignores named selection, per-policy `set vdom`, and system/global blocks outside the VDOM. Need full stack-based parsing per the fortigate-expert guidance (`.claude/agents/fortigate-expert.md:124-158`). |
| Interfaces & zones | Interfaces + zone bindings | `config system interface` + `config system zone` parsed; interface→zone mapping now feeds into ACL bindings (`srczone`/`dstzone`). Need to surface zones in IR import and expose them in CLI/UI filters. |
| Address objects/groups | Basic IPv4 | Supports `set subnet` within `firewall address` and flat `addrgrp` membership. Missing IPv6, dynamic/dns objects, tags, comments, fabric connectors. |
| Services / service groups | Basic TCP/UDP ranges | Handles `tcp-portrange` / `udp-portrange` but no `protocol-number`, ICMP, or application signatures; no `set comment` or helper flags. |
| Policies | Simplified | Captures `action`, `srcaddr`, `dstaddr`, `service`. Ignores `srcintf`, `dstintf`, schedules, logging, NAT flags, UTM/security profiles, status, comments, uuid, internet-service references. |
| NAT (VIP, IP pool, central SNAT) | Round-trip ready | VIP/VIPgrp, IP pools, per-policy `set nat/ippool`, and `central-snat-map` parsed and exported as IR NAT entries; IR import now regenerates `firewall vip` and `central-snat-map` blocks with policy references. Next: thread these into path-check simulations + UI displays. |
| Path check (CLI/UI) | CLI + Web UI + TUI | CLI path check supports FortiGate alongside ASA; web UI and TUI now call the shared Forti simulator (VDOM-aware) for packet probes/tab results. Need to surface Forti warnings/contexts in richer UI cards. |
| Web UI Inspect/Compare/Find | Parity with ASA | Inspect/Compare/Find tabs now accept Forti configs (with optional `vdom`), render Forti-specific summaries, and send results through packet-check jump actions. Future: richer Forti object membership visuals. |
| Routing | Static, OSPF, BGP (basic) | Captures top-level parameters but omits VDOM context, interface bindings inside OSPF areas, redistribution metrics, and most BGP neighbor knobs. |
| IR export/import | Interfaces + NAT emitting (round-trip aware) | IR export includes Forti interfaces plus VIP/policy/central-SNAT metadata; IR import now rehydrates `set srcintf/dstintf`, schedules/names, per-policy SNAT flags, and emits `config firewall vip` entries with references for DNAT policies. Central SNAT still TODO. |
| Tests / fixtures | Advanced fixture + parser tests | Added `tests/fixtures/configs/fortigate/advanced_policy_nat.conf` and `tests/test_fortigate_parser.py` to lock in interfaces, VIP/IP-pool parsing, ACL bindings, and IR NAT emission. Need more fixtures covering multi-VDOM + zone membership. |

## Proposed Next Steps

1. **Fixture expansion**: create representative FortiOS 7.4/7.6 configs that include interfaces, zones, VIPs, IP pools, policy NAT settings, and static routes (see `tests/fixtures/configs/fortigate/advanced_policy_nat.conf`). Use them as golden inputs for new parser + IR tests.
2. **Parser refactor**: replace the current ad-hoc scanners with a stack-based Forti parser per `.claude/agents/fortigate-expert.md`, keeping VDOM context and supporting nested `config`/`edit` sections without relying on indentation.
3. **IR alignment**: emit `Device`, `Interface`, `Object`, `Group`, `ServiceGroup`, `ACL`, `NAT`, and `Route` instances so CLI/TUI/web UI all consume the same Forti data. Coordinate with `parsers/model.py` if new fields are required.
4. **NAT + interface semantics**: model policy `set srcintf/dstintf`, `set nat`, `set ippool enable`, VIP references, and `central-snat-map` so packet-path simulations (web UI “Path check”, TUI path tools) work for Forti devices.
5. **Testing & docs**: add unit tests under `tests/test_fortigate_*` covering each feature slice, and document Forti parity plus limitations in README + AGENTS once features land.

This document will track progress as we implement each slice; update the matrix rows when coverage improves.
