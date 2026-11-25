"""Child-process sandbox: ok run, hung child timeout, memory over the limit, crash."""

from __future__ import annotations

import dataclasses
import os
from typing import Any

import pytest
from kata_reader import Limits, run_extract_isolated, run_isolated
from kata_reader.extract import PDF, Result, fail
from kata_reader.sandbox import _child_env

from tests.reader.conftest import PAGE_TEXT, Corpus, make_pdf

MIB = 1024 * 1024
HERE = __name__


def test_child_env_passes_only_allow_listed_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMPDIR", "/scratch-for-test")
    monkeypatch.setenv("KATA_SECRET_FOR_TEST", "must-not-leak")
    env = _child_env()
    assert env["TMPDIR"] == "/scratch-for-test"
    assert "KATA_SECRET_FOR_TEST" not in env
    assert "PYTHONPATH" in env


def _hang(job: dict[str, Any]) -> Result:
    """Blocks forever: the write end stays open in this child, so the read never returns."""
    read_end, _write_end = os.pipe()
    os.read(read_end, 1)
    return fail(job["doc_id"], "bad_file")


def _allocate(job: dict[str, Any]) -> Result:
    """Asks for 2 GiB; with the child's RLIMIT_AS at 1 GiB this raises MemoryError."""
    bytearray(2048 * MIB)
    return Result(id=job["doc_id"], status="ok")


def _crash(job: dict[str, Any]) -> Result:
    os._exit(3)  # dies without printing a result


def test_normal_run_returns_ok(corpus: Corpus) -> None:
    path = corpus.write("good.pdf", make_pdf([PAGE_TEXT]))
    result = run_extract_isolated(path, PDF, Limits(), corpus.out_dir(), doc_id="d1")
    assert result.status == "ok", result
    assert PAGE_TEXT in result.pages[0].text


def test_hung_child_times_out() -> None:
    limits = dataclasses.replace(Limits(), wall_seconds=1)
    result = run_isolated(f"{HERE}:_hang", {"doc_id": "d2"}, limits, "d2")
    assert result.status == "error"
    assert result.error == "timeout"


def test_child_over_memory_limit_is_error() -> None:
    limits = dataclasses.replace(Limits(), child_memory_mb=1024)
    result = run_isolated(f"{HERE}:_allocate", {"doc_id": "d3"}, limits, "d3")
    assert result.status == "error", result
    assert result.error == "bad_file"


def test_crashed_child_is_bad_file() -> None:
    result = run_isolated(f"{HERE}:_crash", {"doc_id": "d4"}, Limits(), "d4")
    assert result.status == "error"
    assert result.error == "bad_file"
