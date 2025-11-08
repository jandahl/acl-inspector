import contextlib
import io
import threading
import types
import unittest
from unittest import mock

from webui.shared import settings as settings_mod
from webui import server as server_mod


class RunServerPrewarmTests(unittest.TestCase):
    def test_run_server_does_not_block_on_prewarm(self):
        prewarm_started = threading.Event()
        release_prewarm = threading.Event()
        serve_called = threading.Event()

        def fake_prewarm(_server):
            prewarm_started.set()
            release_prewarm.wait(timeout=1.0)
            return 3

        class FakeHTTPServer:
            def __init__(self, *_args, **_kwargs):
                self.config_dirs = {}
                self.index_cache = {}
                self.cache_dir = None
                self.search_limit = 50
                self.theme_dir = "themes"
                self.themes = []
                self.app_state = None
                self.router = None

            def serve_forever(self):
                serve_called.set()
                raise KeyboardInterrupt()

            def server_close(self):
                pass

        fake_state = types.SimpleNamespace(themes=[], settings=settings_mod.Settings())
        settings = settings_mod.Settings(
            server=settings_mod.ServerSettings(host="127.0.0.1", port=0, prewarm_all=True)
        )

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
            mock.patch.object(server_mod.AppState, "create", return_value=fake_state), \
            mock.patch("webui.server.register_api"), \
            mock.patch("webui.server.register_pages"), \
            mock.patch("webui.server.register_static"), \
            mock.patch("webui.server.ThreadingHTTPServer", FakeHTTPServer), \
            mock.patch.object(server_mod, "_legacy") as legacy_mock:
            legacy_mock.prewarm_all_configs.side_effect = fake_prewarm
            thread = threading.Thread(target=server_mod.run_server, args=(settings,), daemon=True)
            thread.start()
            self.assertTrue(prewarm_started.wait(timeout=1.0), "prewarm thread never started")
            self.assertTrue(serve_called.wait(timeout=1.0), "server did not begin serving")
            # Ensure we can still shut down cleanly even while prewarm is running.
            release_prewarm.set()
            thread.join(timeout=1.0)
            self.assertFalse(thread.is_alive(), "run_server should exit promptly after shutdown")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
