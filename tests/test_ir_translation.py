# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Unit tests for IR translation (export/import) functionality.

Tests the complete translation pipeline:
- ASA → IR → ASA (round-trip)
- FortiGate → IR → FortiGate (round-trip)
- ASA → IR → FortiGate (cross-vendor)
- FortiGate → IR → ASA (cross-vendor)

Round-trip tests ensure that IR conversion preserves essential configuration
semantics and validates the IR schema stability.
"""

import unittest
from pathlib import Path
from parsers.cisco.asa.parser import ASAConfig
from parsers.cisco.asa import ir_export as asa_export
from parsers.cisco.asa import ir_import as asa_import
from parsers.fortigate.config import FTGConfig
from parsers.fortigate import ir_export as ftg_export
from parsers.fortigate import ir_import as ftg_import
from parsers import model as ir

FIXTURES = Path(__file__).parent / "fixtures" / "configs" / "fortigate"


class TestASARoundTrip(unittest.TestCase):
    """Test ASA → IR → ASA round-trip conversion."""

    def test_simple_network_objects(self):
        """Test that network objects survive round-trip."""
        config = """
object network HOST1
 host 10.0.0.1
object network NET1
 subnet 192.168.1.0 255.255.255.0
"""
        cfg = ASAConfig(config)
        device = asa_export.to_ir(cfg, device_name="test-asa")

        # Verify IR structure
        self.assertEqual(device.vendor, 'asa')
        self.assertEqual(device.name, 'test-asa')
        self.assertEqual(len(device.objects), 2)

        # Find specific objects
        host1 = next((o for o in device.objects if o.name == 'HOST1'), None)
        self.assertIsNotNone(host1)
        self.assertIn('10.0.0.1', host1.literals)

        net1 = next((o for o in device.objects if o.name == 'NET1'), None)
        self.assertIsNotNone(net1)
        self.assertIn('192.168.1.0/24', net1.literals)

        # Round-trip back to ASA
        output = asa_import.from_ir(device)
        self.assertIn('object network HOST1', output)
        self.assertIn('host 10.0.0.1', output)
        self.assertIn('object network NET1', output)
        # ASA uses netmask notation, not CIDR
        self.assertIn('subnet 192.168.1.0 255.255.255.0', output)

    def test_object_groups(self):
        """Test that object-groups survive round-trip."""
        config = """
object network OBJ1
 host 10.0.0.1
object-group network GRP1
 network-object object OBJ1
 network-object 192.168.0.0 255.255.255.0
 group-object GRP2
object-group network GRP2
 network-object host 10.0.0.2
"""
        cfg = ASAConfig(config)
        device = asa_export.to_ir(cfg)

        # Verify groups
        self.assertEqual(len(device.groups), 2)

        grp1 = next((g for g in device.groups if g.name == 'GRP1'), None)
        self.assertIsNotNone(grp1)
        self.assertEqual(len(grp1.members), 3)

        # Check member types
        member_kinds = [m.kind for m in grp1.members]
        self.assertIn('object', member_kinds)
        self.assertIn('literal', member_kinds)
        self.assertIn('group', member_kinds)

        # Round-trip
        output = asa_import.from_ir(device)
        self.assertIn('object-group network GRP1', output)
        self.assertIn('network-object object OBJ1', output)
        self.assertIn('group-object GRP2', output)

    def test_simple_acl(self):
        """Test that ACLs survive round-trip."""
        config = """
object network WEB
 host 10.0.0.10
access-list OUTSIDE extended permit tcp any object WEB eq 443
access-list OUTSIDE extended deny ip any any
"""
        cfg = ASAConfig(config)
        device = asa_export.to_ir(cfg)

        # Verify ACLs
        self.assertGreater(len(device.acls), 0)

        outside_acl = next((a for a in device.acls if a.name == 'OUTSIDE'), None)
        self.assertIsNotNone(outside_acl)
        self.assertGreater(len(outside_acl.entries), 0)

        # Round-trip
        output = asa_import.from_ir(device)
        self.assertIn('access-list OUTSIDE', output)

    def test_service_groups(self):
        """Test that service object-groups survive round-trip."""
        config = """
object-group service WEB tcp
 port-object eq 80
 port-object eq 443
object-group service SSH
 service-object tcp eq 22
"""
        cfg = ASAConfig(config)
        device = asa_export.to_ir(cfg)

        # Verify service groups were parsed
        self.assertGreater(len(device.service_groups), 0)

        # Find WEB service group
        web_sg = next((sg for sg in device.service_groups if sg.name == 'WEB'), None)
        self.assertIsNotNone(web_sg)
        self.assertEqual(len(web_sg.members), 2)

        # Verify port-object entries
        for member in web_sg.members:
            self.assertIn('proto', member)
            self.assertEqual(member['proto'], 'tcp')
            self.assertIn('op', member)

        # Round-trip
        output = asa_import.from_ir(device)
        self.assertIn('object-group service', output)


class TestFortiGateRoundTrip(unittest.TestCase):
    """Test FortiGate → IR → FortiGate round-trip conversion."""

    def test_simple_addresses(self):
        """Test that firewall addresses survive round-trip."""
        config = """
config firewall address
    edit "HOST1"
        set subnet 10.0.0.1 255.255.255.255
    next
    edit "NET1"
        set subnet 192.168.1.0 255.255.255.0
    next
end
"""
        cfg = FTGConfig(config)
        device = ftg_export.to_ir(cfg, device_name="test-ftg")

        # Verify IR structure
        self.assertEqual(device.vendor, 'fortigate')
        self.assertEqual(device.name, 'test-ftg')
        self.assertEqual(len(device.objects), 2)

        # Round-trip
        output = ftg_import.from_ir(device)
        self.assertIn('config firewall address', output)
        self.assertIn('edit "HOST1"', output)
        self.assertIn('set subnet 10.0.0.1 255.255.255.255', output)

    def test_address_groups(self):
        """Test that firewall addrgrp survive round-trip."""
        config = """
config firewall address
    edit "HOST1"
        set subnet 10.0.0.1 255.255.255.255
    next
end
config firewall addrgrp
    edit "GRP1"
        set member "HOST1"
    next
end
"""
        cfg = FTGConfig(config)
        device = ftg_export.to_ir(cfg)

        # Verify groups
        self.assertEqual(len(device.groups), 1)

        # Round-trip
        output = ftg_import.from_ir(device)
        self.assertIn('config firewall addrgrp', output)
        self.assertIn('edit "GRP1"', output)

    def test_service_custom(self):
        """Test that service custom objects survive round-trip."""
        config = """
config firewall service custom
    edit "WEB"
        set tcp-portrange 80 443
    next
end
"""
        cfg = FTGConfig(config)
        device = ftg_export.to_ir(cfg)

        # Verify service groups
        self.assertGreater(len(device.service_groups), 0)

        # Round-trip
        output = ftg_import.from_ir(device)
        self.assertIn('config firewall service custom', output)
        self.assertIn('edit "WEB"', output)

    def test_policies(self):
        """Test that firewall policies survive round-trip."""
        config = """
config firewall address
    edit "SRC"
        set subnet 10.0.0.0 255.255.255.0
    next
    edit "DST"
        set subnet 192.168.1.0 255.255.255.0
    next
end
config firewall policy
    edit 1
        set action accept
        set srcaddr "SRC"
        set dstaddr "DST"
        set service "ALL"
    next
end
"""
        cfg = FTGConfig(config)
        device = ftg_export.to_ir(cfg)

        # Verify policies converted to ACLs
        self.assertEqual(len(device.acls), 1)
        self.assertEqual(device.acls[0].name, 'policy')

        # Round-trip
        output = ftg_import.from_ir(device)
        self.assertIn('config firewall policy', output)

    def test_policy_interfaces_and_vips_roundtrip(self):
        """Ensure interfaces/NAT/VIP metadata survive IR round-trip."""
        config = (FIXTURES / "advanced_policy_nat.conf").read_text()
        cfg = FTGConfig(config)
        device = ftg_export.to_ir(cfg)

        output = ftg_import.from_ir(device)
        self.assertIn('set srcintf "port2"', output)
        self.assertIn('set dstintf "port1"', output)
        self.assertIn('config firewall vip', output)
        self.assertIn('edit "WEB-VIP"', output)
        self.assertIn('set nat enable', output)
        self.assertIn('config firewall central-snat-map', output)
        self.assertIn('set nat-ippool "OUT_POOL"', output)


class TestCrossVendorTranslation(unittest.TestCase):
    """Test cross-vendor translation (ASA ↔ FortiGate)."""

    def test_asa_to_fortigate_objects(self):
        """Test ASA network objects translate to FortiGate addresses."""
        config = """
object network HOST1
 host 10.0.0.1
object network NET1
 subnet 192.168.1.0 255.255.255.0
"""
        cfg = ASAConfig(config)
        device = asa_export.to_ir(cfg)

        # Translate to FortiGate
        output = ftg_import.from_ir(device)

        # Verify FortiGate syntax
        self.assertIn('config firewall address', output)
        self.assertIn('edit "HOST1"', output)
        self.assertIn('set subnet 10.0.0.1 255.255.255.255', output)
        self.assertIn('edit "NET1"', output)
        self.assertIn('set subnet 192.168.1.0 255.255.255.0', output)

    def test_asa_to_fortigate_groups(self):
        """Test ASA object-groups translate to FortiGate addrgrp."""
        config = """
object network OBJ1
 host 10.0.0.1
object-group network GRP1
 network-object object OBJ1
"""
        cfg = ASAConfig(config)
        device = asa_export.to_ir(cfg)

        output = ftg_import.from_ir(device)

        self.assertIn('config firewall addrgrp', output)
        self.assertIn('edit "GRP1"', output)
        self.assertIn('set member', output)

    def test_fortigate_to_asa_addresses(self):
        """Test FortiGate addresses translate to ASA objects."""
        config = """
config firewall address
    edit "HOST1"
        set subnet 10.0.0.1 255.255.255.255
    next
end
"""
        cfg = FTGConfig(config)
        device = ftg_export.to_ir(cfg)

        output = asa_import.from_ir(device)

        self.assertIn('object network HOST1', output)
        self.assertIn('host 10.0.0.1', output)

    def test_fortigate_to_asa_groups(self):
        """Test FortiGate addrgrp translate to ASA object-groups."""
        config = """
config firewall address
    edit "HOST1"
        set subnet 10.0.0.1 255.255.255.255
    next
end
config firewall addrgrp
    edit "GRP1"
        set member "HOST1"
    next
end
"""
        cfg = FTGConfig(config)
        device = ftg_export.to_ir(cfg)

        output = asa_import.from_ir(device)

        self.assertIn('object-group network GRP1', output)
        self.assertIn('network-object object HOST1', output)


class TestIRSchemaStability(unittest.TestCase):
    """Test IR schema structure and stability."""

    def test_ir_version_present(self):
        """Ensure IR version is tracked."""
        config = "object network TEST\n host 10.0.0.1"
        cfg = ASAConfig(config)
        device = asa_export.to_ir(cfg)

        self.assertIsNotNone(device.ir_version)
        self.assertEqual(device.ir_version, ir.IR_VERSION)

    def test_to_dict_json_serializable(self):
        """Ensure IR can be serialized to JSON."""
        config = """
object network HOST1
 host 10.0.0.1
object-group network GRP1
 network-object object HOST1
"""
        cfg = ASAConfig(config)
        device = asa_export.to_ir(cfg)

        # to_dict should produce JSON-serializable output
        import json
        device_dict = device.to_dict()
        json_str = json.dumps(device_dict)
        self.assertIsInstance(json_str, str)

        # Verify structure
        self.assertIn('vendor', device_dict)
        self.assertIn('objects', device_dict)
        self.assertIn('groups', device_dict)

    def test_ir_preserves_object_literals(self):
        """Ensure IP literals are preserved as strings in IR."""
        config = "object network TEST\n host 10.0.0.1\n subnet 192.168.0.0 255.255.255.0"
        cfg = ASAConfig(config)
        device = asa_export.to_ir(cfg)

        test_obj = device.objects[0]
        self.assertIsInstance(test_obj.literals, list)
        for literal in test_obj.literals:
            self.assertIsInstance(literal, str)


class TestRoutingProtocolTranslation(unittest.TestCase):
    """Test routing protocol IR translation."""

    def test_asa_static_routes_to_ir(self):
        """Test ASA static routes export to IR."""
        config = """
route outside 0.0.0.0 0.0.0.0 203.0.113.1 1
route inside 192.168.1.0 255.255.255.0 10.0.0.1 10 tunneled
route dmz 10.20.0.0 255.255.0.0 10.20.1.1 1 track 10
"""
        cfg = ASAConfig(config)
        device = asa_export.to_ir(cfg)

        # Verify static routes
        self.assertEqual(len(device.static_routes), 3)

        # Check default route
        default_route = next((r for r in device.static_routes if r.destination == '0.0.0.0/0'), None)
        self.assertIsNotNone(default_route)
        self.assertEqual(default_route.next_hop, '203.0.113.1')
        self.assertEqual(default_route.interface, 'outside')
        self.assertEqual(default_route.distance, 1)

        # Check tunneled route
        tunneled = next((r for r in device.static_routes if r.tunneled), None)
        self.assertIsNotNone(tunneled)
        self.assertEqual(tunneled.destination, '192.168.1.0/24')

        # Check tracked route
        tracked = next((r for r in device.static_routes if r.track is not None), None)
        self.assertIsNotNone(tracked)
        self.assertEqual(tracked.track, 10)

    def test_asa_ospf_to_ir(self):
        """Test ASA OSPF configuration export to IR."""
        config = """
router ospf 1
 router-id 1.1.1.1
 network 192.168.1.0 255.255.255.0 area 0
 network 192.168.2.0 255.255.255.0 area 1
 log-adjacency-changes
"""
        cfg = ASAConfig(config)
        device = asa_export.to_ir(cfg)

        # Verify OSPF process
        self.assertEqual(len(device.dynamic_routing), 1)
        ospf = device.dynamic_routing[0]

        self.assertEqual(ospf.protocol, 'ospf')
        self.assertEqual(ospf.process_id, '1')  # Process ID stored as string
        self.assertEqual(ospf.router_id, '1.1.1.1')
        self.assertEqual(len(ospf.networks), 2)

        # Check networks
        area0 = next((n for n in ospf.networks if n.get('area') == '0'), None)
        self.assertIsNotNone(area0)
        self.assertIn('192.168.1.0', area0.get('network', ''))

    def test_asa_bgp_to_ir(self):
        """Test ASA BGP configuration export to IR."""
        config = """
router bgp 65001
 router-id 10.10.10.10
 neighbor 203.0.113.100 remote-as 65002
 neighbor 203.0.113.101 remote-as 65003
"""
        cfg = ASAConfig(config)
        device = asa_export.to_ir(cfg)

        # Verify BGP process
        bgp = next((r for r in device.dynamic_routing if r.protocol == 'bgp'), None)
        self.assertIsNotNone(bgp)
        self.assertEqual(bgp.process_id, '65001')  # Process ID stored as string
        self.assertEqual(bgp.router_id, '10.10.10.10')
        self.assertEqual(len(bgp.neighbors), 2)

        # Check neighbor
        neighbor = bgp.neighbors[0]
        self.assertIn('ip', neighbor)
        self.assertIn('remote_as', neighbor)

    def test_fortigate_static_routes_to_ir(self):
        """Test FortiGate static routes export to IR."""
        config = """
config router static
    edit 1
        set dst 0.0.0.0/0
        set gateway 203.0.113.1
        set device "wan1"
        set distance 10
    next
    edit 2
        set dst 192.168.1.0/24
        set gateway 10.0.0.1
        set device "lan"
    next
end
"""
        cfg = FTGConfig(config)
        device = ftg_export.to_ir(cfg)

        # Verify routes
        self.assertEqual(len(device.static_routes), 2)

        default = next((r for r in device.static_routes if r.destination == '0.0.0.0/0'), None)
        self.assertIsNotNone(default)
        self.assertEqual(default.next_hop, '203.0.113.1')
        self.assertEqual(default.interface, 'wan1')
        self.assertEqual(default.distance, 10)

    def test_fortigate_ospf_to_ir(self):
        """Test FortiGate OSPF export to IR."""
        config = """
config router ospf
    set router-id 1.1.1.1
    config network
        edit 1
            set prefix 192.168.1.0/24
            set area 0.0.0.0
        next
        edit 2
            set prefix 192.168.2.0/24
            set area 0.0.0.1
        next
    end
end
"""
        cfg = FTGConfig(config)
        device = ftg_export.to_ir(cfg)

        # Verify OSPF
        ospf = next((r for r in device.dynamic_routing if r.protocol == 'ospf'), None)
        self.assertIsNotNone(ospf)
        self.assertEqual(ospf.router_id, '1.1.1.1')
        self.assertEqual(len(ospf.networks), 2)  # Should capture both networks now

        # Verify both networks were parsed
        area0 = next((n for n in ospf.networks if n.get('area') == '0.0.0.0'), None)
        area1 = next((n for n in ospf.networks if n.get('area') == '0.0.0.1'), None)
        self.assertIsNotNone(area0)
        self.assertIsNotNone(area1)

    def test_routing_cross_vendor_asa_to_fortigate(self):
        """Test ASA routing translates to FortiGate."""
        config = """
route outside 0.0.0.0 0.0.0.0 203.0.113.1 1
router ospf 1
 router-id 1.1.1.1
 network 192.168.1.0 255.255.255.0 area 0
"""
        cfg = ASAConfig(config)
        device = asa_export.to_ir(cfg)

        # Translate to FortiGate
        output = ftg_import.from_ir(device)

        # Verify FortiGate routing syntax
        self.assertIn('config router static', output)
        self.assertIn('set dst 0.0.0.0/0', output)
        self.assertIn('set gateway 203.0.113.1', output)
        self.assertIn('config router ospf', output)
        self.assertIn('set router-id 1.1.1.1', output)

    def test_routing_cross_vendor_fortigate_to_asa(self):
        """Test FortiGate routing translates to ASA."""
        config = """
config router static
    edit 1
        set dst 0.0.0.0/0
        set gateway 203.0.113.1
        set device "outside"
        set distance 1
    next
end
config router ospf
    set router-id 1.1.1.1
    config network
        edit 1
            set prefix 192.168.1.0/24
            set area 0.0.0.0
        next
    end
end
"""
        cfg = FTGConfig(config)
        device = ftg_export.to_ir(cfg)

        # Translate to ASA
        output = asa_import.from_ir(device)

        # Verify ASA routing syntax
        self.assertIn('route outside 0.0.0.0 0.0.0.0 203.0.113.1 1', output)
        self.assertIn('router ospf', output)
        self.assertIn('router-id 1.1.1.1', output)
        self.assertIn('network 192.168.1.0', output)


if __name__ == '__main__':
    unittest.main()
