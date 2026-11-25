"""Worker side of the reader spool: submit, wait with injected clock, validate every result check, cleanup."""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import Any

import pytest
from kata_worker.reader_spool import (
    ReaderBadResult,
    ReaderTimeout,
    ResultLimits,
    cleanup,
    read_page_image,
    result_max_bytes,
    submit,
    validate_result,
    wait_result,
)

DOC_ID = "0123456789abcdef0123456789abcdef"
LIMITS = ResultLimits(
    max_pages=5, max_text_chars_per_page=100, max_image_bytes=4096, max_image_side_px=1600
)
PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _png(width: int, height: int, pad: int = 0) -> bytes:
    ihdr = b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"
    return PNG_SIG + ihdr + b"\x00" * 4 + b"\x00" * pad


def _page(n: int, text: str = "hello", image: str | None = None) -> dict[str, Any]:
    return {"n": n, "text": text, "image": image}


def _result(pages: list[dict[str, Any]] | None = None, **changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "v": 1,
        "id": DOC_ID,
        "status": "ok",
        "error": None,
        "pages": pages or [],
    }
    base.update(changes)
    return base


def _publish(
    spool_out: Path, result: dict[str, Any], images: dict[str, bytes] | None = None
) -> Path:
    out = spool_out / DOC_ID
    out.mkdir(parents=True)
    for name, data in (images or {}).items():
        (out / name).write_bytes(data)
    (out / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return out


def _ids() -> str:
    return DOC_ID


# submit ----------------------------------------------------------------


def test_submit_writes_bytes_then_marker(tmp_path: Path) -> None:
    spool_in = tmp_path / "in"
    doc_id = submit(spool_in, "application/pdf", b"%PDF-1.4", id_factory=_ids)
    assert doc_id == DOC_ID
    assert (spool_in / f"{DOC_ID}.bin").read_bytes() == b"%PDF-1.4"
    marker = json.loads((spool_in / f"{DOC_ID}.json").read_text(encoding="utf-8"))
    assert marker["v"] == 1
    assert marker["id"] == DOC_ID
    assert marker["media_type"] == "application/pdf"
    assert marker["size"] == 8
    assert len(marker["sha256"]) == 64
    assert sorted(p.name for p in spool_in.iterdir()) == [f"{DOC_ID}.bin", f"{DOC_ID}.json"]


def test_submit_rejects_bad_id_and_writes_nothing(tmp_path: Path) -> None:
    spool_in = tmp_path / "in"
    with pytest.raises(ValueError):
        submit(spool_in, "image/png", b"x", id_factory=lambda: "../evil")
    assert not spool_in.exists()


# wait_result -----------------------------------------------------------


def test_wait_returns_result_once_published(tmp_path: Path) -> None:
    spool_out = tmp_path / "out"
    spool_out.mkdir()
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 2:
            _publish(spool_out, _result())

    got = wait_result(spool_out, DOC_ID, 60, 1, clock=lambda: 0.0, sleep=sleep, max_bytes=1000)
    assert got["status"] == "ok"
    assert sleeps == [1, 1]


def test_wait_raises_timeout_at_deadline(tmp_path: Path) -> None:
    spool_out = tmp_path / "out"
    spool_out.mkdir()
    ticks = iter([0.0, 5.0, 11.0])
    with pytest.raises(ReaderTimeout):
        wait_result(
            spool_out,
            DOC_ID,
            10,
            1,
            clock=lambda: next(ticks),
            sleep=lambda _s: None,
            max_bytes=1000,
        )


def test_wait_rejects_non_object_result(tmp_path: Path) -> None:
    spool_out = tmp_path / "out"
    (spool_out / DOC_ID).mkdir(parents=True)
    (spool_out / DOC_ID / "result.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ReaderBadResult):
        wait_result(spool_out, DOC_ID, 10, 1, clock=lambda: 0.0, sleep=lambda _s: None, max_bytes=1000)


def test_wait_rejects_result_over_byte_cap(tmp_path: Path) -> None:
    spool_out = tmp_path / "out"
    (spool_out / DOC_ID).mkdir(parents=True)
    cap = result_max_bytes(LIMITS)
    (spool_out / DOC_ID / "result.json").write_bytes(b" " * (cap + 1))
    with pytest.raises(ReaderBadResult):
        wait_result(spool_out, DOC_ID, 10, 1, clock=lambda: 0.0, sleep=lambda _s: None, max_bytes=cap)


def test_result_max_bytes_allows_worst_case_escaped_page() -> None:
    worst_text = "\U0001f600" * LIMITS.max_text_chars_per_page
    pages = [_page(n, text=worst_text, image="p0001.png") for n in range(1, LIMITS.max_pages + 1)]
    encoded = json.dumps(_result(pages)).encode("utf-8")
    assert len(encoded) <= result_max_bytes(LIMITS)


# validate_result -------------------------------------------------------


def test_valid_text_result_passes(tmp_path: Path) -> None:
    out = _publish(tmp_path / "out", _result([_page(1), _page(2, text="")]))
    validate_result(_result([_page(1), _page(2, text="")]), out, LIMITS)


def test_valid_page_image_passes(tmp_path: Path) -> None:
    result = _result([_page(1, text="", image="p0001.png")])
    out = _publish(tmp_path / "out", result, {"p0001.png": _png(800, 600)})
    validate_result(result, out, LIMITS)


Built = tuple[dict[str, Any], dict[str, bytes] | None]


def _bad_results() -> list[tuple[str, Built]]:
    def case(result: dict[str, Any], images: dict[str, bytes] | None = None) -> Built:
        return result, images

    return [
        ("wrong version", case(_result(v=2))),
        ("bool version", case(_result(v=True))),
        ("id mismatch", case(_result(id="f" * 32))),
        ("unknown status", case(_result(status="maybe"))),
        ("ok with error", case(_result(error="too_large"))),
        ("error with unknown code", case(_result(status="error", error="boom"))),
        ("too many pages", case(_result([_page(n) for n in range(1, 7)]))),
        ("page numbers out of order", case(_result([_page(2), _page(1)]))),
        ("page number is a bool", case(_result([{"n": True, "text": "", "image": None}]))),
        ("text too long", case(_result([_page(1, text="x" * 101)]))),
        ("image not a string", case(_result([{"n": 1, "text": "", "image": 7}]))),
        ("page lacks image key", case(_result([{"n": 1, "text": "hi"}]))),
        ("image dot-dot name", case(_result([_page(1, image="p0001.png/../x")]))),
        ("image without leading zeros", case(_result([_page(1, image="p1.png")]))),
        ("image upper case", case(_result([_page(1, image="P0001.PNG")]))),
        ("image file missing", case(_result([_page(1, image="p0001.png")]))),
        (
            "image without PNG signature",
            case(
                _result([_page(1, image="p0001.png")]),
                {"p0001.png": b"\x00" * 8 + _png(40, 30)[8:]},
            ),
        ),
        (
            "image over max_image_bytes",
            case(_result([_page(1, image="p0001.png")]), {"p0001.png": _png(10, 10, pad=5000)}),
        ),
        (
            "image bomb dimensions",
            case(_result([_page(1, image="p0001.png")]), {"p0001.png": _png(1_000_000, 1_000_000)}),
        ),
        (
            "image zero width",
            case(_result([_page(1, image="p0001.png")]), {"p0001.png": _png(0, 10)}),
        ),
    ]


@pytest.mark.parametrize(
    ("name", "built"), _bad_results(), ids=[name for name, _ in _bad_results()]
)
def test_invalid_result_is_rejected(tmp_path: Path, name: str, built: Built) -> None:
    result, images = built
    out = _publish(tmp_path / "out", result, images)
    with pytest.raises(ReaderBadResult) as info:
        validate_result(result, out, LIMITS)
    assert info.value.code == "reader_bad_result"


def test_image_symlink_is_rejected(tmp_path: Path) -> None:
    result = _result([_page(1, image="p0001.png")])
    out = _publish(tmp_path / "out", result)
    target = tmp_path / "outside.png"
    target.write_bytes(_png(10, 10))
    os.symlink(target, out / "p0001.png")
    with pytest.raises(ReaderBadResult):
        validate_result(result, out, LIMITS)


def test_read_page_image_returns_checked_bytes(tmp_path: Path) -> None:
    png = _png(40, 30)
    result = _result([_page(1, text="", image="p0001.png")])
    out = _publish(tmp_path / "out", result, {"p0001.png": png})
    assert read_page_image(out, "p0001.png", LIMITS) == png
    with pytest.raises(ReaderBadResult):
        read_page_image(out, "../p0001.png", LIMITS)


# cleanup ---------------------------------------------------------------


def test_cleanup_removes_request_files_only(tmp_path: Path) -> None:
    spool_in, spool_out = tmp_path / "in", tmp_path / "out"
    submit(spool_in, "image/png", b"x", id_factory=_ids)
    _publish(spool_out, _result())
    (spool_out / f"{DOC_ID}.tmp").mkdir()
    (spool_in / "keep.txt").write_text("other", encoding="utf-8")
    cleanup(spool_in, spool_out, DOC_ID)
    assert sorted(p.name for p in spool_in.iterdir()) == ["keep.txt"]
    assert list(spool_out.iterdir()) == []


def test_cleanup_unlinks_symlink_without_following(tmp_path: Path) -> None:
    spool_in, spool_out = tmp_path / "in", tmp_path / "out"
    spool_in.mkdir()
    spool_out.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep", encoding="utf-8")
    os.symlink(victim, spool_out / DOC_ID)
    cleanup(spool_in, spool_out, DOC_ID)
    assert not (spool_out / DOC_ID).is_symlink()
    assert (victim / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_cleanup_rejects_bad_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        cleanup(tmp_path, tmp_path, "../x")
