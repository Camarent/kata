"""The exam_mode_analyse lane handler: routed analysis posted to its ticket, failures give it back, no question text logged."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import cast

import pytest
from kata_worker.core_client import CoreClient, CoreError, ExamAnalysisItem
from kata_worker.handlers import exam_mode_analyse as handler
from kata_worker.handlers import load_handlers
from kata_worker.providers.router import Routed, Router

SENTINEL = "SENTINEL-QUESTION-7f3a"
ITEM = ExamAnalysisItem(
    ticket=5,
    session_id=2,
    position=3,
    question=f"Which protocol is {SENTINEL}?",
    choices=("UDP", "TCP"),
    picked=1,
)
REPLY = json.dumps({"topic": "Networks", "concepts": ["ordering"], "outcome": "likely_right"})


@dataclass
class FakeRouter:
    reply: str = REPLY
    error: Exception | None = None
    seen: list[tuple[str, str, str]] = field(default_factory=list)

    def route(self, task_class: str, system: str, user: str) -> Routed:
        self.seen.append((task_class, system, user))
        if self.error is not None:
            raise self.error
        return Routed(reply=self.reply, provider="fake")


@dataclass
class FakeClient:
    reported: list[tuple[int, str | None, list[str], str]] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)

    def report_exam_analysis(
        self, ticket: int, topic: str | None, concepts: list[str], outcome: str
    ) -> None:
        self.reported.append((ticket, topic, list(concepts), outcome))

    def fail_exam_analysis(self, ticket: int) -> None:
        self.failed.append(ticket)


def _run(router: FakeRouter, client: FakeClient) -> None:
    handler.handle_item(ITEM, cast(Router, router), cast(CoreClient, client))


def test_success_reports_topic_concepts_and_outcome_to_the_ticket() -> None:
    client = FakeClient()
    _run(FakeRouter(), client)
    assert client.reported == [(5, "Networks", ["ordering"], "likely_right")]
    assert client.failed == []


def test_router_gets_exam_analyse_class_and_the_question_as_json() -> None:
    router = FakeRouter()
    _run(router, FakeClient())
    task_class, system, user = router.seen[0]
    assert task_class == "exam_analyse"
    assert system == handler.SYSTEM_PROMPT
    assert json.loads(user) == {
        "question": ITEM.question,
        "choices": ["UDP", "TCP"],
        "picked": 1,
    }


def test_fenced_reply_is_accepted() -> None:
    client = FakeClient()
    _run(FakeRouter(reply=f"```json\n{REPLY}\n```"), client)
    assert client.reported == [(5, "Networks", ["ordering"], "likely_right")]


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        '["a", "list"]',
        '{"topic": 3, "concepts": [], "outcome": "unsure"}',
        '{"topic": "x", "concepts": "ordering", "outcome": "unsure"}',
        '{"topic": "x", "concepts": [3], "outcome": "unsure"}',
        '{"topic": "x"}',
    ],
)
def test_unreadable_reply_gives_the_ticket_back(reply: str) -> None:
    client = FakeClient()
    _run(FakeRouter(reply=reply), client)
    assert client.reported == []
    assert client.failed == [5]


def test_model_error_gives_the_ticket_back_and_reports_nothing() -> None:
    client = FakeClient()
    _run(FakeRouter(error=RuntimeError(f"model refused {SENTINEL}")), client)
    assert client.reported == []
    assert client.failed == [5]


def test_core_error_from_router_gives_the_ticket_back() -> None:
    client = FakeClient()
    _run(FakeRouter(error=CoreError("ledger down")), client)
    assert client.failed == [5]
    assert client.reported == []


def test_core_error_from_report_gives_the_ticket_back() -> None:
    class ReportFails(FakeClient):
        def report_exam_analysis(
            self, ticket: int, topic: str | None, concepts: list[str], outcome: str
        ) -> None:
            raise CoreError("output route down")

    client = ReportFails()
    _run(FakeRouter(), client)
    assert client.failed == [5]


def test_question_text_reaches_no_log_at_any_level(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    _run(FakeRouter(), FakeClient())
    _run(FakeRouter(reply=f"not json {SENTINEL}"), FakeClient())
    _run(FakeRouter(error=RuntimeError(f"model refused {SENTINEL}")), FakeClient())
    assert caplog.records
    assert SENTINEL not in caplog.text


def test_question_text_is_not_in_the_posted_output() -> None:
    client = FakeClient()
    _run(FakeRouter(reply=REPLY), client)
    assert all(SENTINEL not in str(entry) for entry in client.reported)


def test_exam_analyse_is_not_a_job_kind() -> None:
    assert not hasattr(handler, "KIND")
    assert "exam_analyse" not in load_handlers()
