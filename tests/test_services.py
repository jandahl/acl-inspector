import unittest
from ASA_ACL_inspector import ASAConfig, evaluate_acl


class TestServices(unittest.TestCase):
    def test_eq_port_matching(self):
        cfg_text = """
access-list T extended permit tcp host 1.1.1.1 host 2.2.2.2 eq 443
"""
        cfg = ASAConfig(cfg_text)
        entries = cfg.flatten_acl()
        svc_filter = {'proto': 'tcp', 'dports': {443}}
        hits = evaluate_acl(entries, {cfg.resolve_network('1.1.1.1').pop()}, cfg, service_filter=svc_filter)
        self.assertEqual(len(hits), 1)

    def test_service_group_proto_position(self):
        cfg_text = """
object-group service SQLCL
 service-object tcp eq 1433
 service-object udp eq 1434
access-list T extended permit object-group SQLCL host 1.1.1.1 host 2.2.2.2
"""
        cfg = ASAConfig(cfg_text)
        entries = cfg.flatten_acl()
        svc_filter_tcp = {'proto': 'tcp', 'dports': {1433}}
        svc_filter_udp = {'proto': 'udp', 'dports': {1434}}
        src = cfg.resolve_network('1.1.1.1')
        hits_tcp = evaluate_acl(entries, src, cfg, service_filter=svc_filter_tcp)
        hits_udp = evaluate_acl(entries, src, cfg, service_filter=svc_filter_udp)
        self.assertEqual(len(hits_tcp), 1)
        self.assertEqual(len(hits_udp), 1)


if __name__ == '__main__':
    unittest.main()

