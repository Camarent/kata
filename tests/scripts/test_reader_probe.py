"""scripts/dev/reader_probe.py: corpus, spool feed with fake runner, sandbox checks, report and --check-report."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "scripts" / "dev" / "reader_probe.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("reader_probe", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


reader_probe = _load_script()


class FakeClock:
    """Injected clock: sleep only moves the time forward."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


class FakeRunner:
    """Stands in for docker compose exec. Worker writes record the media; reader cat answers per media.

    results maps a media type to a result dict (answered), raw bytes (answered as is, e.g. not JSON),
    or None (no result file: the probe times out).
    sandbox maps 'connect'/'write' to the stdout of that check, or None for a failed exec.
    """

    def __init__(self, results: dict[str, dict | bytes | None], sandbox: dict[str, str | None]) -> None:
        self.results = results
        self.sandbox = sandbox
        self.media_by_id: dict[str, str] = {}

    def __call__(self, service: str, argv: list[str], _stdin: bytes) -> tuple[int, bytes]:
        if service == reader_probe.WORKER_SERVICE:
            marker = json.loads(argv[6])
            self.media_by_id[argv[5]] = marker["media_type"]
            return 0, b""
        if argv[0] == "cat":
            doc_id = argv[1].split("/")[-2]
            answer = self.results.get(self.media_by_id[doc_id])
            if answer is None:
                return 1, b""
            if isinstance(answer, bytes):
                return 0, answer
            return 0, json.dumps({**answer, "id": doc_id}).encode()
        check = "connect" if "192.0.2.1" in argv[3] else "write"
        out = self.sandbox[check]
        return (0, out.encode()) if out is not None else (1, b"")


OK_RESULT = {"v": 1, "status": "ok", "error": None, "pages": [{"n": 1, "text": "hi", "image": None}]}
BAD_RESULT = {"v": 1, "status": "error", "error": "bad_file", "pages": []}
BLOCKED_SANDBOX = {"connect": "blocked", "write": "blocked"}


def _good_report() -> str:
    rows = [reader_probe.Row("a.pdf", "application/pdf", "done", 1)]
    return reader_probe.build_report(rows, dict(BLOCKED_SANDBOX))


def test_corpus_writes_five_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = reader_probe.make_corpus(Path(tmp) / "corpus")
        assert len(paths) == 5
        assert sorted(p.name for p in paths) == sorted(
            ["empty.pdf", "bad_magic.pdf", "truncated.pdf", "huge_declared.png", "trailing_junk.png"]
        )
        assert (Path(tmp) / "corpus" / "empty.pdf").read_bytes() == b""


def test_run_probe_rows_done_error_timeout() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ok = Path(tmp) / "ok.pdf"
        bad = Path(tmp) / "bad.png"
        slow = Path(tmp) / "slow.webp"
        ok.write_bytes(b"%PDF-1.4 body")
        bad.write_bytes(b"\x89PNG bad")
        slow.write_bytes(b"RIFF....WEBP")
        runner = FakeRunner(
            {"application/pdf": OK_RESULT, "image/png": BAD_RESULT, "image/webp": None},
            dict(BLOCKED_SANDBOX),
        )
        rows = reader_probe.run_probe([ok, bad, slow], runner, FakeClock(), poll_seconds=1.0, timeout_seconds=3.0)
    assert [(r.name, r.media, r.status, r.pages) for r in rows] == [
        ("ok.pdf", "application/pdf", "done", 1),
        ("bad.png", "image/png", "bad_file", 0),
        ("slow.webp", "image/webp", "timeout", 0),
    ]


def test_run_probe_unreadable_result_is_bad_result() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "x.pdf"
        path.write_bytes(b"%PDF")
        runner = FakeRunner({"application/pdf": {"v": 1}}, dict(BLOCKED_SANDBOX))
        rows = reader_probe.run_probe([path], runner, FakeClock())
    assert rows[0].status == "bad_result"


def test_run_probe_garbage_result_is_bad_result_finding() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "x.pdf"
        path.write_bytes(b"%PDF")
        runner = FakeRunner({"application/pdf": b"\x00 not json"}, dict(BLOCKED_SANDBOX))
        rows = reader_probe.run_probe([path], runner, FakeClock())
    assert rows[0].status == "bad_result"
    report = reader_probe.build_report(rows, dict(BLOCKED_SANDBOX))
    assert "- x.pdf: bad_result" in report
    assert "Status: pending" in report
    assert reader_probe.check_report(report)


def test_report_feed_error_is_not_done() -> None:
    rows = [reader_probe.Row("a.pdf", "application/pdf", "feed_error", 0)]
    report = reader_probe.build_report(rows, dict(BLOCKED_SANDBOX))
    assert "- a.pdf: feed_error" in report
    assert "Status: pending" in report
    assert "Status: done" not in report
    assert reader_probe.check_report(report) == [
        "file a.pdf: feed_error, must be done",
        "end to end: not 'Status: done'",
    ]


def test_report_error_sandbox_is_a_finding() -> None:
    rows = [reader_probe.Row("a.pdf", "application/pdf", "done", 1)]
    report = reader_probe.build_report(rows, {"connect": "error", "write": "blocked"})
    assert "- sandbox connect: error" in report
    assert reader_probe.check_report(report) == ["sandbox connect: error, must be blocked"]


def test_main_make_corpus_and_run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        corpus = Path(tmp) / "corpus"
        assert reader_probe.main(["--make-corpus", str(corpus)]) == 0
        assert len(list(corpus.iterdir())) == 5
        files = Path(tmp) / "files"
        files.mkdir()
        (files / "ok.pdf").write_bytes(b"%PDF-1.4 body")
        report = Path(tmp) / "report.md"
        runner = FakeRunner({"application/pdf": OK_RESULT}, dict(BLOCKED_SANDBOX))
        monkeypatch.setattr(reader_probe, "make_compose_runner", lambda *_args: runner)
        argv = [
            "--run", "--compose-file", "c.yml", "--env-file", "e.env", "--project", "p",
            "--files", str(files), "--report", str(report),
        ]
        assert reader_probe.main(argv) == 0
        text = report.read_text(encoding="utf-8")
        assert "| ok.pdf | application/pdf | done | 1 |" in text
        assert reader_probe.check_report(text) == []
        assert reader_probe.main(["--check-report", str(report)]) == 0
    assert capsys.readouterr().err == ""


def test_sandbox_blocked_both() -> None:
    checks = reader_probe.run_sandbox_checks(FakeRunner({}, dict(BLOCKED_SANDBOX)))
    assert checks == {"connect": "blocked", "write": "blocked"}


def test_sandbox_open_connect_and_failed_write_exec() -> None:
    runner = FakeRunner({}, {"connect": "OPEN", "write": None})
    checks = reader_probe.run_sandbox_checks(runner)
    assert checks == {"connect": "OPEN", "write": "error"}


def test_sandbox_open_write() -> None:
    checks = reader_probe.run_sandbox_checks(FakeRunner({}, {"connect": "blocked", "write": "OPEN"}))
    assert checks == {"connect": "blocked", "write": "OPEN"}


def test_good_report_passes() -> None:
    assert reader_probe.check_report(_good_report()) == []


def test_report_findings_lists_timeout_and_open() -> None:
    rows = [reader_probe.Row("slow.pdf", "application/pdf", "timeout", 0)]
    report = reader_probe.build_report(rows, {"connect": "OPEN", "write": "blocked"})
    assert "- slow.pdf: timeout" in report
    assert "- sandbox connect: OPEN" in report
    assert "Status: pending" in report
    problems = reader_probe.check_report(report)
    assert "Status: done" not in report
    assert problems


def test_report_clean_run_has_none_finding() -> None:
    report = _good_report()
    assert "- none" in report
    assert "Status: done" in report


def _mutate_report(report: str, old: str, new: str) -> str:
    assert old in report, old
    return report.replace(old, new)


DECOYS = {
    "open connect": lambda r: _mutate_report(r, "connect: blocked", "connect: OPEN"),
    "open write": lambda r: _mutate_report(r, "write: blocked", "write: OPEN"),
    "no rows": lambda r: _mutate_report(
        r, "| a.pdf | application/pdf | done | 1 |\n", ""
    ),
    "pending": lambda r: _mutate_report(r, "Status: done", "Status: pending"),
    "missing section": lambda r: _mutate_report(
        r, "## Findings\n\n- none\n\n", ""
    ),
}


@pytest.mark.parametrize("name", sorted(DECOYS))
def test_decoy_report_fails(name: str) -> None:
    problems = reader_probe.check_report(DECOYS[name](_good_report()))
    assert len(problems) == 1, problems


def test_check_report_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.md"
        good.write_text(_good_report(), encoding="utf-8")
        bad = Path(tmp) / "bad.md"
        bad.write_text(DECOYS["open write"](_good_report()), encoding="utf-8")
        missing = Path(tmp) / "none.md"
        assert reader_probe.main(["--check-report", str(good)]) == 0
        assert reader_probe.main(["--check-report", str(bad)]) == 1
        assert reader_probe.main(["--check-report", str(missing)]) == 2
    err = capsys.readouterr().err.splitlines()
    assert err == [
        "reader_probe: sandbox write: OPEN, must be blocked",
        f"reader_probe: no such file: {missing}",
    ]

