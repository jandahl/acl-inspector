"""Tests for path_check_supported helper."""

import unittest

from analysis_core import path_check_supported
from parsers.cisco.asa import ASAConfig
from parsers.fortigate.config import FTGConfig


class TestPathCaps(unittest.TestCase):
    def test_asa_supported(self):
        cfg = ASAConfig("access-list ACL1 extended permit ip any any")
        self.assertTrue(path_check_supported(cfg))

    def test_fortigate_supported(self):
        cfg = FTGConfig(
            """
config vdom
    edit alpha
        config firewall address
            edit "a"
                set subnet 10.0.0.1 255.255.255.255
            next
        end
    next
end
"""
        )
        self.assertTrue(path_check_supported(cfg))

    def test_unknown_false(self):
        class Dummy:
            pass
        self.assertFalse(path_check_supported(Dummy()))


if __name__ == "__main__":
    unittest.main()
