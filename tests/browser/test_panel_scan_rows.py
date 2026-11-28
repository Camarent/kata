"""Browser proof: the Scan page button draws the scan rows the core returns, in the scan-results screen.

Runs once per browser (browser_name param, see conftest.py). A missing browser, driver or selenium
skips that case; nothing here reaches beyond 127.0.0.1 (the stub core, the lesson page and the panel).

The background scans the active tab of the window that holds the panel. So the lesson page is made
the active tab first (chrome.tabs.update from the panel), then the panel's Scan page button is clicked.
"""

from __future__ import annotations

from typing import Any

import pytest

from browser.panel_page import PANEL_WAIT_SECONDS, open_panel, panel_url
from browser.signed_in import grant_host_permission, seed_session
from browser.stub_core import stub_core

LESSON_PATH = "/lesson.html"
SCAN_LABEL = "pan"
SCAN_ROW_SELECTOR = "section.scan-results li.rrow span.nm"
SCAN_BUTTON_SELECTOR = "section.scan-results button.scan-page"
# The stub core answers every block with one finished job; the topic label is the row label.
STUB_ROUTES = {
    "/jobs": {"id": 1},
    "/jobs/1": {"status": "done", "topic": {"id": 1, "category": "cooking", "label": SCAN_LABEL}, "known": False},
}
# Makes the lesson tab active (the background scans the active tab), then clicks the Scan page button.
# The last argument of execute_async_script is the callback.
ACTIVATE_LESSON_AND_SCAN = """
const done = arguments[arguments.length - 1];
const lessonPath = arguments[0];
(async () => {
  const tabs = await chrome.tabs.query({});
  const lesson = tabs.find((tab) => tab.url && tab.url.endsWith(lessonPath));
  if (!lesson) throw new Error("lesson tab not found");
  await chrome.tabs.update(lesson.id, { active: true });
  document.querySelector("section.scan-results button.scan-page").click();
  return true;
})().then(() => done({ ok: true }), (err) => done({ error: String(err) }));
"""
# True when a scan-results row shows the label; the label is the script argument.
HAS_LABEL_SCRIPT = """
const label = arguments[0];
return [...document.querySelectorAll(arguments[1])].some((node) => node.textContent === label);
"""


def test_panel_scan_rows(browser_name: str, driver: Any, page_server: str) -> None:
    webdriver_support = pytest.importorskip("selenium.webdriver.support.ui")
    driver.get(f"{page_server}{LESSON_PATH}")
    driver.switch_to.new_window("tab")
    open_panel(driver, browser_name)
    with stub_core(STUB_ROUTES) as base_url:
        seed_session(driver, base_url)
        grant_host_permission(driver, base_url)
        driver.get(panel_url(browser_name))
        wait = webdriver_support.WebDriverWait(driver, PANEL_WAIT_SECONDS)
        wait.until(lambda d: d.execute_script(f"return !!document.querySelector('{SCAN_BUTTON_SELECTOR}')"))
        reply = driver.execute_async_script(ACTIVATE_LESSON_AND_SCAN, LESSON_PATH)
        assert not (isinstance(reply, dict) and "error" in reply), reply
        wait.until(lambda d: d.execute_script(HAS_LABEL_SCRIPT, SCAN_LABEL, SCAN_ROW_SELECTOR))
