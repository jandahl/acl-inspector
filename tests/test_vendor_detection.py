"""Test vendor detection for repository indexing."""

import unittest
import sys
import os

# Add scripts to path for importing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from index_repo import _detect_vendor


class TestVendorDetection(unittest.TestCase):
    """Test vendor detection heuristics for various firewall platforms."""

    def test_cisco_asa_version_banner(self):
        """Cisco ASA identified by version banner."""
        config = """
Cisco Adaptive Security Appliance Software Version 9.8(2)20
Device Manager Version 7.6(2)

Compiled on Mon 08-May-17 17:03 PDT by builders
Hardware:   ASA5516, 8192 MB RAM, CPU Xeon 5500 series 2133 MHz
"""
        vendor, score, reason = _detect_vendor(config, "firewall.conf")
        self.assertEqual(vendor, 'asa')
        self.assertGreaterEqual(score, 80)
        self.assertEqual(reason, 'asa_version_banner')

    def test_cisco_asa_alternate_banner(self):
        """Cisco ASA identified by alternate banner format."""
        config = "ASA Version 9.12(3)12\ninterface GigabitEthernet0/0\n nameif outside"
        vendor, score, reason = _detect_vendor(config, "asa-fw.txt")
        self.assertEqual(vendor, 'asa')
        self.assertGreaterEqual(score, 80)

    def test_cisco_asa_filename_extension(self):
        """Cisco ASA identified by .asa extension."""
        config = "access-list OUTSIDE_IN extended permit tcp any any eq 443"
        vendor, score, reason = _detect_vendor(config, "firewall.asa")
        self.assertEqual(vendor, 'asa')

    def test_cisco_asa_acl_syntax(self):
        """Cisco ASA identified by ACL syntax."""
        config = """
access-list OUTSIDE_IN extended permit tcp any object WebServer eq https
object network WebServer
 host 192.168.1.50
nameif outside
security-level 0
"""
        vendor, score, reason = _detect_vendor(config, "config.txt")
        self.assertEqual(vendor, 'asa')
        self.assertGreaterEqual(score, 50)

    def test_fortigate_config_version(self):
        """FortiGate identified by config-version."""
        config = """
#config-version=FGT60E-6.4.4-FW-build1803-201130:opmode=0:vdom=0
config system global
    set hostname "FortiGate-60E"
    set timezone 04
end
config firewall policy
    edit 1
        set name "LAN to WAN"
        set uuid 12345678-1234-1234-1234-123456789012
"""
        vendor, score, reason = _detect_vendor(config, "fortigate.conf")
        self.assertEqual(vendor, 'fortigate')
        self.assertGreaterEqual(score, 70)

    def test_fortigate_firewall_policy(self):
        """FortiGate identified by firewall policy syntax."""
        config = """
config firewall policy
    edit 1
        set srcintf "port1"
        set dstintf "port2"
        set action accept
        set uuid a1b2c3d4-e5f6-7890-abcd-ef1234567890
    next
end
"""
        vendor, score, reason = _detect_vendor(config, "fw.fgd")
        self.assertEqual(vendor, 'fortigate')
        self.assertGreaterEqual(score, 60)

    def test_ios_xe_version_banner(self):
        """IOS-XE identified by version banner."""
        config = """
Cisco IOS XE Software, Version 17.06.01a
Cisco IOS Software [Bengaluru], Catalyst L3 Switch Software (CAT9K_IOSXE)
Copyright (c) 1986-2021 by Cisco Systems, Inc.
"""
        vendor, score, reason = _detect_vendor(config, "switch.cfg")
        self.assertEqual(vendor, 'ios-xe')
        self.assertGreaterEqual(score, 85)
        self.assertEqual(reason, 'ios_xe_version_banner')

    def test_ios_xe_platform_identifier(self):
        """IOS-XE identified by platform identifier."""
        config = """
version 16.12
platform: IOS XE
hostname Switch1
interface GigabitEthernet1/0/1
"""
        vendor, score, reason = _detect_vendor(config, "catalyst.conf")
        self.assertEqual(vendor, 'ios-xe')
        self.assertGreaterEqual(score, 80)

    def test_ios_xr_version_banner(self):
        """IOS-XR identified by version banner."""
        config = """
!! IOS XR Configuration 7.3.2
!! Copyright (c) 2013-2021 by Cisco Systems, Inc.
Cisco IOS XR Software, Version 7.3.2
"""
        vendor, score, reason = _detect_vendor(config, "router-xr.cfg")
        self.assertEqual(vendor, 'ios-xr')
        self.assertGreaterEqual(score, 85)
        self.assertEqual(reason, 'ios_xr_version_banner')

    def test_ios_xr_filesystem_hint(self):
        """IOS-XR identified by filesystem paths."""
        config = """
boot system disk0:asr9k-mini-px-7.3.2.iso
disk0:/hfr-mgbl-4.0.0
rp/0/rp0/cpu0:Jan  1 00:00:00.000 UTC: installed
"""
        vendor, score, reason = _detect_vendor(config, "asr.conf")
        self.assertEqual(vendor, 'ios-xr')
        self.assertGreaterEqual(score, 60)

    def test_ios_xr_bgp_syntax(self):
        """IOS-XR identified by BGP address-family syntax."""
        config = """
router bgp 65000
 address-family ipv4 unicast
  network 10.0.0.0/8
 address-family ipv6 unicast
  network 2001:db8::/32
"""
        vendor, score, reason = _detect_vendor(config, "router.txt")
        self.assertEqual(vendor, 'ios-xr')

    def test_generic_ios_version_banner(self):
        """Generic IOS identified by version banner."""
        config = """
Cisco IOS Software, C2960 Software (C2960-LANBASEK9-M), Version 15.0(2)SE11
Technical Support: http://www.cisco.com/techsupport
Copyright (c) 1986-2016 by Cisco Systems, Inc.
"""
        vendor, score, reason = _detect_vendor(config, "switch-2960.cfg")
        self.assertEqual(vendor, 'ios')
        self.assertGreaterEqual(score, 80)
        self.assertEqual(reason, 'ios_version_banner')

    def test_generic_ios_version_command(self):
        """Generic IOS identified by version command."""
        config = """
version 15.2
service timestamps debug datetime msec
service timestamps log datetime msec
hostname Router1
"""
        vendor, score, reason = _detect_vendor(config, "router.conf")
        self.assertEqual(vendor, 'ios')
        self.assertGreaterEqual(score, 50)

    def test_generic_ios_interface_naming(self):
        """Generic IOS identified by interface naming."""
        config = """
interface GigabitEthernet0/0
 description WAN Link
 ip address 203.0.113.1 255.255.255.252
interface FastEthernet0/1
 description LAN
"""
        vendor, score, reason = _detect_vendor(config, "router.cfg")
        self.assertEqual(vendor, 'ios')

    def test_generic_ios_acl_syntax(self):
        """Generic IOS identified by ACL syntax."""
        config = """
ip access-list extended OUTSIDE_IN
 permit tcp any any eq 443
 deny ip any any
interface GigabitEthernet0/0
 ip access-group OUTSIDE_IN in
"""
        vendor, score, reason = _detect_vendor(config, "router.txt")
        self.assertEqual(vendor, 'ios')

    def test_ios_xe_priority_over_generic_ios(self):
        """IOS-XE takes priority over generic IOS when both match."""
        config = """
Cisco IOS XE Software, Catalyst L3 Switch Software
version 16.12
interface GigabitEthernet1/0/1
"""
        vendor, score, reason = _detect_vendor(config, "catalyst.cfg")
        self.assertEqual(vendor, 'ios-xe')
        # IOS-XE should score higher than generic IOS
        self.assertGreaterEqual(score, 85)

    def test_ios_xr_priority_over_generic_ios(self):
        """IOS-XR takes priority over generic IOS when both match."""
        config = """
Cisco IOS XR Software, Version 6.5.3
router bgp 65000
 address-family ipv4 unicast
"""
        vendor, score, reason = _detect_vendor(config, "asr9k.cfg")
        self.assertEqual(vendor, 'ios-xr')
        self.assertGreaterEqual(score, 85)

    def test_unknown_vendor(self):
        """Unknown vendor when no patterns match."""
        config = """
This is some random configuration file
with no recognizable vendor patterns
at all in the content or filename.
"""
        vendor, score, reason = _detect_vendor(config, "mystery.txt")
        self.assertEqual(vendor, 'unknown')
        self.assertEqual(score, 0)
        self.assertEqual(reason, 'no_match')

    def test_filename_hints_for_ios_variants(self):
        """Filename hints work for IOS variants."""
        config = "hostname Router1\ninterface GigabitEthernet0/0"

        vendor_xr, score_xr, _ = _detect_vendor(config, "router-xr.cfg")
        self.assertEqual(vendor_xr, 'ios-xr')

        vendor_xe, score_xe, _ = _detect_vendor(config, "switch-xe.cfg")
        self.assertEqual(vendor_xe, 'ios-xe')

        vendor_ios, score_ios, _ = _detect_vendor(config, "router-ios.cfg")
        self.assertEqual(vendor_ios, 'ios')

    def test_mixed_vendor_signals_highest_score_wins(self):
        """When mixed vendor signals exist, highest score wins."""
        # Config with both ASA and IOS keywords, but stronger ASA signal
        config = """
ASA Version 9.8(2)
interface GigabitEthernet0/0
 nameif outside
 security-level 0
ip access-list extended TEST
"""
        vendor, score, reason = _detect_vendor(config, "mixed.cfg")
        self.assertEqual(vendor, 'asa')
        self.assertGreaterEqual(score, 80)


if __name__ == '__main__':
    unittest.main()
