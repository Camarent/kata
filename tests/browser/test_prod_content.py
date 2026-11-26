"""Production browser test: the built content.js mounts the floating card on sample.html.

The `driver` fixture installs the built extension (extension/dist/<browser>/, which holds content.js).
Its manifest matches http pages, so the browser injects the built content.js into the sample page
served from tests/browser/pages on 127.0.0.1. No harness bundle is loaded here: the card must mount
from the production script alone. Runs once per browser (browser_name param, see conftest.py).
"""

from __future__ import annotations

from typing import Any

SAMPLE_PATH = "/sample.html"
# Root of the floating pin that content.js mounts (extension/src/ui/card/pin.ts: el("div", ..., "float")).
PIN_ROOT = ".float[data-screen]"
WAIT_SECONDS = 10


def test_prod_content_mounts_floating_card(driver: Any, page_server: str) -> None:
    # The driver fixture skips first when selenium is missing, so this import is reached only with it.
    from selenium.webdriver.support.ui import WebDriverWait

    driver.get(f"{page_server}{SAMPLE_PATH}")
    WebDriverWait(driver, WAIT_SECONDS).until(
        lambda d: d.execute_script("return !!document.querySelector(arguments[0])", PIN_ROOT)
    )
    assert driver.execute_script("return document.querySelector(arguments[0]).dataset.screen", PIN_ROOT) == "pin"
