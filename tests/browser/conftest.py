"""Browser test harness: a static page server, and one selenium driver per browser.

The driver fixture is parametrized over firefox and chrome. A browser or driver binary that is
missing skips that case with a message; it never fails the run. Firefox and geckodriver come from
scripts/dev/install-browsers.sh (pinned); Chrome and chromedriver are looked up on PATH.
"""

from __future__ import annotations

import functools
import shutil
import json
import os
import subprocess
import tempfile
import threading
import urllib.request
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from shutil import which
from typing import Any

import pytest

TESTS_BROWSER = Path(__file__).resolve().parent
REPO = TESTS_BROWSER.parents[1]
EXTENSION_DIST = REPO / "extension" / "dist"
PAGES_DIR = TESTS_BROWSER / "pages"
INSTALL_SCRIPT = REPO / "scripts" / "dev" / "install-browsers.sh"
PRINT_DIR_TIMEOUT_SECONDS = 10
CDP_TIMEOUT_SECONDS = 20
# The path of the Chrome extension copy a case loaded: Chrome derives the extension id from the path,
# so panel_page.py reads it from this variable. The fixture sets it and removes it at teardown.
CHROME_LOADED_PATH_ENV = "KATA_BROWSER_CHROME_EXTENSION_PATH"
LOOPBACK_HOST_PATTERN = "http://127.0.0.1/*"
FIREFOX_GECKO_ID = "kata@kata.invalid"
# Fixed uuid for the Firefox extension origin: moz-extension://<uuid>/sidepanel.html is known.
FIREFOX_EXTENSION_UUID = "6f1c3d2e-8a4b-4c5d-9e7f-0a1b2c3d4e5f"
# Chrome creates its singleton socket under TMPDIR; unix socket paths are limited to 108 bytes, so a
# long TMPDIR (a scratch dir) makes Chrome exit at start. Chrome gets its own short temp dir here.
CHROME_TMP_ROOT = "/tmp"
BROWSER_NAMES = ["firefox", "chrome"]
# Firefox content-override value per colour scheme: 0 forces dark, 1 forces light.
FIREFOX_SCHEME_OVERRIDE = {"dark": 0, "light": 1}


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture(params=BROWSER_NAMES)
def browser_name(request: pytest.FixtureRequest) -> str:
    """The browser this case runs in: one case per entry of BROWSER_NAMES."""
    name: str = request.param
    return name


@pytest.fixture
def color_scheme(request: pytest.FixtureRequest) -> str:
    """The prefers-color-scheme the driver forces: 'dark' unless a test parametrizes it indirectly."""
    scheme: str = getattr(request, "param", "dark")
    return scheme


@pytest.fixture
def page_server() -> Iterator[str]:
    """Serve tests/browser/pages on 127.0.0.1 port 0. Yields the base URL; stops it at teardown."""
    handler = functools.partial(_QuietHandler, directory=str(PAGES_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, name="browser-page-server", daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _install_dir() -> Path:
    """The install directory printed by install-browsers.sh --print-dir (no network)."""
    result = subprocess.run(
        ["bash", str(INSTALL_SCRIPT), "--print-dir"],
        capture_output=True,
        text=True,
        check=True,
        timeout=PRINT_DIR_TIMEOUT_SECONDS,
    )
    return Path(result.stdout.strip())


def _firefox_binaries() -> tuple[Path, Path]:
    """Firefox and geckodriver from the pinned install; skip the case when either is missing."""
    base = _install_dir()
    firefox = base / "firefox" / "firefox"
    geckodriver = base / "geckodriver"
    for binary in (firefox, geckodriver):
        if not binary.is_file():
            pytest.skip(f"{binary} missing: run scripts/dev/install-browsers.sh")
    return firefox, geckodriver


def _chrome_binaries() -> tuple[Path, Path]:
    """Chrome and chromedriver from PATH; skip the case when either is missing."""
    chrome = which("google-chrome") or which("chromium") or which("chromium-browser")
    chromedriver = which("chromedriver")
    for name, found in (("chrome", chrome), ("chromedriver", chromedriver)):
        if found is None:
            pytest.skip(f"{name} not on PATH: install it, see scripts/dev/install-browsers.sh")
    assert chrome is not None and chromedriver is not None
    return Path(chrome), Path(chromedriver)


def _require_extension(browser: str) -> Path:
    """The built extension for one browser; fail (not skip) when it was not built."""
    path = EXTENSION_DIST / browser
    if not (path / "manifest.json").is_file():
        pytest.fail(f"{path} missing: build the extension first (npm run build in extension/)")
    return path


def _chrome_extension_with_loopback_grant(source: Path, target: Path) -> Path:
    """Copy the built Chrome extension to target with 127.0.0.1 granted as a host permission.

    Headless Chrome never answers permissions.request, so the tests grant the loopback origin in the
    manifest copy instead (a match pattern ignores the port, so any stub port is covered).
    """
    shutil.copytree(source, target)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["host_permissions"] = [LOOPBACK_HOST_PATTERN]
    manifest_path.write_text(json.dumps(manifest))
    return target


def _load_chrome_extension(driver: Any, path: Path) -> None:
    """Install the unpacked extension via the browser's CDP Extensions domain; fail on an error reply."""
    import websocket

    debugger = driver.capabilities["goog:chromeOptions"]["debuggerAddress"]
    with urllib.request.urlopen(
        f"http://{debugger}/json/version", timeout=CDP_TIMEOUT_SECONDS
    ) as resp:
        ws_url = json.load(resp)["webSocketDebuggerUrl"]
    conn = websocket.create_connection(ws_url, timeout=CDP_TIMEOUT_SECONDS)
    try:
        conn.send(
            json.dumps(
                {"id": 1, "method": "Extensions.loadUnpacked", "params": {"path": str(path)}}
            )
        )
        while True:
            reply = json.loads(conn.recv())
            if reply.get("id") == 1:
                break
    finally:
        conn.close()
    if "error" in reply:
        pytest.fail(f"Extensions.loadUnpacked {path} failed: {reply['error']}")


@pytest.fixture
def driver(browser_name: str, color_scheme: str) -> Iterator[Any]:
    """A headless selenium driver with the built extension loaded. Quit at teardown.

    Each call owns its state, so xdist workers and cases do not share it: a profile dir, a driver
    port (the driver service picks a free port per instance, port 0) and a temp dir, all removed at
    teardown.
    """
    webdriver = pytest.importorskip("selenium.webdriver")
    if browser_name == "firefox":
        from selenium.webdriver.firefox.options import Options as FirefoxOptions
        from selenium.webdriver.firefox.service import Service as FirefoxService

        firefox, geckodriver = _firefox_binaries()
        extension = _require_extension("firefox")
        with tempfile.TemporaryDirectory(prefix="kata-ff-profile-") as profile:
            options = FirefoxOptions()
            options.binary_location = str(firefox)
            options.add_argument("-headless")
            # This case's own profile: geckodriver uses it, the TemporaryDirectory removes it.
            options.add_argument("-profile")
            options.add_argument(profile)
            options.set_preference(
                "extensions.webextensions.uuids",
                json.dumps({FIREFOX_GECKO_ID: FIREFOX_EXTENSION_UUID}),
            )
            # 0 = dark, 1 = light: every page this driver opens reports the scheme (see panel_page.py).
            options.set_preference(
                "layout.css.prefers-color-scheme.content-override",
                FIREFOX_SCHEME_OVERRIDE[color_scheme],
            )
            service = FirefoxService(executable_path=str(geckodriver), port=0)
            drv = webdriver.Firefox(service=service, options=options)
            try:
                drv.install_addon(str(extension), temporary=True)
                yield drv
            finally:
                drv.quit()
    else:
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.chrome.service import Service as ChromeService

        chrome, chromedriver = _chrome_binaries()
        extension = _require_extension("chrome")
        # Chrome gets its own short temp dir under CHROME_TMP_ROOT; its user-data-dir is a child of it.
        with tempfile.TemporaryDirectory(dir=CHROME_TMP_ROOT) as chrome_tmp:
            options = ChromeOptions()
            options.binary_location = str(chrome)
            options.add_argument("--headless=new")
            options.add_argument(f"--user-data-dir={Path(chrome_tmp) / 'profile'}")
            # Branded Chrome 137+ ignores --load-extension; the extension is installed over CDP instead.
            options.add_argument("--enable-unsafe-extension-debugging")
            # The CDP websocket below comes from this test process; the debugger port is local only.
            options.add_argument("--remote-allow-origins=*")
            service = ChromeService(
                executable_path=str(chromedriver),
                port=0,
                env={**os.environ, "TMPDIR": chrome_tmp},
            )
            drv = webdriver.Chrome(service=service, options=options)
            try:
                granted = _chrome_extension_with_loopback_grant(extension, Path(chrome_tmp) / "extension")
                _load_chrome_extension(drv, granted)
                os.environ[CHROME_LOADED_PATH_ENV] = str(granted)
                yield drv
            finally:
                os.environ.pop(CHROME_LOADED_PATH_ENV, None)
                drv.quit()
