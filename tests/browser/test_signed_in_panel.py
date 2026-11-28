"""Browser proof: a seeded session opens the panel signed in (tab bar, no sign-in form).

Runs once per browser (browser_name param, see conftest.py). A missing browser, driver or selenium
skips that case; nothing here reaches beyond 127.0.0.1 (the stub core and the extension pages).
"""

from __future__ import annotations

from typing import Any

import pytest

from browser.panel_page import PANEL_INPUT_SELECTOR, PANEL_WAIT_SECONDS, open_panel, panel_url
from browser.signed_in import grant_host_permission, seed_session
from browser.stub_core import stub_core

TABS_SELECTOR = "nav.tabs"
SIGNIN_FORM_SELECTOR = "form.signin"


def test_signed_in_panel_shows_tabs(browser_name: str, driver: Any) -> None:
    webdriver_support = pytest.importorskip("selenium.webdriver.support.ui")
    open_panel(driver, browser_name)
    with stub_core({}) as base_url:
        seed_session(driver, base_url)
        grant_host_permission(driver, base_url)
        driver.get(panel_url(browser_name))
        wait = webdriver_support.WebDriverWait(driver, PANEL_WAIT_SECONDS)
        wait.until(lambda d: d.execute_script(f"return !!document.querySelector('{TABS_SELECTOR}')"))
        assert driver.find_elements("css selector", SIGNIN_FORM_SELECTOR) == []
        assert driver.find_elements("css selector", PANEL_INPUT_SELECTOR) == []
