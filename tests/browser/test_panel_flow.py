"""Browser flow: the content script answers a scan on a lesson page, and the side panel page renders.

Runs once per browser (browser_name param, see conftest.py). A missing browser, driver or selenium
skips that case; nothing here reaches beyond 127.0.0.1.
"""

from __future__ import annotations

from typing import Any

import pytest

from browser.panel_page import PANEL_INPUT_SELECTOR, PANEL_WAIT_SECONDS, panel_url

LESSON_PATH = "/lesson.html"
LESSON_TEXT = "Sample lesson page for browser tests."
# scanBlocks sets BLOCK_ATTR (data-kata-block) on each block element it answers for (extension/src/scanner.ts).
BLOCK_SELECTOR = "[data-kata-block]"
# Asks the content script of every tab except the panel's own tab for a scan (handleContentMessage, extension/src/content.ts).
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


def test_panel_flow(browser_name: str, driver: Any, page_server: str) -> None:
    webdriver_support = pytest.importorskip("selenium.webdriver.support.ui")
    driver.get(f"{page_server}{LESSON_PATH}")
    lesson_handle = driver.current_window_handle

    driver.switch_to.new_window("tab")
    panel_handle = driver.current_window_handle
    driver.get(panel_url(browser_name))

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
