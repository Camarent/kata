"""[quiz] limits and the quiz_generate task class in the example config."""

from __future__ import annotations

from kata_core.config import EXAMPLE_PATH, load_config
from kata_core.jobs.needs_cloud import TASK_CLASSES

QUIZ_TASK_CLASS = "quiz_generate"
MINI_QUIZ_MAX = 5


def test_example_config_parses_quiz_section() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("quiz", "max_fetch_bytes") > 0
    assert cfg.get("quiz", "max_question_chars") > 0
    assert cfg.get("quiz", "max_questions_per_source") > 0


def test_mini_quiz_size_at_most_five() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    size = cfg.get("quiz", "mini_quiz_size")
    assert 0 < size <= MINI_QUIZ_MAX


def test_quiz_generate_routed_local_then_anthropic() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("routing", QUIZ_TASK_CLASS) == "local,anthropic"


def test_quiz_generate_in_needs_cloud_task_classes() -> None:
    assert QUIZ_TASK_CLASS in TASK_CLASSES
