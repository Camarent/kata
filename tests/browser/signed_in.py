"""Seed a signed-in extension session for browser tests: the stub core base URL and a token.

The session lives in chrome.storage.local under SESSION_KEY (extension/src/tokenStore.ts). Writing it
from an extension page makes the panel boot signed in. The background can only fetch the stub when
the host permission for the stub origin is granted, so grant_host_permission asks for it too.
"""

from __future__ import annotations

from typing import Any

import pytest

SESSION_KEY = "kata.session"
TEST_TOKEN = "browser-test-token"
# Optional host permissions take the origin pattern form: scheme, host, port, then /*.
ORIGIN_PATTERN_SUFFIX = "/*"
SEED_TIMEOUT_SECONDS = 20
# Seeds the session from an extension page (the panel): the last argument is the callback.
SEED_SCRIPT = """
const done = arguments[arguments.length - 1];
const [key, session] = [arguments[0], arguments[1]];
chrome.storage.local.set({ [key]: session })
  .then(() => done({ ok: true }), (err) => done({ error: String(err) }));
"""
# permissions.request only runs inside a user gesture (Chrome and Firefox refuse a script-only call).
# So the page gets a button whose click asks for the origin; the test then clicks it with selenium,
# which sends a trusted input event, and reads the answer from the button's data-result attribute.
GRANT_BUTTON_ID = "kata-test-grant"
GRANT_WAIT_SECONDS = 10
INSTALL_GRANT_SCRIPT = """
const [id, pattern] = [arguments[0], arguments[1]];
const button = document.createElement("button");
button.id = id;
button.textContent = "grant host permission";
button.style.cssText = "position:fixed;top:0;left:0;z-index:2147483647;width:200px;height:40px;";
button.addEventListener("click", () => {
  chrome.permissions.request({ origins: [pattern] }).then(
    (granted) => { button.dataset.result = String(granted); },
    (err) => { button.dataset.result = "error: " + String(err); }
  );
});
document.body.appendChild(button);
"""
CONTAINS_SCRIPT = """
const done = arguments[arguments.length - 1];
chrome.permissions.contains({ origins: [arguments[0]] }).then(done, () => done(false));
"""
REMOVE_GRANT_SCRIPT = """
const button = document.getElementById(arguments[0]);
if (button) button.remove();
"""


def origin_pattern(base_url: str) -> str:
    """The optional host permission pattern for a base URL, e.g. http://127.0.0.1:4000/*."""
    return base_url.rstrip("/") + ORIGIN_PATTERN_SUFFIX


def seed_session(driver: Any, base_url: str, token: str = TEST_TOKEN) -> None:
    """Write the kata session (base URL and token) into extension storage from the current page."""
    reply = driver.execute_async_script(SEED_SCRIPT, SESSION_KEY, {"baseUrl": base_url, "token": token})
    if not isinstance(reply, dict) or "error" in reply:
        raise RuntimeError(f"seeding the session failed: {reply}")


def grant_host_permission(driver: Any, base_url: str) -> None:
    """Grant the host permission for the stub origin via a real click; raise when it is not granted.

    Runs on an extension page (the panel). The button is removed again when the grant is read.
    """
    webdriver_support = pytest.importorskip("selenium.webdriver.support.ui")
    exceptions = pytest.importorskip("selenium.common.exceptions")
    pattern = origin_pattern(base_url)
    # Chrome headless never answers permissions.request: conftest grants loopback in its manifest copy.
    already = driver.execute_async_script(CONTAINS_SCRIPT, pattern)
    if already is True:
        return
    driver.execute_script(INSTALL_GRANT_SCRIPT, GRANT_BUTTON_ID, pattern)
    try:
        driver.find_element("id", GRANT_BUTTON_ID).click()
        wait = webdriver_support.WebDriverWait(driver, GRANT_WAIT_SECONDS)
        try:
            result = wait.until(
                lambda d: d.execute_script(
                    "const b = document.getElementById(arguments[0]); return b && b.dataset.result;",
                    GRANT_BUTTON_ID,
                )
            )
        except exceptions.TimeoutException as err:
            raise RuntimeError(f"host permission {pattern}: no answer from the browser") from err
    finally:
        driver.execute_script(REMOVE_GRANT_SCRIPT, GRANT_BUTTON_ID)
    if result != "true":
        raise RuntimeError(f"host permission {pattern} not granted: {result}")
