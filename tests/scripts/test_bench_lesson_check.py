"""Lesson-check benchmark runner against a live Postgres: determinism, abstain, scratch DB cleanup.

Every run makes its own scratch database (named from a test-chosen uuid) and drops it again.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any

import pytest
from kata_core.config import Config, load_config
from kata_core.storage.provision import connect

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).parents[2]
BENCH_PATH = REPO_ROOT / "scripts" / "bench" / "lesson_check_bench.py"
CASES_PATH = REPO_ROOT / "scripts" / "bench" / "cases.json"
MODULE_NAME = "lesson_check_bench_under_test"


def _load_bench() -> ModuleType:
    spec = importlib.util.spec_from_file_location(MODULE_NAME, BENCH_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(MODULE_NAME, None)
        raise
    return module


bench = _load_bench()


@pytest.fixture
def cfg() -> Config:
    return load_config()


@pytest.fixture
def cases() -> Any:
    from scoring import load_cases  # importable once the bench module put its dir on sys.path

    return load_cases(CASES_PATH)


def _override(cfg: Config, section: str, key: str, value: object) -> Config:
    sections = {name: dict(values) for name, values in cfg.sections.items()}
    sections[section][key] = value
    return Config(sections={name: MappingProxyType(values) for name, values in sections.items()})


def _database_exists(cfg: Config, name: str) -> bool:
    with connect(cfg, autocommit=True) as conn:
        row = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
    return row is not None


@pytest.fixture
def fixed_name(cfg: Config, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Pin the scratch database name of this test so the cleanup check looks at exactly that database."""
    name = f"{cfg.get('database', 'name')}_b{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(bench, "scratch_db_name", lambda _cfg: name)
    yield name
    assert not _database_exists(cfg, name), f"scratch database left behind: {name}"


def test_run_bench_twice_gives_equal_results(cfg: Config, cases: Any) -> None:
    first = bench.run_bench(cfg, cases)
    second = bench.run_bench(cfg, cases)
    assert first == second


def test_every_case_has_a_result(cfg: Config, cases: Any) -> None:
    result = bench.run_bench(cfg, cases)
    assert [case.label for case in result.cases] == [concept.label for concept in cases.concepts]
    assert result.score.total == len(cases.concepts)


def test_abstain_cases_come_back_abstain(cfg: Config, cases: Any) -> None:
    result = bench.run_bench(cfg, cases)
    abstain_cases = [concept for concept in cases.concepts if concept.expected == "abstain"]
    assert abstain_cases, "cases.json needs labels with no entry"
    by_label = {case.label: case for case in result.cases}
    for concept in abstain_cases:
        assert by_label[concept.label].got == "abstain", concept.label


def test_scratch_database_is_dropped_after_run(cfg: Config, cases: Any, fixed_name: str) -> None:
    result = bench.run_bench(cfg, cases)
    assert result.score.total == len(cases.concepts)
    assert not _database_exists(cfg, fixed_name)


def test_scratch_database_is_dropped_when_run_fails(
    cfg: Config, cases: Any, fixed_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(bench, "check_lesson", _boom)
    with pytest.raises(KeyboardInterrupt):
        bench.run_bench(cfg, cases)
    assert not _database_exists(cfg, fixed_name)


def test_min_score_above_every_score_makes_unmarked_cases_abstain(cfg: Config, cases: Any) -> None:
    strict = _override(cfg, "lesson_check", "min_score", 1e9)
    result = bench.run_bench(strict, cases)
    unmarked = [(concept, case) for concept, case in zip(cases.concepts, result.cases, strict=True) if concept.mark is None]
    marked = [(concept, case) for concept, case in zip(cases.concepts, result.cases, strict=True) if concept.mark is not None]
    assert unmarked and marked
    abstained = sum(1 for _, case in unmarked if case.got == "abstain")
    assert abstained / len(unmarked) == pytest.approx(1.0)
    assert result.score.abstain_rate == pytest.approx(len(unmarked) / len(cases.concepts))
    # marks win over retrieval, so marked cases keep their state under any threshold
    assert all(case.got == concept.expected for concept, case in marked)


def test_main_refuses_non_fake_embedder(
    cfg: Config, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    model_cfg = _override(cfg, "retrieval", "embedder", "model")
    monkeypatch.setattr(bench, "load_config", lambda _path=None: model_cfg)
    code = bench.main(["--cases", str(CASES_PATH)])
    assert code == 2
    assert "refuses" in capsys.readouterr().err


def test_rendered_report_has_no_entry_text(cfg: Config, cases: Any) -> None:
    result = bench.run_bench(cfg, cases)
    for render in (bench.render_markdown, bench.render_text):
        text = render(result)
        for entry in cases.entries:
            assert entry.body not in text
        assert result.embedder in text
