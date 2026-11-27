"""The reader.extract handler: document through the spool, page images to vision, failures fail the job, spool emptied."""

from __future__ import annotations

import io
import itertools
import json
import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import EXAMPLE_PATH, Config, load_config
from kata_reader.extract import extract
from kata_reader.limits import Limits
from kata_reader.spool import process_once
from kata_worker.core_client import CoreClient, CoreError, Job
from kata_worker.handlers import load_handlers
from kata_worker.handlers import reader_extract as handler
from kata_worker.providers.base import ProviderError
from kata_worker.providers.policy import Policy
from kata_worker.providers.router import Router
from PIL import Image
from pytest import MonkeyPatch

DOC_ID = "0123456789abcdef0123456789abcdef"
PNG_SIG = b"\x89PNG\r\n\x1a\n"
PAYLOAD = json.dumps({"document_id": 7})
DOC_PNG = "image/png"


@dataclass
class FakeClient:
    """Serves one document and records what the handler posts."""

    document: tuple[str, bytes] = (DOC_PNG, b"")
    outputs: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)
    fetched: list[int] = field(default_factory=list)

    def document_file(self, document_id: int) -> tuple[str, bytes]:
        self.fetched.append(document_id)
        return self.document

    def output(self, job_id: int, obj: dict[str, Any]) -> None:
        self.outputs.append((job_id, obj))

    def fail(self, job_id: int) -> None:
        self.failed.append(job_id)


class CoreErrorClient(FakeClient):
    def document_file(self, document_id: int) -> tuple[str, bytes]:
        raise CoreError("core down")


def _png(width: int, height: int, pad: int = 0) -> bytes:
    ihdr = b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"
    return PNG_SIG + ihdr + b"\x00" * 4 + b"\x00" * pad


def _scan_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, "PNG")
    return buf.getvalue()


def _cfg(spool: Path, **reader: Any) -> Config:
    base = load_config(EXAMPLE_PATH, env={})
    section = {**base.sections["reader"], "spool_dir": str(spool), **reader}
    return Config(sections={**base.sections, "reader": section})


def _policy() -> Policy:
    # The example config keeps vision cloud-only; these tests allow a local vision model, as test_router_vision does.
    base = load_config(EXAMPLE_PATH, env={})
    verdicts = {**base.sections["local_capability"], "vision": "kata-l"}
    return Policy.from_config(Config(sections={**base.sections, "local_capability": verdicts}), {})


def _router(script: list[str | ProviderError]) -> tuple[Router, FakeProvider]:
    provider = FakeProvider(name="local", script=script, vision=True)
    router = Router(
        {handler.VISION_CLASS: (provider.name,)}, {provider.name: provider}, _policy(), [].append
    )
    return router, provider


def _setup(
    monkeypatch: MonkeyPatch, spool: Path, sleep: Any, clock: Any = None, **reader: Any
) -> None:
    cfg = _cfg(spool, **reader)
    monkeypatch.setattr(handler, "load_config", lambda: cfg)
    monkeypatch.setattr(handler, "NEW_ID", lambda: DOC_ID)
    monkeypatch.setattr(handler, "SLEEP", sleep)
    monkeypatch.setattr(handler, "CLOCK", clock or (lambda: 0.0))


def _publish_sleep(
    spool: Path, result: dict[str, Any], images: dict[str, bytes] | None = None
) -> Any:
    """A fake sleep: the first call stands in for the reader and publishes out/<id>/ whole."""

    def sleep(_seconds: float) -> None:
        out = spool / "out" / DOC_ID
        out.mkdir(parents=True, exist_ok=True)
        for name, data in (images or {}).items():
            (out / name).write_bytes(data)
        (out / "result.json").write_text(json.dumps(result), encoding="utf-8")

    return sleep


def _reader_sleep(spool: Path) -> Any:
    """A fake sleep that runs the real reader spool loop once, in process."""

    def sleep(_seconds: float) -> None:
        process_once(spool / "in", spool / "out", Limits(), runner=extract)

    return sleep


def _result(
    pages: list[dict[str, Any]], status: str = "ok", error: str | None = None
) -> dict[str, Any]:
    return {"v": 1, "id": DOC_ID, "status": status, "error": error, "pages": pages}


def _page(n: int, text: str = "", image: str | None = None) -> dict[str, Any]:
    return {"n": n, "text": text, "image": image}


def _spool_empty(spool: Path) -> bool:
    return all(not any(path.iterdir()) for path in (spool / "in", spool / "out") if path.exists())


def _run(client: FakeClient, router: Router) -> None:
    handler.handle(Job(id=5, payload=PAYLOAD, kind=handler.KIND), router, cast(CoreClient, client))


def test_registry_discovers_reader_handler() -> None:
    assert load_handlers()["reader.extract"] is handler.handle


def test_scan_page_image_goes_to_vision_as_png(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    spool = tmp_path / "spool"
    _setup(monkeypatch, spool, _reader_sleep(spool))
    router, provider = _router(["Scanned words"])
    client = FakeClient(document=(DOC_PNG, _scan_png()))
    _run(client, router)
    assert client.fetched == [7]
    assert client.failed == []
    assert client.outputs == [(5, {"pages": [{"n": 1, "text": "Scanned words"}]})]
    assert len(provider.vision_calls) == 1
    system, _user, images = provider.vision_calls[0]
    assert "untrusted" in system
    assert images[0][0] == "image/png"
    assert images[0][1].startswith(PNG_SIG)
    assert _spool_empty(spool)


def test_text_only_page_makes_no_vision_call(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    spool = tmp_path / "spool"
    result = _result([_page(1, text="Plain text")])
    _setup(monkeypatch, spool, _publish_sleep(spool, result))
    router, provider = _router([])
    client = FakeClient()
    _run(client, router)
    assert provider.vision_calls == []
    assert client.outputs == [(5, {"pages": [{"n": 1, "text": "Plain text"}]})]
    assert _spool_empty(spool)


def test_max_images_cap_skips_extra_images(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    spool = tmp_path / "spool"
    names = ["p0001.png", "p0002.png", "p0003.png"]
    pages = [_page(i + 1, text=f"t{i + 1}", image=name) for i, name in enumerate(names)]
    images = {name: _png(20, 20) for name in names}
    _setup(
        monkeypatch, spool, _publish_sleep(spool, _result(pages), images), max_images_per_document=2
    )
    router, provider = _router(["one", "two"])
    client = FakeClient()
    _run(client, router)
    assert len(provider.vision_calls) == 2
    assert client.outputs == [
        (
            5,
            {
                "pages": [
                    {"n": 1, "text": "t1\none"},
                    {"n": 2, "text": "t2\ntwo"},
                    {"n": 3, "text": "t3"},
                ]
            },
        )
    ]
    assert _spool_empty(spool)


def test_reader_error_status_posts_error_code(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    spool = tmp_path / "spool"
    result = _result([], status="error", error="too_large")
    _setup(monkeypatch, spool, _publish_sleep(spool, result))
    router, _provider = _router([])
    client = FakeClient()
    _run(client, router)
    assert client.outputs == [(5, {"pages": [], "error": "too_large"})]
    assert client.failed == []
    assert _spool_empty(spool)


def test_vision_reply_control_chars_are_stripped(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    spool = tmp_path / "spool"
    result = _result([_page(1, text="", image="p0001.png")])
    _setup(monkeypatch, spool, _publish_sleep(spool, result, {"p0001.png": _png(20, 20)}))
    router, _provider = _router(["a\x00b\x07c\td\n"])
    client = FakeClient()
    _run(client, router)
    assert client.outputs == [(5, {"pages": [{"n": 1, "text": "abc\td\n"}]})]
    assert _spool_empty(spool)


def test_vision_reply_is_capped_to_max_text_chars_per_page(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    spool = tmp_path / "spool"
    result = _result([_page(1, text="", image="p0001.png")])
    _setup(
        monkeypatch,
        spool,
        _publish_sleep(spool, result, {"p0001.png": _png(20, 20)}),
        max_text_chars_per_page=10,
    )
    router, _provider = _router(["x" * 50])
    client = FakeClient()
    _run(client, router)
    assert len(client.outputs) == 1
    _job_id, obj = client.outputs[0]
    assert len(obj["pages"][0]["text"]) == 10


def test_failure_log_names_code_without_document_or_page_text(
    tmp_path: Path, monkeypatch: MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    spool = tmp_path / "spool"
    result = _result([_page(1, text="SECRET-PAGE-TEXT", image="p1.png")])
    _setup(monkeypatch, spool, _publish_sleep(spool, result))
    router, _provider = _router([])
    client = FakeClient(document=(DOC_PNG, b"SECRET-DOC-BYTES"))
    caplog.set_level(logging.WARNING, logger=handler.__name__)
    _run(client, router)
    assert client.failed == [5]
    assert "failed while reading document" in caplog.text
    assert "SECRET" not in caplog.text


def _bad_cases() -> list[tuple[str, dict[str, Any], dict[str, bytes] | None]]:
    png_name = "p0001.png"
    return [
        ("wrong version", {**_result([_page(1)]), "v": 2}, None),
        ("page lacks image key", _result([{"n": 1, "text": "hi"}]), None),
        ("page image not a string", _result([{"n": 1, "text": "", "image": 7}]), None),
        ("pages not a list", {**_result([]), "pages": "many"}, None),
        ("bad image name", _result([_page(1, image="p1.png")]), None),
        ("decoy image path", _result([_page(1, image="p0001.png/../x")]), None),
        (
            "oversize png",
            _result([_page(1, image=png_name)]),
            {png_name: _png(10, 10, pad=2_100_000)},
        ),
        (
            "bomb dimensions",
            _result([_page(1, image=png_name)]),
            {png_name: _png(1_000_000, 1_000_000)},
        ),
        (
            "no png signature",
            _result([_page(1, image=png_name)]),
            {png_name: b"\x00" * 8 + _png(40, 30)[8:]},
        ),
    ]


@pytest.mark.parametrize(
    ("name", "result", "images"), _bad_cases(), ids=[case[0] for case in _bad_cases()]
)
def test_bad_result_fails_job_and_empties_spool(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    name: str,
    result: dict[str, Any],
    images: dict[str, bytes] | None,
) -> None:
    spool = tmp_path / "spool"
    _setup(monkeypatch, spool, _publish_sleep(spool, result, images))
    router, provider = _router(["never"])
    client = FakeClient()
    _run(client, router)
    assert client.failed == [5]
    assert client.outputs == []
    assert provider.vision_calls == []
    assert _spool_empty(spool)


def test_timeout_fails_job_and_empties_spool(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    spool = tmp_path / "spool"
    ticks = itertools.count(0, 200)
    _setup(monkeypatch, spool, lambda _s: None, clock=lambda: next(ticks), wait_seconds=120)
    router, _provider = _router([])
    client = FakeClient()
    _run(client, router)
    assert client.failed == [5]
    assert client.outputs == []
    assert _spool_empty(spool)


def test_vision_failure_fails_job_and_empties_spool(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    spool = tmp_path / "spool"
    result = _result([_page(1, text="", image="p0001.png")])
    _setup(monkeypatch, spool, _publish_sleep(spool, result, {"p0001.png": _png(20, 20)}))
    router, _provider = _router([ProviderError("model down")])
    client = FakeClient()
    _run(client, router)
    assert client.failed == [5]
    assert client.outputs == []
    assert _spool_empty(spool)


def test_no_vision_model_fails_job_named_and_sends_no_image(
    tmp_path: Path, monkeypatch: MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    spool = tmp_path / "spool"
    result = _result([_page(1, text="", image="p0001.png")])
    _setup(monkeypatch, spool, _publish_sleep(spool, result, {"p0001.png": _png(20, 20)}))
    provider = FakeProvider(name="local", script=[], vision=False)
    router = Router(
        {handler.VISION_CLASS: (provider.name,)},
        {provider.name: provider},
        _policy(),
        [].append,
    )
    client = FakeClient()
    with caplog.at_level(logging.WARNING, logger=handler.__name__):
        _run(client, router)
    assert client.failed == [5]
    assert client.outputs == []
    assert provider.vision_calls == []
    assert any(handler.NO_VISION_MESSAGE in record.getMessage() for record in caplog.records)
    assert _spool_empty(spool)


def test_core_error_propagates_and_empties_spool(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    spool = tmp_path / "spool"
    _setup(monkeypatch, spool, lambda _s: None)
    router, _provider = _router([])
    client = CoreErrorClient()
    with pytest.raises(CoreError):
        _run(client, router)
    assert client.failed == []
    assert _spool_empty(spool)
