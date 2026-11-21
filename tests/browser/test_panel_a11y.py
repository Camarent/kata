"""Browser a11y: keyboard order and focus indicators of the side panel sign-in view."""

from __future__ import annotations

from typing import Any

import pytest

from browser.panel_page import open_panel

# Expected Tab order from the page start.
FOCUS_ORDER = ["input[name=code]", "input[name=deviceLabel]", "button[type=submit]"]
ACTIVE_MATCHES = "return document.activeElement.matches(arguments[0])"
IN_FORM = "return !!document.activeElement.closest('form.signin')"
FOCUS_INDICATOR = """
const s = getComputedStyle(document.activeElement);
const outline = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0;
return outline || s.boxShadow !== 'none';
"""


def test_signin_tab_order_and_focus_indicator(browser_name: str, driver: Any, page_server: str) -> None:
    action_chains = pytest.importorskip("selenium.webdriver.common.action_chains")
    keys = pytest.importorskip("selenium.webdriver.common.keys")
    open_panel(driver, browser_name)
    driver.execute_script("document.activeElement.blur()")
    chain = action_chains.ActionChains(driver)
    for selector in FOCUS_ORDER:
        chain.send_keys(keys.Keys.TAB).perform()
        assert driver.execute_script(ACTIVE_MATCHES, selector), selector
        assert driver.execute_script(FOCUS_INDICATOR), f"no visible focus indicator on {selector}"
    chain.send_keys(keys.Keys.TAB).perform()
    assert not driver.execute_script(IN_FORM)
