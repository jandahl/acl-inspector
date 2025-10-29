import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover
    PLAYWRIGHT_AVAILABLE = False


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(
    PLAYWRIGHT_AVAILABLE, "Playwright is required for UI smoke tests"
)
class TestWebUIWithPlaywright(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="webui_")
        cls._config_name = "asa_ui.conf"
        cfg_path = os.path.join(cls._tmpdir.name, cls._config_name)
        with open(cfg_path, "w", encoding="utf-8") as fh:
            fh.write(
                """
ASA Version 9.14(2)
object network OBJ_HOST
 host 10.10.10.10
object network OBJ_WEB
 host 10.10.20.20
access-list OUT extended permit tcp object OBJ_HOST object OBJ_WEB eq 443
"""
            )
        cls._port = _find_free_port()
        env = os.environ.copy()
        env["ACLINSPECTOR_CONFIGS_CISCO"] = cls._tmpdir.name
        env["ACLINSPECTOR_CONFIGS_FORTIGATE"] = cls._tmpdir.name
        env.setdefault("PYTHONUNBUFFERED", "1")
        cls._server = subprocess.Popen(
            [
                sys.executable,
                "access-list-web.py",
                "--addr",
                "127.0.0.1",
                "--port",
                str(cls._port),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        cls._wait_for_server()
        cls._play = sync_playwright().start()
        try:
            cls._browser = cls._play.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover
            cls._play.stop()
            cls._cleanup_server()
            raise unittest.SkipTest(f"Chromium not available: {exc}")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_browser", None):
            cls._browser.close()
        if getattr(cls, "_play", None):
            cls._play.stop()
        cls._cleanup_server()
        cls._tmpdir.cleanup()

    @classmethod
    def _wait_for_server(cls):
        deadline = time.time() + 15
        while time.time() < deadline:
            if cls._server.poll() is not None:
                stdout, stderr = cls._server.communicate()
                raise RuntimeError(
                    f"Server exited unexpectedly:\nSTDOUT:\n{stdout.decode()}\nSTDERR:\n{stderr.decode()}"
                )
            try:
                with socket.create_connection(
                    ("127.0.0.1", cls._port), timeout=0.5
                ):
                    return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("Timed out waiting for access-list-web.py to start")

    @classmethod
    def _cleanup_server(cls):
        if getattr(cls, "_server", None) and cls._server.poll() is None:
            cls._server.terminate()
            try:
                cls._server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls._server.kill()

    def _new_page(self):
        context = self._browser.new_context()
        self.addCleanup(context.close)
        page = context.new_page()
        self.addCleanup(lambda: page.close())
        return page

    def _goto_root(self, page):
        page.goto(f"http://127.0.0.1:{self._port}/", wait_until="networkidle")

    def _select_config(self, page):
        page.select_option("select#config", value=self._config_name)

    def _run_find(self, page, query="OBJ_HOST"):
        self._goto_root(page)
        self._select_config(page)
        page.click("button[data-tab='find']")
        page.fill("input#findq", query)
        page.wait_for_selector("datalist#targets option")  # ensure suggestions populated
        page.click("div.actions-run[data-tab='find'] button[type=submit]")
        page.wait_for_selector("div.results pre")

    def test_find_host_results_and_suggestions(self):
        page = self._new_page()
        self._goto_root(page)
        self._select_config(page)
        page.click("button[data-tab='find']")
        page.fill("input#findq", "OBJ")
        page.wait_for_selector("datalist#targets option")
        options = page.query_selector_all("datalist#targets option")
        self.assertTrue(any("OBJ_HOST" in opt.get_attribute("value") for opt in options))
        page.click("div.actions-run[data-tab='find'] button[type=submit]")
        page.wait_for_selector("div.results pre")
        text = page.text_content("div.results pre")
        self.assertIn("OBJ_HOST", text or "")

    def test_theme_and_highlight_toggle(self):
        page = self._new_page()
        self._run_find(page)
        page.wait_for_selector("div.results pre")
        body_class = page.get_attribute("body", "class") or ""
        self.assertIn("theme-dark", body_class)
        page.click("#themeToggle")
        page.wait_for_function(
            "document.body.classList.contains('theme-light')"
        )
        body_class = page.get_attribute("body", "class") or ""
        self.assertIn("theme-light", body_class)
        pre_selector = "div.results pre"
        page.wait_for_function(
            "sel => document.querySelector(sel).innerHTML.includes(\"class='addr'\")",
            arg=pre_selector,
        )
        page.click("#hlToggle")
        page.wait_for_function(
            "sel => !document.querySelector(sel).innerHTML.includes(\"class='addr'\")",
            arg=pre_selector,
        )
        page.click("#hlToggle")
        page.wait_for_function(
            "sel => document.querySelector(sel).innerHTML.includes(\"class='addr'\")",
            arg=pre_selector,
        )

    def test_state_persists_in_local_storage(self):
        page = self._new_page()
        self._run_find(page)
        page.click("#themeToggle")  # switch to light
        page.click("#hlToggle")  # disable highlight
        page.wait_for_timeout(100)  # allow storage writes
        page.reload(wait_until="networkidle")
        body_class = page.get_attribute("body", "class") or ""
        self.assertIn("theme-light", body_class)
        self.assertFalse(page.is_checked("#hlToggle"))

    def test_tab_switch_and_run_updates_results(self):
        page = self._new_page()
        self._goto_root(page)
        self._select_config(page)
        page.click("button[data-tab='find']")
        page.wait_for_function(
            "() => document.querySelector('#tab-find').classList.contains('active')"
        )
        page.fill("input#findq", "OBJ_HOST")
        start_url = page.url
        page.click("div.actions-run[data-tab='find'] button[type=submit]")
        page.wait_for_function(
            "() => document.querySelector(\"div.results[data-tab='find']\").textContent.includes('OBJ_HOST')"
        )
        self.assertEqual(page.url, start_url)

    def test_result_box_width_within_container(self):
        page = self._new_page()
        self._run_find(page)
        page.wait_for_selector("div.results[data-tab='find'] .result-box")
        dims = page.evaluate(
            """() => {
            const box = document.querySelector("div.results[data-tab='find'] .result-box");
            if (!box) {
                return null;
            }
            const parent = box.parentElement;
            const boxRect = box.getBoundingClientRect();
            const parentRect = parent ? parent.getBoundingClientRect() : { width: 0 };
            return { boxWidth: boxRect.width, parentWidth: parentRect.width };
        }"""
        )
        self.assertIsNotNone(dims)
        self.assertGreater(dims["boxWidth"], 0)
        self.assertGreater(dims["parentWidth"], 0)
        # Allow for sub-pixel rounding differences (hence the small epsilon).
        self.assertLessEqual(dims["boxWidth"], dims["parentWidth"] + 1.0)

    def test_inspect_run_shows_results_without_tab_switch(self):
        page = self._new_page()
        self._goto_root(page)
        self._select_config(page)
        self.assertTrue(page.is_visible("div.actions-run[data-tab='rules'] button[type=submit]"))
        page.fill("input#inspect", "OBJ_HOST")
        page.click("div.actions-run[data-tab='rules'] button[type=submit]")
        page.wait_for_function(
            "() => { const el = document.querySelector(\"div.results[data-tab='rules']\"); return el && el.textContent.includes('Inspection Report'); }"
        )
        display = page.evaluate(
            "() => window.getComputedStyle(document.querySelector(\"div.results[data-tab='rules']\")).display"
        )
        self.assertEqual(display, "block")

    def test_history_entry_replays_search(self):
        page = self._new_page()
        self._goto_root(page)
        self._select_config(page)
        page.fill("input#inspect", "OBJ_HOST")
        page.click("div.actions-run[data-tab='rules'] button[type=submit]")
        page.wait_for_function(
            "() => document.querySelector(\"div.results[data-tab='rules']\").textContent.includes('OBJ_HOST')"
        )
        page.fill("input#inspect", "OBJ_WEB")
        page.click("div.actions-run[data-tab='rules'] button[type=submit]")
        page.wait_for_function(
            "() => document.querySelector(\"div.results[data-tab='rules']\").textContent.includes('OBJ_WEB')"
        )
        page.click("#histToggle")
        page.wait_for_selector("button.hist-entry")
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('button.hist-entry'))"
            " .some(el => (el.textContent || '').includes('OBJ_HOST'))"
        )
        entries = page.query_selector_all("button.hist-entry")
        target = None
        for entry in entries:
            text = entry.text_content() or ""
            if "OBJ_HOST" in text:
                target = entry
                break
        self.assertIsNotNone(target)
        assert target
        target.click()
        page.wait_for_function(
            "() => document.querySelector(\"div.results[data-tab='rules']\").textContent.includes('OBJ_HOST')"
        )

    def test_shareable_link_restores_state(self):
        page = self._new_page()
        self._goto_root(page)
        self._select_config(page)
        page.fill("input#inspect", "OBJ_HOST")
        page.click("div.actions-run[data-tab='rules'] button[type=submit]")
        page.wait_for_function(
            "() => document.querySelector(\"div.results[data-tab='rules']\").textContent.includes('OBJ_HOST')"
        )
        share_url = page.url
        self.assertIn("inspect=OBJ_HOST", share_url)
        new_page = self._new_page()
        new_page.goto(share_url, wait_until="networkidle")
        new_page.wait_for_selector("select#config")
        new_page.wait_for_function(
            "expected => document.querySelector('select#config')?.value === expected",
            arg=self._config_name,
        )
        new_page.wait_for_function(
            "() => document.querySelector(\"div.results[data-tab='rules']\") && document.querySelector(\"div.results[data-tab='rules']\").textContent.includes('OBJ_HOST')"
        )
        config_value = new_page.get_attribute("select#config", "value")
        self.assertEqual(config_value, self._config_name)
        inspect_value = new_page.get_attribute("input#inspect", "value")
        self.assertEqual(inspect_value, "OBJ_HOST")
