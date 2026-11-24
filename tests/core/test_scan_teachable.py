"""Teachable-content check: a table of teachable and non-teachable page blocks.

Pure function, no database and no I/O. Decoys (a paragraph that mentions cookies or a port number)
must stay teachable.
"""

from __future__ import annotations

import pytest
from kata_core.scan.teachable import teachable

MIN_CHARS = 40

TEACHABLE: list[str] = [
    "A process is an instance of a running program with its own memory space and file descriptors.",
    "Photosynthesis converts light energy into chemical energy stored in glucose molecules.",
    "Binary search halves the remaining range each step, so finding an item takes logarithmic time.",
    "Mitochondria produce most of the cell's ATP through oxidative phosphorylation in the inner membrane.",
    # decoy: the word cookie in a teaching paragraph
    "HTTP cookies store session state in the browser so a server can recognise a returning visitor.",
    # decoy: a port number in a teaching paragraph
    "The default PostgreSQL port 5432 accepts client connections once the server has started.",
]

# (category, text): two examples per category
NON_TEACHABLE: list[tuple[str, str]] = [
    ("short", "Click here to read more."),
    ("short", "Next page"),
    ("phone", "Call our support desk on +44 20 7946 0958 today for help."),
    ("phone", "Reach us at (555) 123-4567 any weekday morning before noon."),
    ("email", "Write to sales@example-shop.com for a quote on bulk orders."),
    ("email", "Send feedback to john.doe@mail.example.org with your order number."),
    ("cookie", "We use cookies to improve your experience on this site."),
    ("cookie", "Click Accept all cookies or manage your cookie settings below."),
    ("nav", "Home | About us | Products | Contact us | Blog"),
    ("nav", "Home\nAbout\nProducts\nContact"),
    ("footer", "© 2026 Example Ltd. All rights reserved."),
    ("footer", "Copyright 2025 Example Press, printed in the UK by the publisher."),
    ("legal", "By using this site you agree to our Terms of Service and Privacy Policy."),
    ("legal", "These terms and conditions are governed by the laws of England and Wales."),
    ("boilerplate", "Leave a comment below and share this post with your friends online."),
    ("boilerplate", "Advertisement: scroll down to continue reading the article."),
]


@pytest.mark.parametrize("text", TEACHABLE)
def test_teachable_text_passes(text: str) -> None:
    assert teachable(text, MIN_CHARS) == (True, "")


@pytest.mark.parametrize(("_category", "text"), NON_TEACHABLE)
def test_non_teachable_text_is_refused(_category: str, text: str) -> None:
    ok, reason = teachable(text, MIN_CHARS)
    assert ok is False
    assert reason != ""


def test_reason_names_the_category() -> None:
    assert teachable("Call +44 20 7946 0958 for a quote on bulk orders today.", MIN_CHARS) == (
        False,
        "phone number",
    )
    assert teachable("Click here to read more.", MIN_CHARS) == (False, "too short")


def test_limit_is_taken_from_the_caller() -> None:
    text = "Binary search halves the range."
    assert teachable(text, MIN_CHARS)[0] is False
    assert teachable(text, 10) == (True, "")
