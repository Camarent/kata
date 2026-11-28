"""Browser proof: the Settings tab opens the exam entry, saving imports the result and the result screen shows its score.

Runs once per browser (browser_name param, see conftest.py). A missing browser, driver or selenium
skips that case; nothing here reaches beyond 127.0.0.1 (the stub core and the extension pages).
"""

from __future__ import annotations

from typing import Any

import pytest

from browser.panel_page import PANEL_WAIT_SECONDS, open_panel, panel_url
from browser.signed_in import grant_host_permission, seed_session
from browser.stub_core import stub_core

STUB_RESULT = {
    "id": 7,
    "origin": "page",
    "taken_at": "2026-01-01T00:00:00Z",
    "passed": True,
    "score": 0.85,
    "status": "pending",
    "concepts": [],
}
FILL_ENTRY = """
const entry = document.querySelector('section.exam-entry');
entry.querySelector('input[name="date"]').value = '2026-01-01';
entry.querySelector('input[name="score"]').value = '85';
entry.querySelector('button.save-result').click();
"""


def _click(driver: Any, selector: str) -> None:
    driver.execute_script(f"document.querySelector('{selector}').click()")


def test_panel_exam_result_screen(browser_name: str, driver: Any) -> None:
    webdriver_support = pytest.importorskip("selenium.webdriver.support.ui")
    open_panel(driver, browser_name)
    received: list[str] = []
    with stub_core({"/exams/import": STUB_RESULT}, received) as base_url:
        seed_session(driver, base_url)
        grant_host_permission(driver, base_url)
        driver.get(panel_url(browser_name))
        wait = webdriver_support.WebDriverWait(driver, PANEL_WAIT_SECONDS)

        def present(selector: str) -> Any:
            return lambda d: d.execute_script(f"return !!document.querySelector('{selector}')")

        wait.until(present("nav.tabs"))
        _click(driver, "nav.tabs button.tab-settings")
        wait.until(present("button.open-exam-entry"))
        _click(driver, "button.open-exam-entry")
        wait.until(present("section.exam-entry"))
        driver.execute_script(FILL_ENTRY)
        wait.until(present("section.exam-result"))
        score = driver.execute_script("return document.querySelector('p.exam-score').textContent")
        assert "85%" in score
    assert "POST /exams/import" in received
