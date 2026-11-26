"""Shared helper for browser tests of the side panel page."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from browser.conftest import EXTENSION_DIST, FIREFOX_EXTENSION_UUID

PANEL_PATH = "/sidepanel.html"
# The sign-in form is the panel's first view with no session (extension/src/sidepanel.ts:63).
PANEL_INPUT_SELECTOR = 'form.signin input[name="code"]'
PANEL_WAIT_SECONDS = 10


def _chrome_extension_id(path: Path) -> str:
    """The id Chrome gives an unpacked extension: first 32 hex digits of sha256(path), a-p."""
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:32]
    return "".join(chr(ord("a") + int(digit, 16)) for digit in digest)


def panel_url(browser_name: str) -> str:
    if browser_name == "firefox":
        return f"moz-extension://{FIREFOX_EXTENSION_UUID}{PANEL_PATH}"
    return f"chrome-extension://{_chrome_extension_id(EXTENSION_DIST / 'chrome')}{PANEL_PATH}"


def open_panel(driver: Any, browser_name: str) -> None:
    """Open the panel page; return once the sign-in code input exists."""
    webdriver_support = pytest.importorskip("selenium.webdriver.support.ui")
    driver.get(panel_url(browser_name))
    wait = webdriver_support.WebDriverWait(driver, PANEL_WAIT_SECONDS)
    wait.until(
        lambda d: d.execute_script(f"return !!document.querySelector('{PANEL_INPUT_SELECTOR}')")
    )


def force_scheme(driver: Any, browser_name: str, scheme: str) -> None:
    """Make the page report prefers-color-scheme: <scheme> (light or dark) for every page opened next.

    Firefox: the layout.css.prefers-color-scheme.content-override pref is set at launch by the driver
    fixture (conftest.py) from the same scheme; chrome context is refused by geckodriver, so it is not set from script.
    Chrome: CDP Emulation.setEmulatedMedia. Callers check matchMedia after opening the page.
    """
    if browser_name == "firefox":
        return
    driver.execute_cdp_cmd(
        "Emulation.setEmulatedMedia",
        {"features": [{"name": "prefers-color-scheme", "value": scheme}]},
    )
