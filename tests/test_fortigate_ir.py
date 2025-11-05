import json
import unittest

from parsers.fortigate.config import FTGConfig


FORTI_SAMPLE = """
#config-version=FG100E-7.4.1,build1234
config system interface
    edit "port1"
        set vdom "Alpha"
        set ip 10.0.1.1 255.255.255.0
    next
    edit "port2"
        set vdom "Alpha"
        set ip 10.0.2.1/24
    next
end
config vdom
    edit "Alpha"
        config firewall address
            edit "NET-A"
                set subnet 10.1.1.0 255.255.255.0
            next
            edit "RANGE-B"
                set type iprange
                set start-ip 10.1.2.10
                set end-ip 10.1.2.11
            next
            edit "FQDN-C"
                set type fqdn
                set fqdn "app.example.com"
            next
        end
        config firewall addrgrp
            edit "GRP-MIX"
                set member "NET-A" "RANGE-B"
            next
        end
        config firewall service custom
            edit "TCP1000"
                set tcp-portrange 1000
            next
        end
        config firewall service group
            edit "SVC-GRP"
                set member "TCP1000" "HTTP"
            next
        end
        config firewall policy
            edit 1
                set name "AllowMix"
                set srcintf "port1"
                set dstintf "port2"
                set srcaddr "NET-A"
                set dstaddr "GRP-MIX"
                set action accept
                set schedule "always"
                set service "SVC-GRP"
            next
            edit 2
                set name "DisabledPolicy"
                set srcintf "port1"
                set dstintf "port2"
                set srcaddr "NET-A"
                set dstaddr "NET-A"
                set action accept
                set schedule "always"
                set service "ALL"
                set status disable
            next
        end
    next
end
"""


class TestFortiGateIR(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = FTGConfig(FORTI_SAMPLE, vdom="Alpha")

    def test_version_and_vdom_selection(self):
        self.assertEqual(self.cfg.version, "7.4.1")
        self.assertEqual(self.cfg.active_vdom, "Alpha")
        self.assertIn("port1", self.cfg.interfaces_by_vdom.get("Alpha", {}))

    def test_address_resolution(self):
        range_nets = {str(n) for n in self.cfg.resolve_addr_token("RANGE-B") if not isinstance(n, str)}
        self.assertIn("10.1.2.10/31", range_nets)
        fqdn_tokens = self.cfg.resolve_addr_token("FQDN-C")
        self.assertIn("fqdn:app.example.com", fqdn_tokens)

    def test_flatten_policies_filters_disabled(self):
        entries = self.cfg.flatten_policies()
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["binding"]["srcintf"], ["port1"])
        self.assertEqual(entry["binding"]["dstintf"], ["port2"])
        self.assertEqual(entry["bound_to"], "src:port1 dst:port2")

    def test_to_ir_device_shape(self):
        dev = self.cfg.to_ir(device_name="alpha-fw")
        d = dev.to_dict()
        self.assertEqual(d.get("vendor"), "fortigate")
        self.assertEqual(d.get("os"), "FortiOS")
        self.assertEqual(d.get("version"), "7.4.1")
        self.assertEqual(d.get("name"), "alpha-fw")
        ifaces = {i["name"]: i for i in d.get("interfaces", [])}
        self.assertEqual(ifaces["port1"]["ipv4"], "10.0.1.1/24")
        self.assertEqual(ifaces["port2"]["ipv4"], "10.0.2.1/24")
        objects = {o["name"]: o for o in d.get("objects", [])}
        self.assertIn("NET-A", objects)
        self.assertIn("RANGE-B", objects)
        self.assertIn("FQDN-C", objects)
        self.assertIn("fqdn:app.example.com", objects["FQDN-C"]["literals"])
        groups = {g["name"]: g for g in d.get("groups", [])}
        self.assertIn("GRP-MIX", groups)
        grp_members = groups["GRP-MIX"]["members"]
        kinds = {m["kind"] for m in grp_members}
        self.assertIn("object", kinds)
        svc_groups = {g["name"]: g for g in d.get("service_groups", [])}
        self.assertIn("SVC-GRP", svc_groups)
        self.assertTrue(any(m.get("object") == "TCP1000" for m in svc_groups["SVC-GRP"]["members"]))
        acls = d.get("acls", [])
        self.assertEqual(len(acls), 1)
        entries = acls[0]["entries"]
        self.assertEqual(len(entries), 1)
        svc = entries[0]["svc"]
        self.assertTrue(any(p.get("start") == 1000 for p in svc.get("dst_ports", [])))
        json.dumps(d)


if __name__ == "__main__":
    unittest.main()
