"""Browser a11y: WCAG 2.x contrast of the side panel sign-in view in dark mode.

The panel is opened with prefers-color-scheme forced to each scheme under test (dark and light). For
each text element (labels, input text, button text, error text) the effective background is the
first non-transparent background up the ancestor chain, or the canvas colour when none is set. A
case skips, with the cause, when the browser does not report the forced scheme.
"""

from __future__ import annotations

from typing import Any

import pytest

from browser.panel_page import PANEL_WAIT_SECONDS, force_scheme, open_panel

# WCAG 2.x AA minimum contrast ratio for normal text.
MIN_RATIO = 4.5
# Error paragraph of the sign-in form, rendered by renderSignIn (extension/src/ui/panel/signin.ts).
ERROR_SELECTOR = "form.signin p.error"
SUBMIT_SELECTOR = 'form.signin button[type="submit"]'
# Name -> selector of the text elements checked. Each selector may match several elements.
TEXT_TARGETS = {
    "label": "form.signin label",
    "input text": 'form.signin input[name="code"]',
    "button text": SUBMIT_SELECTOR,
    "error text": ERROR_SELECTOR,
}
# Returns, per target, the text colour and the effective background as computed CSS colour strings.
# The canvas probe reads the colour the browser uses for an unstyled page in the current scheme.
COLOURS = """
const targets = arguments[0];
const probe = document.createElement('div');
probe.style.backgroundColor = 'Canvas';
document.body.append(probe);
const canvas = getComputedStyle(probe).backgroundColor;
probe.remove();
function alphaOf(css) {
  const parts = css.slice(css.indexOf('(') + 1, -1).split(',');
  return parts.length === 4 ? parseFloat(parts[3]) : 1;
}
function effectiveBackground(el) {
  for (let node = el; node; node = node.parentElement) {
    const bg = getComputedStyle(node).backgroundColor;
    if (alphaOf(bg) > 0) return bg;
  }
  return canvas;
}
const out = {};
for (const [name, selector] of Object.entries(targets)) {
  out[name] = [...document.querySelectorAll(selector)].map((el) => ({
    text: getComputedStyle(el).color,
    background: effectiveBackground(el),
  }));
}
const scheme = arguments[1];
return { scheme: matchMedia('(prefers-color-scheme: ' + scheme + ')').matches, targets: out };
"""


def _channel(value: float) -> float:
    """sRGB channel 0-255 to linear light, per WCAG 2.x."""
    srgb = value / 255
    return srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4


def _luminance(rgb: tuple[float, float, float]) -> float:
    red, green, blue = (_channel(c) for c in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    """WCAG 2.x contrast ratio of two sRGB colours (0-255 channels), from 1 to 21."""
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _parse_css_rgb(css: str) -> tuple[float, float, float]:
    """The rgb channels of a computed colour string such as 'rgb(1, 2, 3)' or 'rgba(1, 2, 3, 1)'."""
    parts = [float(part) for part in css[css.index("(") + 1 : -1].split(",")]
    return parts[0], parts[1], parts[2]


def test_contrast_ratio_known_pairs() -> None:
    assert contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    # #777 on white is 4.48:1, just under the AA minimum.
    assert contrast_ratio((0x77, 0x77, 0x77), (255, 255, 255)) == pytest.approx(4.48, abs=0.01)


@pytest.mark.parametrize("color_scheme", ["dark", "light"], indirect=True)
def test_panel_signin_theme_contrast(browser_name: str, color_scheme: str, driver: Any) -> None:
    webdriver_support = pytest.importorskip("selenium.webdriver.support.ui")
    force_scheme(driver, browser_name, color_scheme)
    open_panel(driver, browser_name)
    observed = driver.execute_script(COLOURS, TEXT_TARGETS, color_scheme)
    if not observed["scheme"]:
        pytest.skip(
            f"{browser_name} did not force prefers-color-scheme: {color_scheme} (matchMedia is false)"
        )

    driver.execute_script(f"document.querySelector('{SUBMIT_SELECTOR}').click()")
    wait = webdriver_support.WebDriverWait(driver, PANEL_WAIT_SECONDS)
    wait.until(
        lambda d: d.execute_script(
            f"return !!document.querySelector('{ERROR_SELECTOR}').textContent"
        )
    )
    observed = driver.execute_script(COLOURS, TEXT_TARGETS, color_scheme)

    failures = []
    for name, elements in observed["targets"].items():
        assert elements, f"no element matches {name}"
        for element in elements:
            ratio = contrast_ratio(
                _parse_css_rgb(element["text"]), _parse_css_rgb(element["background"])
            )
            if ratio < MIN_RATIO:
                failures.append(
                    f"{name}: {element['text']} on {element['background']} = {ratio:.2f}"
                )
    assert not failures, failures
