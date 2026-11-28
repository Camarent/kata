"""Browser proof: hovering a scanned block opens the block menu with its concept rows, and Ignore sends the request.

The built extension runs against the stub core: the classification and the extraction job answer one
concept, "kata", for the only block. The card's Scan button starts the scan; hovering the block then
shows the block menu (ui/overlay/blockMenu.ts) with the concept row "Kata" and its Delete / Ignore
buttons. Ignore asks for confirmation, then after the undo window sends `PUT /concepts/7/ignore` to the
stub. Runs once per browser (browser_name param, see conftest.py); a missing browser, driver or
selenium skips that case, and nothing here reaches beyond 127.0.0.1.
"""

from __future__ import annotations

from typing import Any

from browser.panel_page import open_panel
from browser.signed_in import grant_host_permission, seed_session
from browser.stub_core import stub_core

SAMPLE_PATH = "/hover.html"
WAIT_SECONDS = 10
PIN_BUTTON_SELECTOR = ".float .pinbtn"
SCAN_BUTTON_SELECTOR = ".card-host button.scan"
HL_SELECTOR = "span.hl"
BLOCK_SELECTOR = "[data-kata-block]"
MENU_SELECTOR = ".block-menu"
CONCEPT_ROW_SELECTOR = ".block-menu .concept-row"
IGNORE_SELECTOR = ".block-menu .concept-ignore"
CONFIRM_SELECTOR = ".block-menu .concept-actions .confirm-yes"
CONCEPT_LABEL = "Kata"
CONCEPT_ID = 7
IGNORE_REQUEST = f"PUT /concepts/{CONCEPT_ID}/ignore"
BLOCK_IDS = ["b0"]
# Only the collapsed pin icon opens the main card (content.ts); the expanded mascot (in .pinwrap) opens
# the undo mini-menu. The first matching button that is not in .pinwrap is the collapsed icon.
CLICK_COLLAPSED_PIN_SCRIPT = """
const button = [...document.querySelectorAll(arguments[0])].find((el) => !el.closest(".pinwrap"));
if (!button) return false;
button.click();
return true;
"""
CLICK_SCRIPT = """
const button = document.querySelector(arguments[0]);
if (!button) return false;
button.click();
return true;
"""
EXISTS_SCRIPT = "return !!document.querySelector(arguments[0])"


def open_card(driver: Any, pin_selector: str) -> bool:
    """Click the collapsed pin icon, then report whether the card's Scan button is there."""
    driver.execute_script(CLICK_COLLAPSED_PIN_SCRIPT, pin_selector)
    return bool(driver.execute_script(EXISTS_SCRIPT, SCAN_BUTTON_SELECTOR))


def _concept() -> dict[str, Any]:
    return {
        "word": "kata",
        "conceptId": CONCEPT_ID,
        "label": CONCEPT_LABEL,
        "definition": "a practised form",
        "state": "new",
        "candidates": [],
    }


def _stub_routes() -> dict[str, Any]:
    blocks = [{"blockId": block_id, "concepts": [_concept()]} for block_id in BLOCK_IDS]
    done = {"status": "done", "topic": {"id": 3, "category": "net", "label": "tcp"}, "known": False}
    # The concept calls use unprefixed paths (coreClientConcepts.ts, coreClient.ts enqueue/jobStatus)
    # and the core answers snake_case JSON (getClassification reads area_id and topic_id).
    return {
        "/scan/classification": {"area_id": 2, "topic_id": 3, "area": "net", "topic": "tcp", "candidates": []},
        "/jobs": {"id": 1},
        "/jobs/1": {**done, "output": {"blocks": blocks}},
        f"/concepts/{CONCEPT_ID}/ignore": {},
    }


def test_block_menu_opens_on_hover_and_ignore_sends_request(browser_name: str, driver: Any, page_server: str) -> None:
    # The driver fixture skips first when selenium is missing, so these imports are reached only with it.
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait

    # The extension APIs (chrome.storage) exist only on an extension page: open the panel first, as
    # test_signed_in_panel.py does, then seed the session from it.
    open_panel(driver, browser_name)
    received: list[str] = []
    with stub_core(_stub_routes(), received) as base_url:
        seed_session(driver, base_url)
        grant_host_permission(driver, base_url)
        driver.get(f"{page_server}{SAMPLE_PATH}")
        wait = WebDriverWait(driver, WAIT_SECONDS)
        # The collapsed pin icon opens the main card (content.ts), then its Scan button starts the scan.
        wait.until(lambda d: open_card(d, PIN_BUTTON_SELECTOR))
        wait.until(lambda d: d.execute_script(CLICK_SCRIPT, SCAN_BUTTON_SELECTOR))
        wait.until(lambda d: d.execute_script(EXISTS_SCRIPT, HL_SELECTOR))

        block = driver.find_element("css selector", BLOCK_SELECTOR)
        ActionChains(driver).move_to_element(block).perform()
        wait.until(lambda d: d.execute_script(EXISTS_SCRIPT, MENU_SELECTOR))
        wait.until(lambda d: d.execute_script(EXISTS_SCRIPT, CONCEPT_ROW_SELECTOR))
        row_text = driver.find_element("css selector", CONCEPT_ROW_SELECTOR).text
        assert CONCEPT_LABEL in row_text

        # Ignore asks for confirmation; the confirm button sends the request after the undo window.
        wait.until(lambda d: d.execute_script(CLICK_SCRIPT, IGNORE_SELECTOR))
        wait.until(lambda d: d.execute_script(CLICK_SCRIPT, CONFIRM_SELECTOR))
        wait.until(lambda d: IGNORE_REQUEST in received)
