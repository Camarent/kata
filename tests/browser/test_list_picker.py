"""Browser proof: the block menu's "Add all to list" opens the list picker with the stub's lists, and a pick sends the add.

The built extension runs against the stub core: the classification and the extraction job answer one
concept, "kata", for the only block, and the stub holds two lists. Hovering the scanned block opens the
block menu (ui/overlay/blockMenu.ts); its "Add all to list" button swaps the menu body for the list picker
(ui/overlay/listPicker.ts), which must show both list names. Picking "Networking basics" sends
`POST /v1/lists/1/concepts` to the stub. Runs once per browser (browser_name param, see conftest.py); a
missing browser, driver or selenium skips that case, and nothing here reaches beyond 127.0.0.1.
"""

from __future__ import annotations

import json
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
ADD_ALL_SELECTOR = ".block-menu .block-add-list"
PICKER_SELECTOR = ".block-menu .list-picker"
PICKER_BUTTON_SELECTOR = ".list-picker button"
CONCEPT_ID = 7
LIST_ID = 1
LIST_NAMES = ["Networking basics", "Reading"]
ADD_REQUEST = f"POST /v1/lists/{LIST_ID}/concepts"
# The collapsed pin icon opens the main card (content.ts); the expanded mascot is inside .pinwrap.
CLICK_COLLAPSED_PIN_SCRIPT = """
const button = [...document.querySelectorAll(arguments[0])].find((el) => !el.closest(".pinwrap"));
if (!button) return false;
button.click();
return true;
"""
CLICK_SCRIPT = """
const button = [...document.querySelectorAll(arguments[0])].find((el) => el.textContent === arguments[1]);
if (!button) return false;
button.click();
return true;
"""
CLICK_FIRST_SCRIPT = """
const button = document.querySelector(arguments[0]);
if (!button) return false;
button.click();
return true;
"""
PICKER_TEXTS_SCRIPT = "return [...document.querySelectorAll(arguments[0])].map((el) => el.textContent)"
EXISTS_SCRIPT = "return !!document.querySelector(arguments[0])"


def open_card(driver: Any, pin_selector: str) -> bool:
    """Click the collapsed pin icon, then report whether the card's Scan button is there."""
    driver.execute_script(CLICK_COLLAPSED_PIN_SCRIPT, pin_selector)
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


def _stub_routes() -> dict[str, Any]:
    blocks = [{"blockId": "b0", "concepts": [_concept()]}]
    done = {"status": "done", "topic": {"id": 3, "category": "net", "label": "tcp"}, "known": False}
    lists = [
        {"id": LIST_ID, "name": LIST_NAMES[0], "item_count": 2},
        {"id": 2, "name": LIST_NAMES[1], "item_count": 0},
    ]
    # The concept calls use unprefixed paths and the core answers snake_case JSON (see test_block_menu.py).
    return {
        "/scan/classification": {"area_id": 2, "topic_id": 3, "area": "net", "topic": "tcp", "candidates": []},
        "/jobs": {"id": 1},
        "/jobs/1": {**done, "output": {"blocks": blocks}},
        "/v1/lists": lists,
        f"/v1/lists/{LIST_ID}/concepts": {"added": 1},
    }


def test_list_picker_opens_from_block_menu_and_pick_sends_add(browser_name: str, driver: Any, page_server: str) -> None:
    # The driver fixture skips first when selenium is missing, so these imports are reached only with it.
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait

    # The extension APIs (chrome.storage) exist only on an extension page: open the panel first, as
    # test_block_menu.py does, then seed the session from it.
    open_panel(driver, browser_name)
    received: list[str] = []
    bodies: list[str] = []
    with stub_core(_stub_routes(), received, bodies) as base_url:
        seed_session(driver, base_url)
        grant_host_permission(driver, base_url)
        driver.get(f"{page_server}{SAMPLE_PATH}")
        wait = WebDriverWait(driver, WAIT_SECONDS)
        wait.until(lambda d: open_card(d, PIN_BUTTON_SELECTOR))
        wait.until(lambda d: d.execute_script(CLICK_FIRST_SCRIPT, SCAN_BUTTON_SELECTOR))
        wait.until(lambda d: d.execute_script(EXISTS_SCRIPT, HL_SELECTOR))

        block = driver.find_element("css selector", BLOCK_SELECTOR)
        ActionChains(driver).move_to_element(block).perform()
        wait.until(lambda d: d.execute_script(EXISTS_SCRIPT, ADD_ALL_SELECTOR))

        # The button opens the picker; both lists from the stub show as buttons.
        wait.until(lambda d: d.execute_script(CLICK_FIRST_SCRIPT, ADD_ALL_SELECTOR))
        wait.until(lambda d: d.execute_script(EXISTS_SCRIPT, PICKER_SELECTOR))
        wait.until(
            lambda d: all(name in d.execute_script(PICKER_TEXTS_SCRIPT, PICKER_BUTTON_SELECTOR) for name in LIST_NAMES)
        )

        # Picking the first list sends the add to that list's id.
        wait.until(lambda d: d.execute_script(CLICK_SCRIPT, PICKER_BUTTON_SELECTOR, LIST_NAMES[0]))
        wait.until(lambda _: ADD_REQUEST in received)
        assert ADD_REQUEST in received
        # The body carries the block's concept id.
        sent = json.loads(bodies[received.index(ADD_REQUEST)])
        assert sent["concept_ids"] == [CONCEPT_ID]
