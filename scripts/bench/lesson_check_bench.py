"""Lesson-check benchmark: seed synthetic cases into a scratch database, run check_lesson, report.

Only the fake embedder runs here: a config whose [retrieval] embedder is not 'fake' is refused
(exit 2) before any database work, so no model loads. The scratch database is created per run and
dropped in a finally, also on Ctrl-C. The report holds labels and numbers only, never entry text.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kata_core.config import Config, ConfigError, load_config
from kata_core.lesson_check.checker import check_lesson
from kata_core.retrieval.embedder import load_embedder
from kata_core.retrieval.retriever import Retriever
from kata_core.retrieval.store import add_entry
from kata_core.storage.concepts import create_concept, set_concept_mark
from kata_core.storage.provision import connect, create_database, drop_database, migrate
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from kata_core.storage.users import create_user

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CASES = SCRIPT_DIR / "cases.json"
REQUIRED_EMBEDDER = "fake"
EXIT_REFUSED = 2
BENCH_CATEGORY = "bench"
BENCH_TOPIC = "bench"
BENCH_USER = "bench"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from scoring import Cases, Score, load_cases, score


class EmbedderNotFakeError(ValueError):
    """The config asks for an embedder other than the offline fake one."""


@dataclass(frozen=True)
class CaseResult:
    label: str
    expected: str
    got: str
    source: str
    hits: int


@dataclass(frozen=True)
class BenchResult:
    score: Score
    cases: tuple[CaseResult, ...]
    thresholds: dict[str, float | int]
    embedder: str


def scratch_db_name(cfg: Config) -> str:
    """'<database.name>_b<uuid8>': the prefix keeps bench databases apart from test ones."""
    return f"{cfg.get('database', 'name')}_b{uuid.uuid4().hex[:8]}"


def _refuse_unless_fake(cfg: Config) -> None:
    embedder = str(cfg.get("retrieval", "embedder"))
    if embedder != REQUIRED_EMBEDDER:
        raise EmbedderNotFakeError(
            f"bench refuses embedder {embedder!r}: only {REQUIRED_EMBEDDER!r} runs in this phase"
        )


def _seed(conn: Any, cfg: Config, cases: Cases) -> tuple[int, list[int]]:
    """Insert user, taxonomy, concepts, marks and entries; return user id and concept ids in case order."""
    user_id = create_user(conn, BENCH_USER)
    category_id = ensure_category(conn, BENCH_CATEGORY)
    topic_id = ensure_topic(conn, category_id, BENCH_TOPIC)
    embedder = load_embedder(cfg)
    for entry in cases.entries:
        add_entry(conn, embedder, None, entry.source_ref, entry.body)
    concept_ids: list[int] = []
    for concept in cases.concepts:
        concept_id = create_concept(conn, topic_id, concept.label)
        if concept.mark is not None:
            set_concept_mark(conn, user_id, concept_id, concept.mark)
        concept_ids.append(concept_id)
    return user_id, concept_ids


def run_bench(cfg: Config, cases: Cases) -> BenchResult:
    """Run every case against a fresh scratch database and score the states against the expectations."""
    _refuse_unless_fake(cfg)
    name = scratch_db_name(cfg)
    create_database(cfg, name)
    try:
        with connect(cfg, name) as conn:
            migrate(conn)
            user_id, concept_ids = _seed(conn, cfg, cases)
            retriever = Retriever.from_config(conn, cfg)
            checks = check_lesson(conn, retriever, cfg, user_id, concept_ids)
    finally:
        drop_database(cfg, name)
    results = tuple(
        CaseResult(
            label=concept.label,
            expected=concept.expected,
            got=check.state,
            source=check.source,
            hits=len(check.evidence) if isinstance(check.evidence, tuple) else 0,
        )
        for concept, check in zip(cases.concepts, checks, strict=True)
    )
    scored = score([r.expected for r in results], [r.got for r in results])
    thresholds: dict[str, float | int] = {
        "min_score": float(cfg.get("lesson_check", "min_score")),
        "known_hits": int(cfg.get("lesson_check", "known_hits")),
        "search_limit": int(cfg.get("lesson_check", "search_limit")),
    }
    return BenchResult(
        score=scored,
        cases=results,
        thresholds=thresholds,
        embedder=load_embedder(cfg).name,
    )


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def render_markdown(result: BenchResult) -> str:
    s = result.score
    lines = [
        "# Lesson-check benchmark",
        "",
        "| metric | value |",
        "| --- | --- |",
        f"| accuracy | {_pct(s.accuracy)} |",
        f"| abstain_rate | {_pct(s.abstain_rate)} |",
        f"| abstain_precision | {_pct(s.abstain_precision)} |",
        f"| total | {s.total} |",
        f"| embedder | {result.embedder} |",
        "",
        "| state | expected count |",
        "| --- | --- |",
    ]
    lines += [f"| {state} | {count} |" for state, count in s.per_state.items()]
    lines += ["", "| threshold | value |", "| --- | --- |"]
    lines += [f"| {key} | {value} |" for key, value in result.thresholds.items()]
    return "\n".join(lines) + "\n"


def render_text(result: BenchResult) -> str:
    s = result.score
    lines = [
        (
            f"accuracy={_pct(s.accuracy)} abstain_rate={_pct(s.abstain_rate)} "
            f"abstain_precision={_pct(s.abstain_precision)} total={s.total}"
        ),
        f"embedder={result.embedder}",
        "per_state " + " ".join(f"{state}={count}" for state, count in s.per_state.items()),
        "thresholds " + " ".join(f"{key}={value}" for key, value in result.thresholds.items()),
    ]
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the lesson-check benchmark on the fake embedder.")
    parser.add_argument("--config", default=None, help="config file (default: env KATA_CONFIG)")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="cases file (default: cases.json beside this script)")
    parser.add_argument("--format", dest="fmt", choices=("text", "markdown"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
        cases = load_cases(Path(args.cases))
        result = run_bench(cfg, cases)
    except (EmbedderNotFakeError, ConfigError) as exc:
        print(f"lesson_check_bench: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    render = render_markdown if args.fmt == "markdown" else render_text
    sys.stdout.write(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
