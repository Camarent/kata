"""Browser proof: the section quiz pin shows on the scanned page and its action asks the core for the mini quiz.

The built extension runs against the stub core: the classification and the extraction job answer one
"new" concept, "kata", for the only block, and `GET /quiz/mini` answers one question. The card's Scan
button starts the scan; the block's end is in view on the short sample page, so the section quiz pin
(ui/overlay/quizPin.ts, mounted by overlayHost.ts) shows "Quiz this section". Its button sends
`panel:miniQuiz`, which the background answers with `GET /quiz/mini` on the stub. Runs once per browser
(browser_name param, see conftest.py); a missing browser, driver or selenium skips that case, and nothing
here reaches beyond 127.0.0.1.
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
QUIZ_PIN_SELECTOR = ".quiz-pin"
QUIZ_PIN_BUTTON_SELECTOR = ".quiz-pin button"
QUIZ_PIN_LABEL = "Quiz this section"
MINI_QUIZ_REQUEST = "GET /quiz/mini"
CONCEPT_ID = 7
BLOCK_IDS = ["b0"]
# The first matching button that is not in .pinwrap is the collapsed pin icon (content.ts).
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
PIN_TEXT_SCRIPT = "const pin = document.querySelector(arguments[0]); return pin ? pin.textContent : ''"


def open_card(driver: Any) -> bool:
    """Click the collapsed pin icon, then report whether the card's Scan button is there."""
    driver.execute_script(CLICK_COLLAPSED_PIN_SCRIPT, PIN_BUTTON_SELECTOR)
    return bool(driver.execute_script(EXISTS_SCRIPT, SCAN_BUTTON_SELECTOR))


def _concept() -> dict[str, Any]:
    return {
        "word": "kata",
        "conceptId": CONCEPT_ID,
        "label": "Kata",
        "definition": "a practised form",
        "state": "new",
        "candidates": [],
    }


def _question() -> dict[str, Any]:
    return {
        "id": 1,
        "question": "What is a kata?",
        "choices": ["a practised form", "a bird", "a tool", "a town"],
        "source_url": "https://example.test/kata",
        "tier": 1,
        "licence": "CC-BY",
    }


def _stub_routes() -> dict[str, Any]:
    blocks = [{"blockId": block_id, "concepts": [_concept()]} for block_id in BLOCK_IDS]
    done = {"status": "done", "topic": {"id": 3, "category": "net", "label": "tcp"}, "known": False}
    # The unprefixed paths and the snake_case JSON match the core routes (see test_block_menu.py).
    return {
        "/scan/classification": {"area_id": 2, "topic_id": 3, "area": "net", "topic": "tcp", "candidates": []},
        "/jobs": {"id": 1},
        "/jobs/1": {**done, "output": {"blocks": blocks}},
        "/quiz/mini": [_question()],
    }


def test_quiz_pin_shows_and_its_action_requests_mini_quiz(browser_name: str, driver: Any, page_server: str) -> None:
    # The driver fixture skips first when selenium is missing, so these imports are reached only with it.
    from selenium.webdriver.support.ui import WebDriverWait

    # The extension APIs (chrome.storage) exist only on an extension page: open the panel first, as
    # test_block_menu.py does, then seed the session from it.
    open_panel(driver, browser_name)
    received: list[str] = []
    with stub_core(_stub_routes(), received) as base_url:
        seed_session(driver, base_url)
        grant_host_permission(driver, base_url)
        driver.get(f"{page_server}{SAMPLE_PATH}")
        wait = WebDriverWait(driver, WAIT_SECONDS)
        # The collapsed pin icon opens the main card, then its Scan button starts the scan.
        wait.until(lambda d: open_card(d))
        wait.until(lambda d: d.execute_script(CLICK_SCRIPT, SCAN_BUTTON_SELECTOR))
        wait.until(lambda d: d.execute_script(EXISTS_SCRIPT, HL_SELECTOR))

        # The section end is in view on the short page, so the pin shows. The pin renders its label
        # ("Quiz this section") and count, not question text, so the check is on the label.
        wait.until(lambda d: d.execute_script(EXISTS_SCRIPT, QUIZ_PIN_SELECTOR))
        pin_text = driver.execute_script(PIN_TEXT_SCRIPT, QUIZ_PIN_SELECTOR)
        assert QUIZ_PIN_LABEL in pin_text

        # The pin's action asks the background for the mini quiz; the stub core gets the request.
        wait.until(lambda d: d.execute_script(CLICK_SCRIPT, QUIZ_PIN_BUTTON_SELECTOR))
        wait.until(lambda d: MINI_QUIZ_REQUEST in received)
