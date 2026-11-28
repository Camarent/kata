"""Browser proof: the Tracks tab New track form sends the track on Save, and the new row shows in the list.

Runs once per browser (browser_name param, see conftest.py). A missing browser, driver or selenium
skips that case; nothing here reaches beyond 127.0.0.1 (the stub core and the extension pages).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from browser.panel_page import PANEL_WAIT_SECONDS, open_panel, panel_url
from browser.signed_in import grant_host_permission, seed_session
from browser.stub_core import stub_core

ALPHA = {
    "id": 1,
    "name": "Alpha",
    "deadline": "2027-01-01",
    "priority": 0,
    "status": "active",
    "items": [],
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}
BETA = {**ALPHA, "id": 2, "name": "Beta", "deadline": "2027-03-01"}


def _click(driver: Any, selector: str) -> None:
    driver.execute_script(f"document.querySelector('{selector}').click()")


def test_panel_track_create_save_sends_track_and_shows_row(browser_name: str, driver: Any) -> None:
    webdriver_support = pytest.importorskip("selenium.webdriver.support.ui")
    open_panel(driver, browser_name)
    received: list[str] = []
    bodies: list[str] = []

    def tracks() -> dict[str, Any]:
        # The list shows Beta once the stub has taken the POST; before that only Alpha.
        items = [ALPHA, BETA] if "POST /v1/tracks" in received else [ALPHA]
        return {"items": items, "next_before_id": None}

    routes: dict[str, Any] = {"/v1/tracks": tracks}
    with stub_core(routes, received, bodies) as base_url:
        seed_session(driver, base_url)
        grant_host_permission(driver, base_url)
        driver.get(panel_url(browser_name))
        wait = webdriver_support.WebDriverWait(driver, PANEL_WAIT_SECONDS)

        def present(selector: str) -> Any:
            return lambda d: d.execute_script(f"return !!document.querySelector('{selector}')")

        def tab_text_has(text: str) -> Any:
            script = (
                "const t = document.querySelector('section.tracks-tab');"
                " return !!t && t.textContent.includes(arguments[0]);"
            )
            return lambda d: d.execute_script(script, text)

        wait.until(present("nav.tabs"))
        _click(driver, "nav.tabs button.tab-tracks")
        # The list load redraws the tab; wait for it to finish before New track, or the form would be replaced.
        wait.until(present("section.tracks-tab[data-state=ready] button.new-track"))
        _click(driver, "section.tracks-tab button.new-track")
        wait.until(present("form.track-create"))

        driver.execute_script(
            "const f = document.querySelector('form.track-create');"
            "f.querySelector('input[name=name]').value = 'Beta';"
            "f.querySelector('input[name=deadline]').value = '2027-03-01';"
        )
        _click(driver, "form.track-create button[type=submit]")
        wait.until(tab_text_has("Beta"))
        assert not driver.execute_script("return !!document.querySelector('form.track-create')")
    assert "POST /v1/tracks" in received
    assert json.loads(bodies[received.index("POST /v1/tracks")]) == {"name": "Beta", "deadline": "2027-03-01"}
