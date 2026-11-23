"""Real-dojo smoke: build a synthetic course with build_course_dir, then check the built artifacts.

Opt-in and started by hand only: never run by check-all.sh or CI. Refused (exit 2, no run) unless
KATA_TEST_DOJO is set to an executable file. Optional KATA_TEST_DOJO_WASM and KATA_TEST_DOJO_WEB
are passed to `dojo build` when set. The run works in a temp dir that is removed at the end.
Eight synthetic drafts go in; the one with an empty answer must be dropped by the probe. Exit 0
only when every check passes; the built file list and sizes are printed.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kata_core.config import Config, load_config
from kata_core.trainer.build import BuildRejected, BuiltCourse, build_course_dir
from kata_core.trainer.cli import TrainerCli, TrainerError
from kata_core.trainer.dojo_cli import DojoTrainerCli

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = REPO_ROOT / "config" / "kata.example.toml"
GATE_ENV = "KATA_TEST_DOJO"
WASM_ENV = "KATA_TEST_DOJO_WASM"
WEB_ENV = "KATA_TEST_DOJO_WEB"
COURSE_ID = "smoke-course"
COURSE_TITLE = "Smoke course"
# Seven good drafts and one with an empty answer, which the probe must drop.
SYNTHETIC_DRAFTS: list[dict[str, Any]] = [
    {"concept_id": 1, "prompt": "The capital of Italy is ___.", "answer": "Rome"},
    {"concept_id": 2, "prompt": "The capital of France is ___.", "answer": "Paris"},
    {"concept_id": 3, "prompt": "The capital of Spain is ___.", "answer": "Madrid"},
    {"concept_id": 4, "prompt": "The capital of Germany is ___.", "answer": "Berlin"},
    {"concept_id": 5, "prompt": "The capital of Japan is ___.", "answer": "Tokyo"},
    {"concept_id": 6, "prompt": "The capital of Egypt is ___.", "answer": "Cairo"},
    {"concept_id": 7, "prompt": "The capital of Peru is ___.", "answer": "Lima"},
    {"concept_id": 8, "prompt": "The capital of Chile is ___.", "answer": ""},
]
EXPECTED_KEPT = 7
EXPECTED_DROPPED = 1
REQUIRED_FILES = ("index.html", "data/content.json", "manifest.json")
TIMEOUT_SECONDS = 60.0
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2


class SmokeFailed(Exception):
    """A built course that does not match what the smoke expects."""


def _refuse(message: str) -> int:
    print(message, file=sys.stderr)
    return EXIT_REFUSED


def run_smoke(cli: TrainerCli, cfg: Config) -> BuiltCourse:
    """Build the synthetic course with `cli` and check it; raise SmokeFailed when a check fails."""
    built = build_course_dir(cli, cfg, COURSE_ID, COURSE_TITLE, list(SYNTHETIC_DRAFTS))
    _check(built, int(cfg.get("trainer", "max_artifact_bytes")))
    return built


def _check(built: BuiltCourse, max_bytes: int) -> None:
    missing = [name for name in REQUIRED_FILES if name not in built.artifacts]
    if missing:
        raise SmokeFailed(f"built course lacks {', '.join(missing)}")
    if len(built.kept) != EXPECTED_KEPT or len(built.item_ids) != EXPECTED_KEPT:
        raise SmokeFailed(f"expected {EXPECTED_KEPT} items kept, got {len(built.item_ids)}")
    if len(built.dropped) != EXPECTED_DROPPED:
        raise SmokeFailed(f"expected {EXPECTED_DROPPED} item dropped, got {len(built.dropped)}")
    total = sum(len(data) for _, data in built.artifacts.values())
    if total > max_bytes:
        raise SmokeFailed(f"artifacts are {total} bytes, over the {max_bytes} byte cap")
    content = json.loads(built.artifacts["data/content.json"][1])
    if sorted(item["prompt"] for item in content) != sorted(d["prompt"] for d in built.kept):
        raise SmokeFailed("data/content.json does not hold the kept prompts")


def _report(built: BuiltCourse) -> None:
    for item_id in built.item_ids:
        print(f"added {item_id}")
    for item_id, message in built.dropped.items():
        print(f"dropped {item_id}: {message}")
    for name, (_, data) in sorted(built.artifacts.items()):
        print(f"{name} {len(data)} bytes")


def main(env: Mapping[str, str]) -> int:
    """Run the real-dojo smoke against the binary named in KATA_TEST_DOJO. Returns the exit code."""
    binary = env.get(GATE_ENV, "")
    if not binary:
        return _refuse(f"refused: set {GATE_ENV} to the path of an executable dojo binary")
    if not (Path(binary).is_file() and os.access(binary, os.X_OK)):
        return _refuse(f"refused: {GATE_ENV} is not an executable file: {binary}")
    cli = DojoTrainerCli(
        argv_prefix=[binary],
        timeout=TIMEOUT_SECONDS,
        wasm=env.get(WASM_ENV, ""),
        web=env.get(WEB_ENV, ""),
    )
    try:
        built = run_smoke(cli, load_config(EXAMPLE_CONFIG, env={}))
    except (TrainerError, BuildRejected, SmokeFailed) as exc:
        print(f"dojo smoke failed: {exc}", file=sys.stderr)
        return EXIT_FAILED
    _report(built)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(os.environ))
