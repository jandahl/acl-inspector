"""Unit tests for TUI multi-config directory loading."""

import unittest
import tempfile
import os
from pathlib import Path


class TestTUIMultiConfig(unittest.TestCase):
    """Test TUI multi-config directory loading functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary directory with test configs
        self.test_dir = tempfile.mkdtemp()

        # Create test config 1
        self.config1_path = os.path.join(self.test_dir, "fw1.conf")
        with open(self.config1_path, 'w') as f:
            f.write("""
interface GigabitEthernet0/1
 nameif outside
 ip address 192.168.1.1 255.255.255.0
!
object network Server1
 host 10.0.1.10
object network Server2
 host 10.0.1.20
""")

        # Create test config 2
        self.config2_path = os.path.join(self.test_dir, "fw2.conf")
        with open(self.config2_path, 'w') as f:
            f.write("""
interface GigabitEthernet0/1
 nameif outside
 ip address 192.168.2.1 255.255.255.0
!
object network AppServer1
 host 172.16.1.10
object network AppServer2
 host 172.16.1.20
""")

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_directory_detection(self):
        """Test that TUI correctly detects directory vs file."""
        try:
            from tui.app import SingularityApp
        except ImportError:
            self.skipTest("textual not installed")

        # Test with directory
        app = SingularityApp(vendor="asa", config_path=self.test_dir)
        app._load_config()
        self.assertTrue(app.is_directory, "Should detect directory")
        self.assertEqual(len(app.config_files), 2, "Should find 2 config files")

        # Test with single file
        app_single = SingularityApp(vendor="asa", config_path=self.config1_path)
        app_single._load_config()
        self.assertFalse(app_single.is_directory, "Should detect single file")

    def test_multi_config_object_loading(self):
        """Test that objects from multiple configs are loaded."""
        try:
            from tui.app import SingularityApp
        except ImportError:
            self.skipTest("textual not installed")

        app = SingularityApp(vendor="asa", config_path=self.test_dir)
        app._load_config()

        # Should have objects from both configs
        self.assertGreater(len(app.all_objects), 0, "Should load objects")

        # Check that objects have source_file
        for obj in app.all_objects:
            self.assertIn('source_file', obj, "Object should have source_file")
            self.assertIn(obj['source_file'], ['fw1.conf', 'fw2.conf'],
                         f"source_file should be fw1.conf or fw2.conf, got {obj['source_file']}")

    def test_multi_config_parsed_configs_dict(self):
        """Test that parsed_configs dict is populated correctly."""
        try:
            from tui.app import SingularityApp
        except ImportError:
            self.skipTest("textual not installed")

        app = SingularityApp(vendor="asa", config_path=self.test_dir)
        app._load_config()

        # Should have entries for both files
        self.assertEqual(len(app.parsed_configs), 2, "Should have 2 parsed configs")
        self.assertIn('fw1.conf', app.parsed_configs, "Should have fw1.conf")
        self.assertIn('fw2.conf', app.parsed_configs, "Should have fw2.conf")

        # Each should have network_objects
        for filename, config in app.parsed_configs.items():
            self.assertTrue(hasattr(config, 'network_objects'),
                          f"{filename} config should have network_objects")

    def test_object_config_reference(self):
        """Test that each object has reference to its config."""
        try:
            from tui.app import SingularityApp
        except ImportError:
            self.skipTest("textual not installed")

        app = SingularityApp(vendor="asa", config_path=self.test_dir)
        app._load_config()

        # Each object should have config reference
        for obj in app.all_objects:
            self.assertIn('config', obj, "Object should have config reference")
            self.assertIsNotNone(obj['config'], "Config reference should not be None")

            # The config should be the same as in parsed_configs
            source_file = obj['source_file']
            self.assertIs(obj['config'], app.parsed_configs[source_file],
                         "Object config should reference parsed_configs entry")

    def test_single_file_backward_compatibility(self):
        """Test that single file mode still works (backward compatibility)."""
        try:
            from tui.app import SingularityApp
        except ImportError:
            self.skipTest("textual not installed")

        app = SingularityApp(vendor="asa", config_path=self.config1_path)
        app._load_config()

        # Should still set parsed_config for backward compatibility
        self.assertIsNotNone(app.parsed_config, "Single file mode should set parsed_config")
        self.assertFalse(app.is_directory, "Should not be directory mode")

        # Objects should still have source_file and config
        for obj in app.all_objects:
            self.assertIn('source_file', obj)
            self.assertIn('config', obj)
            self.assertEqual(obj['source_file'], 'fw1.conf')

    def test_empty_directory_handling(self):
        """Test that empty directory is handled gracefully."""
        try:
            from tui.app import SingularityApp
        except ImportError:
            self.skipTest("textual not installed")

        empty_dir = tempfile.mkdtemp()
        try:
            app = SingularityApp(vendor="asa", config_path=empty_dir)
            # Should raise or handle gracefully
            # The current implementation raises ValueError
            with self.assertRaises(ValueError):
                app._load_config()
        finally:
            import shutil
            shutil.rmtree(empty_dir)

    def test_hidden_files_ignored(self):
        """Test that hidden files (starting with .) are ignored."""
        try:
            from tui.app import SingularityApp
        except ImportError:
            self.skipTest("textual not installed")

        # Create a hidden file
        hidden_path = os.path.join(self.test_dir, ".hidden.conf")
        with open(hidden_path, 'w') as f:
            f.write("! hidden file\n")

        app = SingularityApp(vendor="asa", config_path=self.test_dir)
        app._load_config()

        # Should still find only 2 files (fw1.conf, fw2.conf)
        self.assertEqual(len(app.config_files), 2,
                        "Should ignore hidden files")

        # Verify no hidden file was loaded
        for config_file in app.config_files:
            self.assertFalse(os.path.basename(config_file).startswith('.'),
                           "Should not load hidden files")


if __name__ == '__main__':
    unittest.main()
