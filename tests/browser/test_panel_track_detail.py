"""Browser proof: a track's detail Add source button opens the add-source form, and its Quiz button opens the quiz run.

Runs once per browser (browser_name param, see conftest.py). A missing browser, driver or selenium
skips that case; nothing here reaches beyond 127.0.0.1 (the stub core and the extension pages).
"""

from __future__ import annotations

from typing import Any

import pytest

from browser.panel_page import PANEL_WAIT_SECONDS, open_panel, panel_url
from browser.signed_in import grant_host_permission, seed_session
from browser.stub_core import stub_core

TRACK_ID = 1
STUB_TRACKS = {
    "items": [
        {
            "id": TRACK_ID,
            "name": "Alpha",
            "deadline": "2027-01-01",
            "priority": 0,
            "status": "active",
            "items": [],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ],
    "next_before_id": None,
}


def _click(driver: Any, selector: str) -> None:
    driver.execute_script(f"document.querySelector('{selector}').click()")


def test_panel_track_detail_add_source_and_quiz(browser_name: str, driver: Any) -> None:
    webdriver_support = pytest.importorskip("selenium.webdriver.support.ui")
    open_panel(driver, browser_name)
    received: list[str] = []
    routes: dict[str, Any] = {"/v1/tracks": STUB_TRACKS}
    with stub_core(routes, received) as base_url:
        seed_session(driver, base_url)
        grant_host_permission(driver, base_url)
        driver.get(panel_url(browser_name))
        wait = webdriver_support.WebDriverWait(driver, PANEL_WAIT_SECONDS)

        def present(selector: str) -> Any:
            return lambda d: d.execute_script(f"return !!document.querySelector('{selector}')")

        wait.until(present("nav.tabs"))
        _click(driver, "nav.tabs button.tab-tracks")
        wait.until(present("section.tracks-tab button.open-track"))
        _click(driver, "section.tracks-tab button.open-track")
        wait.until(present("section.track-detail button.add-source"))

        _click(driver, "section.track-detail button.add-source")
        wait.until(present("section.source-add button.add-source"))
        assert not driver.execute_script("return !!document.querySelector('section.track-detail')")
        _click(driver, "section.source-add button.cancel")
        wait.until(present("section.track-detail button.quiz"))

        _click(driver, "section.track-detail button.quiz")
        wait.until(present("section.quiz-run button.stop"))
        assert not driver.execute_script("return !!document.querySelector('section.track-detail')")
        _click(driver, "section.quiz-run button.stop")
        wait.until(present("section.track-detail button.quiz"))
    assert "GET /v1/tracks" in received
