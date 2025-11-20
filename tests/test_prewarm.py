import os
import tempfile
import importlib.util
import unittest


_MOD_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cli', 'cli/access-list-web.py')
spec = importlib.util.spec_from_file_location('access_list_web', _MOD_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)  # type: ignore


class DummyServer:
    def __init__(self, config_dirs, cache_dir=None):
        self.config_dirs = config_dirs
        self.cache_dir = cache_dir
        self.index_cache = {}
        self.search_limit = 50


def _write_cfg(text: str) -> str:
    tmp = tempfile.NamedTemporaryFile('w', delete=False, suffix='.cfg')
    tmp.write(text)
    tmp.flush()
    tmp.close()
    return tmp.name


class TestPrewarm(unittest.TestCase):
    def test_prewarm_builds_index_for_all_configs(self):
        cfg_path = _write_cfg(
            """
object network OBJ1
 host 10.0.0.1
object network OBJ2
 host 10.0.0.2
""".strip()
        )
        try:
            directory = os.path.dirname(cfg_path)
            config_dirs = {'asa': directory, 'fortigate': ''}
            server = DummyServer(config_dirs)
            count = mod.prewarm_all_configs(server)
            self.assertGreaterEqual(count, 1)
            self.assertTrue(any(payload.get('index') for payload in server.index_cache.values()))
        finally:
            os.unlink(cfg_path)


if __name__ == '__main__':
    unittest.main()
