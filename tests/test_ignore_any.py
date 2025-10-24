import unittest

from parsers.cisco.asa import ASAConfig, inspect_host


ASA_SAMPLE = """
object network HOST
 host 10.0.0.10
object network WEB
 host 10.0.0.20
access-list OUT extended permit tcp any object WEB eq 443
access-list OUT extended permit tcp object HOST object WEB eq 443
"""


class TestIgnoreAny(unittest.TestCase):
    def test_ignore_any_default(self):
        report = inspect_host(ASA_SAMPLE, 'HOST', service_filter=None)
        # Should only include the specific HOST->WEB rule by default
        self.assertEqual(len(report['hits']), 1)
        self.assertIn('object HOST', report['hits'][0]['raw'])

    def test_include_any_flag(self):
        report = inspect_host(ASA_SAMPLE, 'HOST', service_filter=None, include_any=True)
        # Should include both rules now
        self.assertEqual(len(report['hits']), 2)


if __name__ == '__main__':
    unittest.main()

