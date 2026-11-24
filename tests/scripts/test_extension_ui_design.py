"""docs/design/extension-ui.md and its mockups: required parts present, no network, no private names."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
DESIGN = REPO_ROOT / "docs" / "design" / "extension-ui.md"
MOCKUP_DIR = REPO_ROOT / "docs" / "design" / "extension-ui"
PANEL = MOCKUP_DIR / "panel-states.html"
PAGE = MOCKUP_DIR / "lesson-page.html"
TOKENS = MOCKUP_DIR / "tokens.css"
BACKLOG = REPO_ROOT / "docs" / "backlog.md"
# Every mockup html and css file, so later mockups get the same checks at once.
FILES = (DESIGN, *sorted(MOCKUP_DIR.glob("*.html")), *sorted(MOCKUP_DIR.glob("*.css")))

# Heading prefixes the design doc must keep (section and screen titles).
DOC_HEADINGS = (
    "## 1. Principles for the UI",
    "## 2. Side panel: screens and states",
    "### 2.1 First run and sign-in",
    "### 2.2 Connected idle",
    "### 2.3 Scanning, with progress",
    "### 2.4 Partial result",
    "### 2.5 Results, grouped by topic",
    "### 2.6 Known and new marks",
    "### 2.7 \"I know this\"",
    "### 2.8 Review screen",
    "### 2.9 Courses",
    "### 2.10 Offline",
    "### 2.11 Sign-in expired",
    "### 2.12 Empty page",
    "### 2.13 Error",
    "### 2.14 Allowed sites",
    "### 2.15 Navigation map",
    "### 2.16 Settings page",
    "### 2.17 Auto-scan this site",
    "## 3. The page: highlights and detail",
    "### 3.1 Long text split",
    "## 4. Scan trigger",
    "## 5. Keyboard and focus order",
    "## 6. Accessibility rules",
    "## 7. Themes",
    "## 8. Open points for the owner",
)

# Accessibility terms the design must state in plain words.
DOC_TERMS = (
    "contrast", "focus order", "reduced motion", "Scan this page",
    "Learning", "Known by course", "Exam pages",
    "extension-ui/block-states.html", "extension-ui/long-lesson.html",
)

# Lesson mark classes the tokens must define (labels, not colour alone).
TOKEN_CLASSES = (".mark-known", ".mark-learning", ".mark-new", ".mark-untagged")

# Ids the panel mockup must keep; the auto-scan toggle is the switch for 2.17.
PANEL_IDS = ("auto-scan-toggle",)

# Every side panel state has a section with this id in panel-states.html.
STATE_IDS = (
    "first-run", "sign-in", "idle", "scanning", "partial", "results-grouped",
    "i-know-this", "review", "courses-list", "courses-create", "courses-delete",
    "courses-open", "offline", "auth-lost", "empty-page", "error",
)

NETWORK_PATTERNS = (
    ("http(s) URL", re.compile(r"https?://", re.IGNORECASE)),
    ("script src", re.compile(r"<script[^>]*\bsrc\s*=", re.IGNORECASE)),
    ("protocol-relative link", re.compile(r"""(?:src|href|url)\s*[=(]\s*["']?//""", re.IGNORECASE)),
    ("hostname", re.compile(r"\b[a-z0-9-]+\.(?:lan|local|internal|home|corp|ts\.net)\b|\blocalhost\b", re.IGNORECASE)),
    ("IPv4 address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
)

# Infrastructure and personal names that must not appear in tracked design files.
PRIVATE_WORDS = ("claude-safe", "proxmox", "tailnet", "ollama", "modelctl", "wt.py", "/home/", "/root/")


def _violations(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    found = [f"{path.name}: {label}" for label, pattern in NETWORK_PATTERNS if pattern.search(text)]
    lowered = text.lower()
    found += [f"{path.name}: private name {word!r}" for word in PRIVATE_WORDS if word in lowered]
    return found


def test_design_doc_has_required_headings_and_terms() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    lines = text.splitlines()
    for heading in DOC_HEADINGS:
        assert any(line.startswith(heading) for line in lines), heading
    for term in DOC_TERMS:
        assert term.lower() in text.lower(), term


def test_panel_mockup_has_every_state_id() -> None:
    html = PANEL.read_text(encoding="utf-8")
    for state in STATE_IDS:
        assert f'id="{state}"' in html, state
    for element_id in PANEL_IDS:
        assert f'id="{element_id}"' in html, element_id


def test_tokens_define_every_mark_class() -> None:
    css = TOKENS.read_text(encoding="utf-8")
    for css_class in TOKEN_CLASSES:
        assert re.search(re.escape(css_class) + r"\s*[{,:]", css), css_class


def test_backlog_has_exam_pages_entry() -> None:
    backlog = BACKLOG.read_text(encoding="utf-8")
    assert any(line.startswith("## Exam pages") for line in backlog.splitlines()), "Exam pages"


def test_design_files_have_no_network_or_private_names() -> None:
    for path in FILES:
        assert _violations(path) == [], path.name


def test_mutation_injected_http_link_fails_checker(tmp_path) -> None:
    target = tmp_path / "lesson-page.html"
    target.write_text(
        PAGE.read_text(encoding="utf-8") + '\n<a href="http://example.org/x">x</a>\n',
        encoding="utf-8",
    )
    found = _violations(target)
    assert any("http(s) URL" in item for item in found), found
