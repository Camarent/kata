"""Syllabus parser and model-extract validation: pure functions, no database."""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest
from kata_core.importer.syllabus import (
    TITLE_LIMIT,
    Module,
    ParseError,
    _heading_title,
    _numbered_title,
    parse_modules,
    validate_extracted,
)

SOURCE = "Intro to graphs. Nodes and edges. Trees are graphs. Sorting basics."


def test_markdown_headings_split_modules() -> None:
    text = "# Graphs\nNodes and edges.\n## Trees\nTrees are graphs.\n"
    modules = parse_modules(text)
    assert [m.title for m in modules] == ["Graphs", "Trees"]
    assert modules[0].body == "Nodes and edges."
    assert modules[1].body == "Trees are graphs."


def test_heading_needs_space_so_hashtag_is_not_heading() -> None:
    text = "1. Graphs\nSee #graphs for more.\n2. Sorting\nBubble sort.\n"
    modules = parse_modules(text)
    assert [m.title for m in modules] == ["Graphs", "Sorting"]
    assert modules[0].body == "See #graphs for more."


def test_numbered_lines_split_modules() -> None:
    text = "1. Graphs\nNodes and edges.\n2. Sorting\nBubble sort.\n"
    modules = parse_modules(text)
    assert [m.title for m in modules] == ["Graphs", "Sorting"]
    assert modules[1].body == "Bubble sort."


def test_module_prefix_lines_split_modules() -> None:
    text = "Module 1: Graphs\nNodes.\nmodule 2 - Sorting\nBubble sort.\n"
    modules = parse_modules(text)
    assert [m.title for m in modules] == ["Graphs", "Sorting"]


def test_plain_text_is_one_module() -> None:
    modules = parse_modules(SOURCE)
    assert len(modules) == 1
    assert modules[0].title == SOURCE
    assert modules[0].body == SOURCE


def test_words_counts_body_words() -> None:
    modules = parse_modules("# Graphs\none two three\n")
    assert modules[0].words == 3


def test_blank_text_raises() -> None:
    with pytest.raises(ParseError):
        parse_modules("  \n\t ")


def test_heading_wins_over_numbered_lines() -> None:
    text = "# Graphs\n1. Not a module\n"
    modules = parse_modules(text)
    assert [m.title for m in modules] == ["Graphs"]
    assert modules[0].body == "1. Not a module"


def test_decoy_heading_like_line_inside_numbered_text_stays_numbered() -> None:
    text = "1. Graphs\n#1 is the answer\n2. Sorting\nBubble sort.\n"
    modules = parse_modules(text)
    assert [m.title for m in modules] == ["Graphs", "Sorting"]
    assert modules[0].body == "#1 is the answer"


def test_valid_modules_are_kept() -> None:
    modules = [Module(title="Graphs", body="Nodes and edges.", words=3)]
    assert validate_extracted(SOURCE, modules) == modules


def test_whitespace_differences_do_not_fail_substring_check() -> None:
    source = "Nodes   and\n edges. Trees."
    modules = [Module(title="Graphs", body="Nodes and edges.", words=3)]
    assert validate_extracted(source, modules) == modules


def test_body_not_in_source_falls_back_to_whole_source() -> None:
    modules = [
        Module(title="Graphs", body="Nodes and edges.", words=3),
        Module(title="Invented", body="Quantum cooking.", words=2),
    ]
    result = validate_extracted(SOURCE, modules)
    assert len(result) == 1
    assert result[0].body == SOURCE


def test_title_over_limit_falls_back_to_whole_source() -> None:
    long_title = "x" * (TITLE_LIMIT + 1)
    modules = [Module(title=long_title, body="Nodes and edges.", words=3)]
    result = validate_extracted(SOURCE, modules)
    assert len(result) == 1
    assert result[0].body == SOURCE


def test_title_at_limit_is_kept() -> None:
    title = "x" * TITLE_LIMIT
    modules = [Module(title=title, body="Nodes and edges.", words=3)]
    assert validate_extracted(SOURCE, modules) == modules


def test_empty_body_falls_back_to_whole_source() -> None:
    modules = [Module(title="Graphs", body="", words=0)]
    result = validate_extracted(SOURCE, modules)
    assert result[0].body == SOURCE


def test_empty_module_list_falls_back_to_whole_source() -> None:
    result = validate_extracted(SOURCE, [])
    assert result == [Module(title=SOURCE, body=SOURCE, words=len(SOURCE.split()))]


def test_validate_blank_source_raises() -> None:
    with pytest.raises(ParseError):
        validate_extracted("   ", [])


@pytest.mark.parametrize("prefix", ["# Title", "1. Title"])
def test_long_trailing_spaces_parse_fast(prefix: str) -> None:
    # A title followed by a long run of spaces must not backtrack quadratically in the line regexes.
    line = prefix + " " * 200000 + "x"
    started = time.perf_counter()
    modules = parse_modules(line)
    elapsed = time.perf_counter() - started
    assert modules[0].title.endswith("x")
    assert elapsed < 1.0


@pytest.mark.parametrize(
    ("title_of", "line"),
    [(_heading_title, "#"), (_numbered_title, "1."), (_numbered_title, "9)"), (_numbered_title, "Module 9:")],
)
def test_line_matchers_do_not_slow_down_on_space_run(title_of: Callable[[str], str | None], line: str) -> None:
    # Mutant check: a regex with `(.+)$` took quadratic time on this input (about 1 s at 20000 spaces).
    # The space run sits inside the line (the matchers get stripped lines), so it reaches the matcher.
    started = time.perf_counter()
    assert title_of(line + " " * 100000 + "x") == "x"
    assert time.perf_counter() - started < 1.0


@pytest.mark.parametrize(
    ("line", "title"),
    [
        ("1. Graphs", "Graphs"),
        ("1) Graphs", "Graphs"),
        ("Module 1: Graphs", "Graphs"),
        ("module 2 - Graphs", "Graphs"),
        ("MODULE 3. Graphs", "Graphs"),
        ("Module 4) Graphs", "Graphs"),
        ("Module1: Graphs", None),
        ("1.Graphs", None),
        ("1.", None),
        ("Module 5:", None),
    ],
)
def test_numbered_title_forms(line: str, title: str | None) -> None:
    assert _numbered_title(line) == title


@pytest.mark.parametrize("text", ["# ", "#   ", "1. ", "1.   "])
def test_whitespace_only_title_is_body_text_not_a_module_boundary(text: str) -> None:
    # Intended: a heading or numbered line needs a visible title; otherwise the text is one plain module.
    source = text + "\nbody"
    expected = Module(title=text.strip(), body=source.strip(), words=len(source.split()))
    assert parse_modules(source) == [expected]
