"""Browser layout: the side panel fits its width, scan rows clamp to two lines, touch targets are 36px.

Runs once per browser (browser_name param, see conftest.py). The panel is opened on its sign-in view,
the first view with no session. The window is resized to the panel width and to a narrow width; the
page must not scroll sideways at either. Scan rows use the `clamp2` class (extension/src/ui/panelCss.ts);
a row with a long label, built like the scan view, is injected and must render at most two lines tall. Every visible
button and link must measure at least 36px by 36px (the touch target size in panelCss.ts).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from browser.panel_page import open_panel

# Panel width: the `.panel` rule sets width 360px (extension/src/ui/panelCss.ts).
PANEL_WIDTH = 360
# A narrow phone-like width below the panel width.
NARROW_WIDTH = 320
WINDOW_HEIGHT = 800
MIN_TARGET_PX = 36
# Sub-pixel rounding allowance for the two-line height check.
HEIGHT_TOLERANCE_PX = 1
# Injected scan row: a long label that must be clamped, measured against a one-line probe.
LONG_LABEL = " ".join(["scanned-concept-with-a-very-long-name"] * 12)
INJECT_ROW_JS = """
// Same markup as the scan view (extension/src/ui/panel/scanResults.ts): ul.rows > li.rrow > span.nm.clamp2.
// arguments[1] is the label span class list, read from scanResults.ts by the test.
const labelClass = arguments[1];
const list = document.createElement('ul');
list.id = 'layout-rows';
list.className = 'rows';
function addRow(label, cls) {
  const item = document.createElement('li');
  item.className = 'rrow';
  const nm = document.createElement('span');
  nm.className = cls;
  nm.textContent = label;
  const badge = document.createElement('span');
  badge.className = 'badge sg new';
  badge.textContent = 'New';
  item.append(nm, badge);
  list.append(item);
  return nm;
}
const host = document.querySelector('.panel') || document.body;
host.append(list);
const probe = addRow('Line', 'nm');
const row = addRow(arguments[0], labelClass);
return {
  oneLine: probe.getBoundingClientRect().height,
  twoLineMax: row.getBoundingClientRect().height,
};
"""
REMOVE_ROW_JS = """
document.getElementById('layout-rows')?.remove();
"""
# The scan view builds each label as `el("span", row.label, "nm clamp2")`; the test reads that class list
# from the source, so dropping `clamp2` there turns the test red.
SCAN_RESULTS_TS = Path(__file__).resolve().parents[2] / "extension/src/ui/panel/scanResults.ts"
LABEL_CLASS_RE = re.compile(r'el\("span", row\.label, "([^"]+)"\)')


def scan_label_class() -> str:
    match = LABEL_CLASS_RE.search(SCAN_RESULTS_TS.read_text())
    assert match, f"scan row label span not found in {SCAN_RESULTS_TS}"
    return match.group(1)


# Sideways scroll: the document is wider than its viewport.
SCROLL_JS = """
const root = document.documentElement;
return { scrollWidth: root.scrollWidth, clientWidth: root.clientWidth };
"""
# Visible buttons and links with their measured size. Hidden elements have an empty box and are left out.
TARGETS_JS = """
const out = [];
for (const el of document.querySelectorAll('button, a[href]')) {
  const box = el.getBoundingClientRect();
  if (box.width === 0 && box.height === 0) continue;
  out.push({ label: (el.textContent || el.getAttribute('aria-label') || el.tagName).trim(), width: box.width, height: box.height });
}
return out;
"""


@pytest.mark.parametrize("width", [PANEL_WIDTH, NARROW_WIDTH])
def test_panel_does_not_scroll_sideways(browser_name: str, driver: Any, width: int) -> None:
    driver.set_window_size(width, WINDOW_HEIGHT)
    open_panel(driver, browser_name)
    scroll = driver.execute_script(SCROLL_JS)
    assert scroll["scrollWidth"] <= scroll["clientWidth"], f"width {width}px: {scroll}"


def test_scan_rows_clamp_to_two_lines(browser_name: str, driver: Any) -> None:
    driver.set_window_size(PANEL_WIDTH, WINDOW_HEIGHT)
    open_panel(driver, browser_name)
    heights = driver.execute_script(INJECT_ROW_JS, LONG_LABEL, scan_label_class())
    try:
        assert heights["twoLineMax"] <= 2 * heights["oneLine"] + HEIGHT_TOLERANCE_PX, heights
    finally:
        driver.execute_script(REMOVE_ROW_JS)


def test_touch_targets_are_36px(browser_name: str, driver: Any) -> None:
    driver.set_window_size(PANEL_WIDTH, WINDOW_HEIGHT)
    open_panel(driver, browser_name)
    targets = driver.execute_script(TARGETS_JS)
    assert targets, "no visible button or link on the sign-in view"
    small = [t for t in targets if t["width"] < MIN_TARGET_PX or t["height"] < MIN_TARGET_PX]
    assert not small, small
