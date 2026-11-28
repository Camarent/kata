"""Browser proof: hovering a page image shows its pin, and hovering the pin opens the image menu.

The built content.js runs on sample.html (no stub core, no harness bundle). Hovering the image
(`#pic`) shows the image pin (`.image-pin`, overlayHost.ts attachImageMenu); hovering the pin opens the
image menu (ui/overlay/imageMenu.ts) with its heading. Runs once per browser (browser_name param, see
conftest.py); a missing browser, driver or selenium skips that case, and nothing here reaches beyond
127.0.0.1.
"""

from __future__ import annotations

from typing import Any

SAMPLE_PATH = "/sample.html"
IMAGE_SELECTOR = "#pic"
PIN_SELECTOR = ".image-pin"
MENU_SELECTOR = ".image-pin-menu"
MENU_HEADER_SELECTOR = ".image-pin-menu h2"
# TEXT_IMAGE_PIN_MENU[3] in extension/src/ui/strings.ts (the menu heading).
MENU_HEADER_TEXT = "Concepts in this image"
WAIT_SECONDS = 10
EXISTS_SCRIPT = "return !!document.querySelector(arguments[0])"


def test_image_pin_opens_image_menu_on_hover(driver: Any, page_server: str) -> None:
    # The driver fixture skips first when selenium is missing, so these imports are reached only with it.
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait

    driver.get(f"{page_server}{SAMPLE_PATH}")
    wait = WebDriverWait(driver, WAIT_SECONDS)
    wait.until(lambda d: d.execute_script(EXISTS_SCRIPT, IMAGE_SELECTOR))

    # Hovering the image shows its pin; hovering the pin opens the menu under the image.
    image = driver.find_element("css selector", IMAGE_SELECTOR)
    ActionChains(driver).move_to_element(image).perform()
    wait.until(lambda d: d.execute_script(EXISTS_SCRIPT, PIN_SELECTOR))
    pin = driver.find_element("css selector", PIN_SELECTOR)
    ActionChains(driver).move_to_element(pin).perform()
    wait.until(lambda d: d.execute_script(EXISTS_SCRIPT, MENU_SELECTOR))
    header = driver.find_element("css selector", MENU_HEADER_SELECTOR).text
    assert header == MENU_HEADER_TEXT
