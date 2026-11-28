"""Browser proof: a scan on the page highlights its words and a hovered word opens the concept menu.

The built extension (content.js and the background) runs against the stub core: the classification
and the extraction job answer one concept, "kata", for every block. The card's Scan button starts the
scan; the highlighted word then shows the hover menu with the concept name and the New / Learning /
Known buttons. Runs once per browser (browser_name param, see conftest.py); a missing browser,
driver or selenium skips that case, and nothing here reaches beyond 127.0.0.1.
"""

from __future__ import annotations

from typing import Any

from browser.panel_page import open_panel
from browser.signed_in import grant_host_permission, seed_session
from browser.stub_core import stub_core

# A page whose only scanned block is the paragraph holding the word. sample.html puts its paragraph
# under a heading, and the scanner gives the heading the block id, so the word would not be wrapped.
SAMPLE_PATH = "/hover.html"
WAIT_SECONDS = 10
PIN_BUTTON_SELECTOR = ".float .pinbtn"
SCAN_BUTTON_SELECTOR = ".card-host button.scan"
HL_SELECTOR = "span.hl"
MENU_SELECTOR = ".hl-hover-menu"
CONCEPT_LABEL = "Kata"
STATE_LABELS = ("New", "Learning", "Known")
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


def open_card(driver: Any, pin_selector: str) -> bool:
    """Click the collapsed pin icon, then report whether the card's Scan button is there.

    The icon is in the DOM before its click listener is attached (content.ts, after mountPin), so an
    early click can miss. A repeated click is harmless: opening the card again redraws the same card.
    """
    driver.execute_script(CLICK_COLLAPSED_PIN_SCRIPT, pin_selector)
    return bool(driver.execute_script("return !!document.querySelector(arguments[0])", SCAN_BUTTON_SELECTOR))


def _concept() -> dict[str, Any]:
    return {
        "word": "kata",
        "conceptId": 7,
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
    }


def test_hover_menu_opens_on_highlighted_word(browser_name: str, driver: Any, page_server: str) -> None:
    # The driver fixture skips first when selenium is missing, so these imports are reached only with it.
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait

    # The extension APIs (chrome.storage) exist only on an extension page: open the panel first, as
    # test_signed_in_panel.py does, then seed the session from it.
    open_panel(driver, browser_name)
    with stub_core(_stub_routes()) as base_url:
        seed_session(driver, base_url)
        grant_host_permission(driver, base_url)
        driver.get(f"{page_server}{SAMPLE_PATH}")
        wait = WebDriverWait(driver, WAIT_SECONDS)
        # The collapsed pin icon opens the main card (content.ts), then its Scan button starts the scan.
        wait.until(lambda d: open_card(d, PIN_BUTTON_SELECTOR))
        wait.until(lambda d: d.execute_script(CLICK_SCRIPT, SCAN_BUTTON_SELECTOR))
        wait.until(lambda d: d.execute_script("return !!document.querySelector(arguments[0])", HL_SELECTOR))

        word = driver.find_element("css selector", HL_SELECTOR)
        ActionChains(driver).move_to_element(word).perform()
        wait.until(lambda d: d.execute_script("return !!document.querySelector(arguments[0])", MENU_SELECTOR))
        menu_text = driver.find_element("css selector", MENU_SELECTOR).text
        assert CONCEPT_LABEL in menu_text
        for label in STATE_LABELS:
            assert label in menu_text
