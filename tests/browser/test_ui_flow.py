"""Component tests of the page overlay pieces on a sample page: hover menu, Delete/Undo, pin, review tree.

These are component tests, not production tests: the content script does not wire the hover menu or
the concept actions on a page yet, so the page loads a harness bundle (tests/browser/harness/entry.ts,
built here with esbuild) that mounts the real overlay modules. The built content.js is covered by
test_prod_content.py. Runs once per browser (browser_name param, see conftest.py); a missing browser
skips that case. Nothing here reaches beyond 127.0.0.1.
"""

from __future__ import annotations

import functools
import json
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from browser.conftest import PAGES_DIR, REPO, TESTS_BROWSER, _QuietHandler

ESBUILD = REPO / "extension" / "node_modules" / ".bin" / "esbuild"
HARNESS_ENTRY = TESTS_BROWSER / "harness" / "entry.ts"
BUILD_TIMEOUT_SECONDS = 60
WAIT_SECONDS = 10
# Longer than the harness undo window (3 s) so a commit that was not undone has run.
COMMIT_WAIT_SECONDS = 8
SAMPLE_PATH = "/sample.html"
PIN = "#h .float"
STORAGE_KEY = "harness.storage"
POSITION_KEY = "kata.pinPosition"
DRAG_OFFSET = (-120, -80)
POSITION_TOLERANCE = 2


@pytest.fixture
def sample_site() -> Iterator[str]:
    """Serve sample.html with the harness bundle from a temp dir; remove it at teardown."""
    if not ESBUILD.is_file():
        pytest.fail(f"{ESBUILD} missing: run npm ci in extension/")
    with tempfile.TemporaryDirectory(prefix="kata-ui-flow-") as tmp:
        site = Path(tmp)
        shutil.copy(PAGES_DIR / "sample.html", site / "sample.html")
        subprocess.run(
            [str(ESBUILD), str(HARNESS_ENTRY), "--bundle", "--format=iife", f"--outfile={site / 'harness.js'}"],
            check=True,
            capture_output=True,
            timeout=BUILD_TIMEOUT_SECONDS,
        )
        handler = functools.partial(_QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, name="ui-flow-server", daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


def _wait(driver: Any, condition: str, seconds: float = WAIT_SECONDS) -> None:
    support = pytest.importorskip("selenium.webdriver.support.ui")
    support.WebDriverWait(driver, seconds).until(lambda d: d.execute_script(f"return !!({condition})"))


def _open(driver: Any, base: str) -> None:
    driver.get(f"{base}{SAMPLE_PATH}")
    _wait(driver, "document.querySelector('#h[data-ready]')")


def _find(driver: Any, selector: str) -> Any:
    return driver.find_element("css selector", selector)


def _pin_box(driver: Any) -> dict[str, float]:
    box: dict[str, float] = driver.execute_script(
        "const r = document.querySelector(arguments[0]).getBoundingClientRect();"
        "return {left: r.left, top: r.top, width: r.width, height: r.height};",
        PIN,
    )
    return box


def _actions(driver: Any) -> Any:
    from selenium.webdriver.common.action_chains import ActionChains

    return ActionChains(driver)


def test_component_hover_menu_opens_without_shift_and_changes_state(driver: Any, sample_site: str) -> None:
    _open(driver, sample_site)
    popover = "body > .popover:has(.hl-hover-menu)"
    assert not _find(driver, popover).is_displayed()
    _actions(driver).move_to_element(_find(driver, "#word")).perform()
    _wait(driver, f"document.querySelector('{popover}').getClientRects().length > 0")
    _find(driver, f"{popover} .state-learning").click()
    _wait(driver, "window.harnessLog.states.length === 1")
    assert driver.execute_script("return window.harnessLog.states") == ["learning"]


def test_component_delete_confirm_then_undo_then_commit(driver: Any, sample_site: str) -> None:
    _open(driver, sample_site)
    _find(driver, ".concept-delete").click()
    assert driver.execute_script("return !!document.querySelector('.confirm')")
    _find(driver, ".confirm-yes").click()
    _wait(driver, "document.querySelector('.concept-undo')")
    _find(driver, ".concept-undo").click()
    assert driver.execute_script("return !document.querySelector('.concept-undo')")
    assert driver.execute_script("return window.harnessLog.commits") == []
    # A second Delete that is not undone commits once the undo window has passed.
    _find(driver, ".concept-delete").click()
    _find(driver, ".confirm-yes").click()
    _wait(driver, "window.harnessLog.commits.length === 1", COMMIT_WAIT_SECONDS)
    assert driver.execute_script("return window.harnessLog.commits") == ["delete"]


def test_component_pin_drag_is_kept_after_reload(driver: Any, sample_site: str) -> None:
    _open(driver, sample_site)
    before = _pin_box(driver)
    grip = _find(driver, f"{PIN} .drag")
    _actions(driver).click_and_hold(grip).move_by_offset(*DRAG_OFFSET).release().perform()
    moved = _pin_box(driver)
    assert moved["left"] < before["left"] and moved["top"] < before["top"]
    _wait(driver, f"localStorage.getItem('{STORAGE_KEY}')")
    driver.refresh()
    _wait(driver, "document.querySelector('#h[data-ready]')")
    again = _pin_box(driver)
    assert abs(again["left"] - moved["left"]) <= POSITION_TOLERANCE
    assert abs(again["top"] - moved["top"]) <= POSITION_TOLERANCE


def test_component_pin_position_is_clamped_to_the_viewport(driver: Any, sample_site: str) -> None:
    _open(driver, sample_site)
    far = {POSITION_KEY: {"x": 99999, "y": 99999}}
    driver.execute_script("localStorage.setItem(arguments[0], arguments[1])", STORAGE_KEY, json.dumps(far))
    driver.refresh()
    _wait(driver, "document.querySelector('#h[data-ready]')")
    box = _pin_box(driver)
    size = driver.execute_script("return {w: window.innerWidth, h: window.innerHeight}")
    assert box["left"] + box["width"] <= size["w"] + POSITION_TOLERANCE
    assert box["top"] + box["height"] <= size["h"] + POSITION_TOLERANCE
    assert box["left"] >= 0 and box["top"] >= 0


def test_component_pin_collapse_and_expand(driver: Any, sample_site: str) -> None:
    _open(driver, sample_site)
    assert _find(driver, PIN).get_attribute("data-screen") == "pin"
    _find(driver, f"{PIN} .x").click()
    assert _find(driver, PIN).get_attribute("data-screen") == "pin-collapsed"
    _find(driver, f"{PIN} > .pinbtn").click()
    assert _find(driver, PIN).get_attribute("data-screen") == "pin"


def test_component_escape_closes_the_pin_menu(driver: Any, sample_site: str) -> None:
    from selenium.webdriver.common.keys import Keys

    _open(driver, sample_site)
    menu = f"{PIN} .popover"
    _find(driver, f"{PIN} .pinwrap .pinbtn").click()
    _wait(driver, f"document.querySelector('{menu}').getClientRects().length > 0")
    _actions(driver).send_keys(Keys.ESCAPE).perform()
    _wait(driver, f"document.querySelector('{menu}').getClientRects().length === 0")
    assert driver.execute_script(f"return document.querySelector('{menu}').getClientRects().length") == 0


def test_component_review_tree_is_collapsed_by_default(driver: Any, sample_site: str) -> None:
    _open(driver, sample_site)
    areas = driver.execute_script("return document.querySelectorAll('#review details.review-area').length")
    assert areas > 0
    assert driver.execute_script("return document.querySelectorAll('#review details.review-area[open]').length") == 0
