"""Browser proof: the hover menu's "Not this meaning" opens the "Which one?" list and a pick reassigns.

The word "kata" has two candidate meanings besides its own concept (7). The hover menu lists its
"Not this meaning" button; the button opens the list with both candidate labels; picking one sends
the choice and then the reassign request to the stub core. Runs once per browser (browser_name param,
see conftest.py); a missing browser, driver or selenium skips that case, and nothing here reaches
beyond 127.0.0.1.
"""

from __future__ import annotations

from typing import Any

from browser.panel_page import open_panel
from browser.signed_in import grant_host_permission, seed_session
from browser.stub_core import stub_core
from browser.test_hover_menu import (
    BLOCK_IDS,
    CLICK_SCRIPT,
    HL_SELECTOR,
    MENU_SELECTOR,
    PIN_BUTTON_SELECTOR,
    SAMPLE_PATH,
    SCAN_BUTTON_SELECTOR,
    WAIT_SECONDS,
    open_card,
)

NOT_THIS_MEANING_SELECTOR = ".hl-hover-menu .not-this-meaning"
WHICH_ONE_SELECTOR = ".hl-which-one"
CANDIDATES = [{"conceptId": 8, "label": "Form"}, {"conceptId": 9, "label": "Exercise"}]
PICKED = CANDIDATES[0]
CHOOSE_PATH = "/scan/choice"
REASSIGN_PATH = "/scan/reassign"
CLICK_CANDIDATE_SCRIPT = """
const button = [...document.querySelectorAll(".hl-which-one .candidate")]
  .find((el) => el.textContent === arguments[0]);
if (!button) return false;
button.click();
return true;
"""


def _concept() -> dict[str, Any]:
    return {
        "word": "kata",
        "conceptId": 7,
        "label": "Kata",
        "definition": "a practised form",
        "state": "new",
        "candidates": CANDIDATES,
    }


def _stub_routes() -> dict[str, Any]:
    blocks = [{"blockId": block_id, "concepts": [_concept()]} for block_id in BLOCK_IDS]
    done = {"status": "done", "topic": {"id": 3, "category": "net", "label": "tcp"}, "known": False}
    # The concept calls use unprefixed paths (coreClientConcepts.ts, coreClient.ts enqueue/jobStatus).
    return {
        "/scan/classification": {"area_id": 2, "topic_id": 3, "area": "net", "topic": "tcp", "candidates": []},
        "/jobs": {"id": 1},
        "/jobs/1": {**done, "output": {"blocks": blocks}},
        CHOOSE_PATH: {"ok": True},
        REASSIGN_PATH: {"ok": True},
    }


def test_which_one_lists_candidates_and_reassigns(browser_name: str, driver: Any, page_server: str) -> None:
    # The driver fixture skips first when selenium is missing, so these imports are reached only with it.
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait

    open_panel(driver, browser_name)
    received: list[str] = []
    with stub_core(_stub_routes(), received) as base_url:
        seed_session(driver, base_url)
        grant_host_permission(driver, base_url)
        driver.get(f"{page_server}{SAMPLE_PATH}")
        wait = WebDriverWait(driver, WAIT_SECONDS)
        wait.until(lambda d: open_card(d, PIN_BUTTON_SELECTOR))
        wait.until(lambda d: d.execute_script(CLICK_SCRIPT, SCAN_BUTTON_SELECTOR))
        wait.until(lambda d: d.execute_script("return !!document.querySelector(arguments[0])", HL_SELECTOR))

        word = driver.find_element("css selector", HL_SELECTOR)
        ActionChains(driver).move_to_element(word).perform()
        wait.until(lambda d: d.execute_script("return !!document.querySelector(arguments[0])", MENU_SELECTOR))
        wait.until(lambda d: d.execute_script(CLICK_SCRIPT, NOT_THIS_MEANING_SELECTOR))

        wait.until(lambda d: d.execute_script("return !!document.querySelector(arguments[0])", WHICH_ONE_SELECTOR))
        list_text = driver.find_element("css selector", WHICH_ONE_SELECTOR).text
        for candidate in CANDIDATES:
            assert candidate["label"] in list_text

        wait.until(lambda d: d.execute_script(CLICK_CANDIDATE_SCRIPT, PICKED["label"]))
        wait.until(lambda _driver: any(line.endswith(REASSIGN_PATH) for line in received))
        assert f"POST {CHOOSE_PATH}" in received
        assert f"POST {REASSIGN_PATH}" in received
