# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Parity tests: DeviceQuery (IR spine) matches the ASA parser's resolution.

These prove the IR round-trip is loss-free for the operations inspect/compare
rely on, so consumers can read from the IR via DeviceQuery instead of parser
internals.
"""

import ipaddress
import unittest

from parsers.cisco.asa.parser import ASAConfig
from parsers.cisco.asa import ir_export
from parsers.cisco.asa.inspect import evaluate_acl
from parsers.query import DeviceQuery
from tests.fixtures.cisco_asa_example import ASA_EXAMPLE

CFG = """\
object network SRC_HOST
 host 10.0.0.10
object network DST_HOST
 host 192.0.2.10
object network WEB2
 host 192.0.2.10
object-group network SRC_GROUP
 network-object object SRC_HOST
 network-object host 10.0.0.11
object-group network NESTED
 group-object SRC_GROUP
object-group service WEBPORTS tcp
 port-object eq 443
 port-object range 8080 8090
access-list acl1 extended permit tcp object-group SRC_GROUP object DST_HOST eq 443
access-list acl1 extended permit udp object SRC_HOST object DST_HOST eq 53
access-list acl1 extended permit tcp any object DST_HOST object-group WEBPORTS
access-group acl1 in interface outside
"""


class DeviceQueryParityTest(unittest.TestCase):
    def setUp(self):
        self.cfg = ASAConfig(CFG)
        self.device = ir_export.to_ir(self.cfg, device_name="t")
        self.q = DeviceQuery(self.device)

    def _norm(self, nets):
        return sorted(str(n) for n in nets)

    def test_resolve_object(self):
        self.assertEqual(self._norm(self.q.resolve("SRC_HOST")),
                         self._norm(self.cfg.resolve_network("SRC_HOST")))

    def test_resolve_group(self):
        self.assertEqual(self._norm(self.q.resolve("SRC_GROUP")),
                         self._norm(self.cfg.resolve_network("SRC_GROUP")))

    def test_resolve_nested_group(self):
        self.assertEqual(self._norm(self.q.resolve("NESTED")),
                         self._norm(self.cfg.resolve_network("NESTED")))

    def test_resolve_raw_ip(self):
        self.assertEqual(self._norm(self.q.resolve("10.0.0.10")),
                         self._norm(self.cfg.resolve_network("10.0.0.10")))

    def test_resolve_any(self):
        self.assertEqual(self._norm(self.q.resolve("any")),
                         self._norm(self.cfg.resolve_network("any")))

    def test_flat_rules_match_flatten_acl(self):
        parser_entries = self.cfg.flatten_acl()
        ir_entries = self.q.flat_rules()
        self.assertEqual(len(ir_entries), len(parser_entries))
        for p, i in zip(parser_entries, ir_entries):
            self.assertEqual(p["action"], i["action"])
            self.assertEqual(p["proto"], i["proto"])
            self.assertEqual(p["raw"], i["raw"])
            self.assertEqual(p["line"], i["line"])
            self.assertEqual(self._norm(p["src"]), self._norm(i["src"]))
            self.assertEqual(self._norm(p["dst"]), self._norm(i["dst"]))
            self.assertEqual(p["svc"]["dst_ports"], i["svc"]["dst_ports"])
            self.assertEqual(set(p["svc"]["dst_service_groups"]),
                             set(i["svc"]["dst_service_groups"]))

    def _rules_affecting_parity(self, target, svc_filter=None, ignore_any=True):
        target_nets = self.cfg.resolve_network(target)
        parser_hits = evaluate_acl(
            self.cfg.flatten_acl(), target_nets, self.cfg,
            service_filter=svc_filter, ignore_any=ignore_any,
        )
        ir_hits = self.q.rules_affecting(
            self.q.resolve(target), service_filter=svc_filter, ignore_any=ignore_any,
        )
        self.assertEqual(sorted(h["raw"] for h in parser_hits),
                         sorted(h["raw"] for h in ir_hits))

    def test_rules_affecting_object(self):
        self._rules_affecting_parity("DST_HOST")

    def test_rules_affecting_include_any(self):
        self._rules_affecting_parity("DST_HOST", ignore_any=False)

    def test_rules_affecting_service_filter_match(self):
        self._rules_affecting_parity("DST_HOST", svc_filter={"proto": "tcp", "dports": {443}}, ignore_any=False)

    def test_rules_affecting_service_filter_via_group(self):
        self._rules_affecting_parity("DST_HOST", svc_filter={"proto": "tcp", "dports": {8085}}, ignore_any=False)

    def test_rules_affecting_service_filter_no_match(self):
        self._rules_affecting_parity("DST_HOST", svc_filter={"proto": "tcp", "dports": {9999}}, ignore_any=False)

    def test_group_membership_matches(self):
        self.assertEqual(self.q.group_membership(), self.cfg.group_membership())

    def test_alias_objects_matches(self):
        target_nets = self.cfg.resolve_network("DST_HOST")
        parser_alias = self.cfg.find_alias_objects("DST_HOST", target_nets)
        ir_alias = self.q.alias_objects("DST_HOST", self.q.resolve("DST_HOST"))
        self.assertEqual({str(k): sorted(v) for k, v in parser_alias.items()},
                         {str(k): sorted(v) for k, v in ir_alias.items()})


class DeviceQueryFixtureParityTest(unittest.TestCase):
    """Parity on the shared ASA_EXAMPLE fixture."""

    def setUp(self):
        self.cfg = ASAConfig(ASA_EXAMPLE)
        self.q = DeviceQuery(ir_export.to_ir(self.cfg, device_name="ex"))

    def test_inspect_10_0_0_10(self):
        target_nets = self.cfg.resolve_network("10.0.0.10")
        parser_hits = evaluate_acl(self.cfg.flatten_acl(), target_nets, self.cfg, ignore_any=True)
        ir_hits = self.q.rules_affecting(self.q.resolve("10.0.0.10"), ignore_any=True)
        self.assertEqual(sorted(h["raw"] for h in parser_hits),
                         sorted(h["raw"] for h in ir_hits))


if __name__ == "__main__":
    unittest.main()
