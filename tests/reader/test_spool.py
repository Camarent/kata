"""Spool protocol v1, reader side: good requests, every bad marker or body, and the serve loop.

Requests are written by hand into tmp_path/in. A stub runner stands in for the sandbox in all but
one test, which runs the real sandboxed extract on a tiny PDF.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from kata_reader import Limits
from kata_reader.extract import PDF, PNG, Page, Result
from kata_reader.spool import process_once, serve

from tests.reader.conftest import PAGE_TEXT, make_pdf, png_bytes

ID_A = "a" * 32
ID_B = "b" * 32


def _request(in_dir: Path, doc_id: str, data: bytes, media: str = PDF, **marker: Any) -> None:
    """Write in/<id>.bin then the commit marker in/<id>.json, as the worker does."""
    in_dir.mkdir(parents=True, exist_ok=True)
    (in_dir / f"{doc_id}.bin").write_bytes(data)
    body: dict[str, Any] = {
        "v": 1,
        "id": doc_id,
        "media_type": media,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    body.update(marker)
    (in_dir / f"{doc_id}.json").write_text(json.dumps(body), encoding="utf-8")


class StubRunner:
    """Stands in for run_extract_isolated: writes one PNG and returns ok, or raises for fail_ids."""

    def __init__(self, fail_ids: tuple[str, ...] = ()) -> None:
        self.fail_ids = fail_ids
        self.calls: list[str] = []

    def __call__(
        self, path: Path, media: str, limits: Limits, out_dir: Path, doc_id: str
    ) -> Result:
        self.calls.append(doc_id)
        if doc_id in self.fail_ids:
            raise RuntimeError("stub crash")
        (out_dir / "p0001.png").write_bytes(png_bytes(4, 4))
        return Result(id=doc_id, status="ok", pages=(Page(n=1, text="hello", image="p0001.png"),))


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "in", tmp_path / "out"


def _result(out_dir: Path, doc_id: str) -> dict[str, Any]:
    return json.loads((out_dir / doc_id / "result.json").read_text(encoding="utf-8"))


def _assert_clean(in_dir: Path, out_dir: Path, names_before: set[str]) -> None:
    """No work dir left behind, and nothing under in/ was deleted."""
    assert not [p for p in out_dir.iterdir() if p.name.endswith(".tmp")]
    assert names_before <= {p.name for p in in_dir.iterdir()}


def test_ok_request_publishes_result_and_pages(dirs: tuple[Path, Path]) -> None:
    in_dir, out_dir = dirs
    _request(in_dir, ID_A, b"%PDF-body")
    runner = StubRunner()
    assert process_once(in_dir, out_dir, Limits(), runner) == 1
    result = _result(out_dir, ID_A)
    assert result["v"] == 1
    assert result["status"] == "ok"
    assert result["pages"] == [{"n": 1, "text": "hello", "image": "p0001.png"}]
    assert (out_dir / ID_A / "p0001.png").is_file()
    _assert_clean(in_dir, out_dir, {f"{ID_A}.bin", f"{ID_A}.json"})


def test_published_request_is_skipped_on_reprocess(dirs: tuple[Path, Path]) -> None:
    in_dir, out_dir = dirs
    _request(in_dir, ID_A, b"%PDF-body")
    runner = StubRunner()
    process_once(in_dir, out_dir, Limits(), runner)
    assert process_once(in_dir, out_dir, Limits(), runner) == 0
    assert runner.calls == [ID_A]


def test_half_written_body_without_marker_is_ignored(dirs: tuple[Path, Path]) -> None:
    in_dir, out_dir = dirs
    in_dir.mkdir()
    (in_dir / f"{ID_A}.bin").write_bytes(b"%PDF-body")
    runner = StubRunner()
    assert process_once(in_dir, out_dir, Limits(), runner) == 0
    assert runner.calls == []
    assert not (out_dir / ID_A).exists()


@pytest.mark.parametrize(
    "marker",
    [
        {"v": 2},
        {"id": "c" * 32},
        {"media_type": "text/html"},
        {"size": "9"},
        {"size": True},
        {"sha256": "XYZ"},
        {"sha256": None},
    ],
    ids=["version", "id", "media", "size-type", "size-bool", "sha-format", "sha-missing"],
)
def test_bad_marker_field_gives_bad_file(
    dirs: tuple[Path, Path], marker: dict[str, Any]
) -> None:
    in_dir, out_dir = dirs
    _request(in_dir, ID_A, b"%PDF-body", **marker)
    runner = StubRunner()
    process_once(in_dir, out_dir, Limits(), runner)
    assert _result(out_dir, ID_A)["error"] == "bad_file"
    assert runner.calls == []
    _assert_clean(in_dir, out_dir, {f"{ID_A}.bin", f"{ID_A}.json"})


def test_marker_that_is_not_json_gives_bad_file(dirs: tuple[Path, Path]) -> None:
    in_dir, out_dir = dirs
    in_dir.mkdir()
    (in_dir / f"{ID_A}.json").write_text("{not json", encoding="utf-8")
    (in_dir / f"{ID_A}.bin").write_bytes(b"%PDF-body")
    process_once(in_dir, out_dir, Limits(), StubRunner())
    assert _result(out_dir, ID_A)["error"] == "bad_file"


def test_size_mismatch_gives_bad_file(dirs: tuple[Path, Path]) -> None:
    in_dir, out_dir = dirs
    _request(in_dir, ID_A, b"%PDF-body", size=3)
    runner = StubRunner()
    process_once(in_dir, out_dir, Limits(), runner)
    assert _result(out_dir, ID_A)["error"] == "bad_file"
    assert runner.calls == []


def test_sha_mismatch_gives_bad_file(dirs: tuple[Path, Path]) -> None:
    in_dir, out_dir = dirs
    _request(in_dir, ID_A, b"%PDF-body", sha256="0" * 64)
    runner = StubRunner()
    process_once(in_dir, out_dir, Limits(), runner)
    assert _result(out_dir, ID_A)["error"] == "bad_file"
    assert runner.calls == []


def test_size_over_cap_gives_too_large_before_reading(dirs: tuple[Path, Path]) -> None:
    in_dir, out_dir = dirs
    _request(in_dir, ID_A, b"x" * 100)
    runner = StubRunner()
    process_once(in_dir, out_dir, Limits(max_file_bytes=10), runner)
    assert _result(out_dir, ID_A)["error"] == "too_large"
    assert runner.calls == []


def test_symlink_body_is_never_followed(dirs: tuple[Path, Path], tmp_path: Path) -> None:
    in_dir, out_dir = dirs
    in_dir.mkdir()
    outside = tmp_path / "outside.pdf"
    data = make_pdf([PAGE_TEXT])
    outside.write_bytes(data)
    (in_dir / f"{ID_A}.bin").symlink_to(outside)
    _request(in_dir, ID_B, b"%PDF-other")
    (in_dir / f"{ID_A}.json").write_text(
        json.dumps(
            {
                "v": 1,
                "id": ID_A,
                "media_type": PDF,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    runner = StubRunner()
    process_once(in_dir, out_dir, Limits(), runner)
    assert _result(out_dir, ID_A)["error"] == "bad_file"
    assert runner.calls == [ID_B]


def test_marker_id_must_match_file_stem(dirs: tuple[Path, Path], tmp_path: Path) -> None:
    in_dir, out_dir = dirs
    _request(in_dir, ID_A, b"%PDF-body", id="../../outside")
    runner = StubRunner()
    process_once(in_dir, out_dir, Limits(), runner)
    assert _result(out_dir, ID_A)["error"] == "bad_file"
    assert not (tmp_path / "outside").exists()
    assert runner.calls == []


def test_non_hex_file_name_is_ignored(dirs: tuple[Path, Path]) -> None:
    in_dir, out_dir = dirs
    in_dir.mkdir()
    (in_dir / "NOTHEX.json").write_text("{}", encoding="utf-8")
    runner = StubRunner()
    assert process_once(in_dir, out_dir, Limits(), runner) == 0
    assert not out_dir.exists() or not any(out_dir.iterdir())
    assert runner.calls == []


def test_runner_crash_gives_error_and_next_request_is_processed(
    dirs: tuple[Path, Path],
) -> None:
    in_dir, out_dir = dirs
    _request(in_dir, ID_A, b"%PDF-one")
    _request(in_dir, ID_B, b"%PDF-two")
    runner = StubRunner(fail_ids=(ID_A,))
    assert process_once(in_dir, out_dir, Limits(), runner) == 2
    assert _result(out_dir, ID_A)["status"] == "error"
    assert _result(out_dir, ID_A)["error"] == "bad_file"
    assert _result(out_dir, ID_B)["status"] == "ok"
    _assert_clean(in_dir, out_dir, {f"{ID_A}.bin", f"{ID_B}.bin"})


def test_failed_extract_publishes_no_pages(dirs: tuple[Path, Path]) -> None:
    in_dir, out_dir = dirs
    _request(in_dir, ID_A, b"%PDF-body")

    def failing(path: Path, media: str, limits: Limits, out: Path, doc_id: str) -> Result:
        (out / "p0001.png").write_bytes(png_bytes(4, 4))
        return Result(id=doc_id, status="error", error="bomb")

    process_once(in_dir, out_dir, Limits(), failing)
    assert _result(out_dir, ID_A)["error"] == "bomb"
    assert sorted(p.name for p in (out_dir / ID_A).iterdir()) == ["result.json"]
    _assert_clean(in_dir, out_dir, {f"{ID_A}.bin", f"{ID_A}.json"})


def test_real_sandboxed_extract_end_to_end(dirs: tuple[Path, Path]) -> None:
    in_dir, out_dir = dirs
    _request(in_dir, ID_A, make_pdf([PAGE_TEXT]))
    assert process_once(in_dir, out_dir, Limits()) == 1
    result = _result(out_dir, ID_A)
    assert result["v"] == 1
    assert result["status"] == "ok", result
    assert len(result["pages"]) == 1
    assert "Hello" in result["pages"][0]["text"]
    _assert_clean(in_dir, out_dir, {f"{ID_A}.bin", f"{ID_A}.json"})


def test_serve_sleeps_until_stop(dirs: tuple[Path, Path]) -> None:
    in_dir, out_dir = dirs
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    serve(
        in_dir,
        out_dir,
        Limits(),
        2.5,
        fake_sleep,
        lambda: len(sleeps) >= 3,
        StubRunner(),
    )
    assert sleeps == [2.5, 2.5, 2.5]


def test_png_media_request_is_accepted(dirs: tuple[Path, Path]) -> None:
    in_dir, out_dir = dirs
    _request(in_dir, ID_A, png_bytes(4, 4), media=PNG)
    runner = StubRunner()
    process_once(in_dir, out_dir, Limits(), runner)
    assert runner.calls == [ID_A]
    assert _result(out_dir, ID_A)["status"] == "ok"
