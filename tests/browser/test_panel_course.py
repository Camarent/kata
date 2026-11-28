"""Browser proof: the Courses tab shows a course's version label, Open course shows the course page with its version label.

Runs once per browser (browser_name param, see conftest.py). A missing browser, driver or selenium
skips that case; nothing here reaches beyond 127.0.0.1 (the stub core and the extension pages).
"""

from __future__ import annotations

from typing import Any

import pytest

from browser.panel_page import PANEL_WAIT_SECONDS, open_panel, panel_url
from browser.signed_in import grant_host_permission, seed_session
from browser.stub_core import stub_core

COURSE_ID = 4
STUB_LIST = {
    "items": [{"id": COURSE_ID, "title": "Algebra", "status": "ready", "version": 2, "concept_ids": []}],
    "limit": 5,
    "total": 1,
}


def _click(driver: Any, selector: str) -> None:
    driver.execute_script(f"document.querySelector('{selector}').click()")


def _text(driver: Any, selector: str) -> str:
    return driver.execute_script(f"return document.querySelector('{selector}').textContent")


def test_panel_course_page_with_version(browser_name: str, driver: Any) -> None:
    webdriver_support = pytest.importorskip("selenium.webdriver.support.ui")
    open_panel(driver, browser_name)
    received: list[str] = []
    routes: dict[str, Any] = {f"/v1/courses/{COURSE_ID}/open": {}, "/v1/courses": STUB_LIST}
    with stub_core(routes, received) as base_url:
        # The stub serves the same dict it was started with, so the open URL can name the stub port now.
        routes[f"/v1/courses/{COURSE_ID}/open"] = {"url": f"{base_url}/c/{COURSE_ID}"}
        seed_session(driver, base_url)
        grant_host_permission(driver, base_url)
        driver.get(panel_url(browser_name))
        wait = webdriver_support.WebDriverWait(driver, PANEL_WAIT_SECONDS)

        def present(selector: str) -> Any:
            return lambda d: d.execute_script(f"return !!document.querySelector('{selector}')")

        wait.until(present("nav.tabs"))
        _click(driver, "nav.tabs button.tab-courses")
        wait.until(present("section.courses-tab li button"))
        assert _text(driver, "section.courses-tab span.course-version") == "Version 2"

        panel_window = driver.current_window_handle
        opened_before = set(driver.window_handles)
        _click(driver, "section.courses-tab li button")
        wait.until(present("main.course-page"))
        assert _text(driver, "main.course-page h1") == "Algebra"
        assert _text(driver, "main.course-page p.course-version") == "Version 2"
        # Open course also opens the course URL in a new tab; close that tab and return to the panel.
        for handle in set(driver.window_handles) - opened_before:
            driver.switch_to.window(handle)
            driver.close()
        driver.switch_to.window(panel_window)
    assert "GET /v1/courses" in received
    assert f"POST /v1/courses/{COURSE_ID}/open" in received
