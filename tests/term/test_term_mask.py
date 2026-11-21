"""Masking of terminal command text: user mask list, built-in patterns, silence, default path."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from kata_term.mask import default_mask_path, load_masks, mask_command


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_masks_skips_blank_comment_and_invalid_lines(tmp_path: Path) -> None:
    path = _write(tmp_path / "masks", "\n# a comment\nacme-[0-9]+\n(unclosed\n  plain  \n")
    masks = load_masks(path)
    assert [m.pattern for m in masks] == ["acme-[0-9]+", "plain"]


def test_load_masks_skips_overflow_and_empty_matching_lines(tmp_path: Path) -> None:
    path = _write(tmp_path / "masks", "a{4294967296}\nx*\nkeep-me\n")
    assert [m.pattern for m in load_masks(path)] == ["keep-me"]


def test_load_masks_invalid_utf8_byte_only_affects_its_line(tmp_path: Path) -> None:
    path = tmp_path / "masks"
    path.write_bytes(b"first-[0-9]\n\xff\xfe\nlast-[0-9]\n")
    patterns = [m.pattern for m in load_masks(path)]
    assert "first-[0-9]" in patterns and "last-[0-9]" in patterns


def test_load_masks_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_masks(tmp_path / "absent") == []


def test_load_masks_invalid_line_is_not_echoed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    path = _write(tmp_path / "masks", "(secret-unclosed\n")
    with caplog.at_level(logging.DEBUG):
        assert load_masks(path) == []
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    assert caplog.records == []


def test_user_mask_replaces_match(tmp_path: Path) -> None:
    masks = load_masks(_write(tmp_path / "masks", "acme-[0-9]+\n"))
    assert mask_command("deploy acme-42 now", masks) == "deploy [masked] now"


def test_builtin_key_value_assignment_is_masked() -> None:
    assert mask_command("API_KEY=abc123 make", []) == "[masked] make"
    assert mask_command("psql password=hunter2", []) == "psql [masked]"


def test_builtin_bearer_is_masked() -> None:
    assert mask_command("curl -H 'Authorization: Bearer abc.def' x", []) == (
        "curl -H 'Authorization: [masked]' x"
    )


def test_builtin_password_argument_is_masked() -> None:
    assert mask_command("tool -p hunter2 run", []) == "tool [masked] run"
    assert mask_command("tool --password=hunter2 run", []) == "tool [masked] run"


def test_builtin_long_high_entropy_token_is_masked() -> None:
    token = "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6"
    assert mask_command(f"echo {token}", []) == "echo [masked]"


def test_plain_words_and_short_tokens_are_kept() -> None:
    text = "git commit -m fix src/core/kata_term/mask.py abcdefghijklmnopqrstuvwxyzabcdef"
    assert mask_command(text, []) == text


def test_masking_and_loading_bad_list_is_silent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        masks = load_masks(_write(tmp_path / "masks", "[bad\nok-[0-9]\n"))
        mask_command("API_KEY=abc ok-7 Bearer xyz", masks)
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    assert caplog.records == []


def test_default_mask_path_uses_env_override(tmp_path: Path) -> None:
    override = tmp_path / "my-masks"
    assert default_mask_path({"KATA_TERM_MASKS": str(override)}) == override


def test_default_mask_path_falls_back_to_home_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_mask_path({}) == tmp_path / ".config" / "kata" / "term-masks"
