"""docs/design/extension-ui/lesson-page.html: static mockup keeps its required parts. No network."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
PAGE = REPO_ROOT / "docs" / "design" / "extension-ui" / "lesson-page.html"


def _html() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_required_parts() -> None:
    html = _html()
    for needle in ("tokens.css", "Clear highlights", "360px", ":focus", "Known", "New", "Untagged"):
        assert needle in html, needle


def test_state_colours_applied() -> None:
    html = _html()
    for state in ("known", "new", "untagged"):
        assert re.search(rf"\.mark-{state}\s*\{{[^}}]*var\(--color-{state}\)", html), state


def test_no_network_refs_one_main() -> None:
    html = _html()
    assert not re.search(r"https?://|script src", html)
    assert html.count("<main") == 1
