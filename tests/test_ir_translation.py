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
from parsers.cisco.asa.parser import ASAConfig
from parsers.cisco.asa import ir_export as asa_export
from parsers.cisco.asa import ir_import as asa_import
from parsers.fortigate.config import FTGConfig
from parsers.fortigate import ir_export as ftg_export
from parsers.fortigate import ir_import as ftg_import
from parsers import model as ir


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
        """Test that service object-groups survive round-trip.

        TODO: ASA parser currently doesn't parse port-object lines.
        This test is skipped until parser support is added.
        """
        self.skipTest("ASA parser does not yet parse port-object/service-object lines")


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


if __name__ == '__main__':
    unittest.main()
