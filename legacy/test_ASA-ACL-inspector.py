#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
import sys
sys.path.insert(0, '.')
import unittest
import ipaddress
from ASA_ACL_inspector import ASAConfig, to_ip_network, nets_overlap, inspect_host, compare_old_new

class TestASAACLInspector(unittest.TestCase):

    def test_to_ip_network(self):
        self.assertEqual(to_ip_network('1.1.1.1'), ipaddress.ip_address('1.1.1.1'))
        self.assertEqual(to_ip_network('1.1.1.0', '255.255.255.0'), ipaddress.ip_network('1.1.1.0/24'))
        self.assertEqual(to_ip_network('1.1.1.0/24'), ipaddress.ip_network('1.1.1.0/24'))
        self.assertEqual(to_ip_network('any'), 'any')

    def test_nets_overlap(self):
        set_a = {ipaddress.ip_address('1.1.1.1')}
        set_b = {ipaddress.ip_network('1.1.1.0/24')}
        set_c = {ipaddress.ip_address('2.2.2.2')}
        set_d = {ipaddress.ip_network('2.2.2.0/24')}
        self.assertTrue(nets_overlap(set_a, set_b))
        self.assertFalse(nets_overlap(set_a, set_d))
        self.assertTrue(nets_overlap(set_b, set_a))
        self.assertFalse(nets_overlap(set_c, set_b))

    def test_config_parsing(self):
        config_text = """
object network TEST-HOST
 host 1.1.1.1
object-group network TEST-GROUP
 network-object object TEST-HOST
 network-object host 2.2.2.2
access-list TEST extended permit ip object-group TEST-GROUP any
"""
        cfg = ASAConfig(config_text)
        self.assertIn('TEST-HOST', cfg.network_objects)
        self.assertEqual(cfg.network_objects['TEST-HOST'], {ipaddress.ip_address('1.1.1.1')})
        self.assertIn('TEST-GROUP', cfg.network_object_groups)
        self.assertIn('TEST', cfg.acls)

    def test_resolve_network(self):
        config_text = """
object network TEST-HOST
 host 1.1.1.1
object-group network TEST-GROUP
 network-object object TEST-HOST
"""
        cfg = ASAConfig(config_text)
        resolved = cfg.resolve_network('TEST-GROUP')
        self.assertEqual(resolved, {ipaddress.ip_address('1.1.1.1')})

    def test_flatten_acl(self):
        config_text = "access-list TEST extended permit ip host 1.1.1.1 any"
        cfg = ASAConfig(config_text)
        entries = cfg.flatten_acl()
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry['src'], {ipaddress.ip_address('1.1.1.1')})
        self.assertEqual(entry['dst'], {ipaddress.ip_network('0.0.0.0/0')})

    def test_inspect_host(self):
        config_text = "access-list TEST extended permit ip host 1.1.1.1 any"
        report = inspect_host(config_text, '1.1.1.1')
        self.assertEqual(len(report['hits']), 1)

    def test_compare_old_new(self):
        config_text = """
access-list TEST extended permit ip host 1.1.1.1 any
access-list TEST extended permit ip host 2.2.2.2 any
"""
        diff = compare_old_new(config_text, '1.1.1.1', '3.3.3.3')
        self.assertEqual(len(diff['removed_from_old']), 1)
        self.assertEqual(len(diff['added_to_new']), 0)

if __name__ == '__main__':
    unittest.main()
