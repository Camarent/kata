"""Browser flow: the content script answers a scan on a lesson page, and the side panel page renders.

Runs once per browser (browser_name param, see conftest.py). A missing browser, driver or selenium
skips that case; nothing here reaches beyond 127.0.0.1.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from browser.conftest import EXTENSION_DIST, FIREFOX_EXTENSION_UUID

LESSON_PATH = "/lesson.html"
LESSON_TEXT = "Sample lesson page for browser tests."
PANEL_PATH = "/sidepanel.html"
# The sign-in form is the panel's first view with no session: pairing code input (extension/src/sidepanel.ts:63).
PANEL_INPUT_SELECTOR = 'form.signin input[name="code"]'
# scanBlocks sets this attribute on each block element it answers for (extension/src/scanner.ts:104).
BLOCK_SELECTOR = "[data-kata-block]"
PANEL_WAIT_SECONDS = 10
# Asks the content script of every tab except the panel's own tab for a scan (extension/src/content.ts:26).
# The last argument of execute_async_script is the callback; a tab without the content script is skipped.
SCAN_OTHER_TABS = """
const done = arguments[arguments.length - 1];
(async () => {
  const self = await chrome.tabs.getCurrent();
  const tabs = await chrome.tabs.query({});
  const answers = [];
  for (const tab of tabs) {
    if (tab.id === self.id) continue;
    try {
      const reply = await chrome.tabs.sendMessage(tab.id, { type: "scan" });
      if (reply && reply.blocks) answers.push(reply);
    } catch (err) {
      // No content script in this tab.
    }
  }
  return answers;
})().then(done, (err) => done({ error: String(err) }));
"""


def _chrome_extension_id(path: Path) -> str:
    """The id Chrome gives an unpacked extension: first 32 hex digits of sha256(path), a-p."""
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:32]
    return "".join(chr(ord("a") + int(digit, 16)) for digit in digest)


def _panel_url(browser_name: str) -> str:
    if browser_name == "firefox":
        return f"moz-extension://{FIREFOX_EXTENSION_UUID}{PANEL_PATH}"
    return f"chrome-extension://{_chrome_extension_id(EXTENSION_DIST / 'chrome')}{PANEL_PATH}"


def test_panel_flow(browser_name: str, driver: Any, page_server: str) -> None:
    webdriver_support = pytest.importorskip("selenium.webdriver.support.ui")
    driver.get(f"{page_server}{LESSON_PATH}")
    lesson_handle = driver.current_window_handle

    driver.switch_to.new_window("tab")
    panel_handle = driver.current_window_handle
    driver.get(_panel_url(browser_name))

    answers = driver.execute_async_script(SCAN_OTHER_TABS)
    assert not (isinstance(answers, dict) and "error" in answers), answers
    texts = [block["text"] for answer in answers for block in answer["blocks"]]
    assert any(LESSON_TEXT in text for text in texts), answers

    driver.switch_to.window(lesson_handle)
    marked = driver.execute_script(f"return document.querySelectorAll('{BLOCK_SELECTOR}').length")
    assert marked > 0

    driver.switch_to.window(panel_handle)
    wait = webdriver_support.WebDriverWait(driver, PANEL_WAIT_SECONDS)
    wait.until(lambda d: d.execute_script(f"return !!document.querySelector('{PANEL_INPUT_SELECTOR}')"))
