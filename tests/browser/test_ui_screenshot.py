"""Browser screenshot: the panel's sign-in form is checked at panel width and at narrow width.

Runs once per browser (browser_name param, see conftest.py). The panel is opened on its sign-in view at each
width, and a screenshot of the window is taken. The PNG must start with the PNG signature and have a
non-zero IHDR width and height. The sign-in form must
sit inside the viewport horizontally and be at most 360px wide. The panel's own CSS width is not measured here.
The screenshot bytes are kept in memory only: nothing is written to disk.
The test does not compare screenshot width with window width.
"""

from __future__ import annotations

import struct
from typing import Any

import pytest

from browser.panel_page import open_panel

# Window width of the panel case; the sign-in form must not be wider than this.
PANEL_WIDTH = 360
# A narrow phone-like width below the panel width.
NARROW_WIDTH = 320
WINDOW_HEIGHT = 800
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Byte offset of the IHDR width field: 8-byte signature, 4-byte length, 4-byte type.
PNG_WIDTH_OFFSET = 16
# The element measured is the sign-in form on the panel's first view.
PANEL_BOX_JS = """
const form = document.querySelector('form.signin');
if (!form) return null;
const box = form.getBoundingClientRect();
return {
  left: box.left, right: box.right, width: box.width, height: box.height, innerWidth: window.innerWidth,
};
"""


def png_size(data: bytes) -> tuple[int, int]:
    """Width and height from the PNG IHDR chunk; fails the test when the bytes are not a PNG."""
    assert data.startswith(PNG_SIGNATURE), f"not a PNG: {data[:8]!r}"
    width, height = struct.unpack(">II", data[PNG_WIDTH_OFFSET : PNG_WIDTH_OFFSET + 8])
    return width, height


@pytest.mark.parametrize("width", [PANEL_WIDTH, NARROW_WIDTH])
def test_panel_screenshot_at_panel_and_narrow_width(browser_name: str, driver: Any, width: int) -> None:
    driver.set_window_size(width, WINDOW_HEIGHT)
    open_panel(driver, browser_name)
    box = driver.execute_script(PANEL_BOX_JS)
    assert box is not None, "no sign-in form on the panel view"
    assert box["height"] > 0, box
    # Compare with the viewport (innerWidth), not the requested window width.
    assert box["left"] >= 0 and box["right"] <= box["innerWidth"], f"width {width}px: panel box {box}"
    # The sign-in form is at most 360px wide and within the viewport.
    assert box["width"] <= min(PANEL_WIDTH, box["innerWidth"]), f"width {width}px: panel box {box}"
    shot_width, shot_height = png_size(driver.get_screenshot_as_png())
    assert shot_width > 0 and shot_height > 0, f"width {width}px: empty screenshot {shot_width}x{shot_height}"
