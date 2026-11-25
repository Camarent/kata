"""Reader config: the [reader] table only, a clear error for a missing key, exit 2 from main()."""

from __future__ import annotations

from pathlib import Path

import pytest
from kata_reader import config
from kata_reader.__main__ import main
from kata_reader.limits import Limits

FULL_BLOCK = """
[reader]
enabled = false
max_file_bytes = 1234
max_pages = 5
min_page_chars = 40
max_image_side_px = 800
max_image_bytes = 99999
max_images_per_document = 3
max_text_chars_per_page = 500
child_memory_mb = 256
child_cpu_seconds = 7
wall_seconds = 9
poll_seconds = 2
wait_seconds = 120
spool_dir = "/spool"

[secrets]
token = "must-not-be-read"
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "kata.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_reads_reader_table_only(tmp_path: Path) -> None:
    cfg = config.load(_write(tmp_path, FULL_BLOCK))
    assert cfg.limits == Limits(
        max_file_bytes=1234,
        max_pages=5,
        min_page_chars=40,
        max_image_side_px=800,
        max_image_bytes=99999,
        max_text_chars_per_page=500,
        child_memory_mb=256,
        child_cpu_seconds=7,
        wall_seconds=9,
    )
    assert cfg.poll_seconds == 2
    assert cfg.spool_dir == Path("/spool")


def test_missing_key_names_the_key(tmp_path: Path) -> None:
    text = FULL_BLOCK.replace("wall_seconds = 9\n", "")
    with pytest.raises(config.ConfigError, match="wall_seconds"):
        config.load(_write(tmp_path, text))


def test_missing_reader_table_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match=r"\[reader\]"):
        config.load(_write(tmp_path, "[other]\nx = 1\n"))


def test_main_exits_2_on_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "[reader]\n")
    monkeypatch.setenv(config.CONFIG_ENV, str(path))
    assert main() == 2
    assert "missing key" in capsys.readouterr().err
