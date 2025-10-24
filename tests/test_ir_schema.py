import json
import unittest

from parsers.cisco.asa import ASAConfig


ASA_SAMPLE = """
ASA Version 9.12(4)
interface GigabitEthernet0/0
 nameif outside
 security-level 0
 ip address 203.0.113.2 255.255.255.0
!
interface GigabitEthernet0/1
 nameif inside
 security-level 100
 ip address 10.0.0.1 255.255.255.0
!
object network OBJ_HOST1
 host 10.0.0.1
object network OBJ_NET1
 subnet 10.0.1.0 255.255.255.0
object-group network GRP_NET
 network-object object OBJ_NET1
 network-object host 10.0.2.2
object-group service SVC_WEB tcp
 service-object tcp eq 80
 service-object tcp eq 443
!
access-list OUT extended permit tcp object OBJ_HOST1 any eq 443
access-group OUT in interface outside
"""


class TestIRSchema(unittest.TestCase):
    def test_asa_to_ir_device(self):
        cfg = ASAConfig(ASA_SAMPLE)
        dev = cfg.to_ir(device_name='test-fw')
        d = dev.to_dict()
        # Top-level shape
        self.assertEqual(d.get('vendor'), 'asa')
        self.assertEqual(d.get('os'), 'ASA')
        self.assertEqual(d.get('name'), 'test-fw')
        self.assertIn('ir_version', d)
        # Interfaces
        ifaces = {i['name']: i for i in d.get('interfaces', [])}
        self.assertIn('outside', ifaces)
        self.assertIn('inside', ifaces)
        self.assertEqual(ifaces['outside']['security_level'], 0)
        self.assertEqual(ifaces['inside']['security_level'], 100)
        # Objects and groups
        obj_names = [o['name'] for o in d.get('objects', [])]
        self.assertIn('OBJ_HOST1', obj_names)
        self.assertIn('OBJ_NET1', obj_names)
        grp_names = [g['name'] for g in d.get('groups', [])]
        self.assertIn('GRP_NET', grp_names)
        # Service group captured
        svc_grp_names = [g['name'] for g in d.get('service_groups', [])]
        self.assertIn('SVC_WEB', svc_grp_names)
        # ACLs
        acls = {a['name']: a for a in d.get('acls', [])}
        self.assertIn('OUT', acls)
        self.assertEqual(acls['OUT']['bound_to'], 'outside')
        self.assertEqual(acls['OUT']['binding']['direction'], 'in')
        entries = acls['OUT']['entries']
        self.assertGreaterEqual(len(entries), 1)
        e0 = entries[0]
        self.assertEqual(e0['action'], 'permit')
        self.assertEqual(e0['proto'], 'tcp')
        self.assertEqual(e0['bound_to'], 'outside')
        self.assertEqual(e0['binding']['direction'], 'in')
        # Service ports normalized
        svc = e0['svc']
        self.assertIn('dst_ports', svc)
        self.assertTrue(any(p.get('start') == 443 for p in svc['dst_ports']))
        # JSON serializable
        json.dumps(d)


if __name__ == '__main__':
    unittest.main()
