"""Quiz routes: request a source, serve the mini quiz, apply the answer.

The user id always comes from `current_user`, never from the body or the query. The answer is checked
here against the stored `answer_index`; the client sends only its choice. A correct answer moves a New
concept to Learning (D19); it never sets Known (D40) and a wrong answer changes nothing.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user, get_cfg
from kata_core.api.routes.jobs import EnqueueResponse
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.jobs.queue import enqueue
from kata_core.quiz.allowlist import classify
from kata_core.quiz.job_kinds import QUIZ_FETCH_KIND
from kata_core.storage.concepts import concept_mark_states, concept_visible, set_concept_mark
from kata_core.storage.quiz import MINI_QUIZ_MAX, get_question, list_mini_questions

NEW_STATE = "new"
LEARNING_STATE = "learning"
MAX_URL_CHARS = 2000
MAX_CHOICE_INDEX = 100

router = APIRouter(prefix="/quiz")

Caller = Annotated[AuthContext, Depends(current_user)]
Cfg = Annotated[Config, Depends(get_cfg)]


class SourceIn(BaseModel):
    url: str = Field(min_length=1, max_length=MAX_URL_CHARS)


class QuestionOut(BaseModel):
    id: int
    question: str
    choices: list[str]
    source_url: str
    tier: int
    licence: str


class AnswerIn(BaseModel):
    question_id: int
    choice: int = Field(ge=0, le=MAX_CHOICE_INDEX)
    concept_id: int


class AnswerOut(BaseModel):
    correct: bool
    state: str


@router.post("/sources", status_code=202, response_model=EnqueueResponse)
def request_source(body: SourceIn, ctx: Caller, conn: Conn) -> EnqueueResponse:
    """Queue a fetch of an allowlisted source. 400 when the URL is not on the allowlist, before any fetch."""
    if classify(body.url) is None:
        raise HTTPException(status_code=400, detail="source is not on the allowlist")
    job_id = enqueue(conn, ctx.user_id, json.dumps({"url": body.url}), kind=QUIZ_FETCH_KIND)
    return EnqueueResponse(id=job_id)


@router.get("/mini", response_model=list[QuestionOut])
def get_mini_quiz(
    _caller: Caller,
    conn: Conn,
    cfg: Cfg,
    limit: Annotated[int | None, Query(ge=1, le=MINI_QUIZ_MAX)] = None,
) -> list[QuestionOut]:
    """Up to `mini_quiz_size` cached questions (at most 5). No answer index, with the source link, tier and licence."""
    size = limit if limit is not None else cfg.get("quiz", "mini_quiz_size")
    return [QuestionOut(**row) for row in list_mini_questions(conn, size)]


@router.post("/answer", response_model=AnswerOut)
def post_answer(body: AnswerIn, ctx: Caller, conn: Conn) -> AnswerOut:
    """Check one answer in core. A correct answer moves the concept from New to Learning only.

    404 when the question or the concept is not visible to the caller; 422 when the choice is not one of the question's choices.
    """
    question = get_question(conn, body.question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="question not found")
    if body.choice >= len(question["choices"]):
        raise HTTPException(status_code=422, detail="choice is not one of the question's choices")
    if not concept_visible(conn, ctx.user_id, body.concept_id):
        raise HTTPException(status_code=404, detail="concept not found")
    correct = body.choice == question["answer_index"]
    state = concept_mark_states(conn, ctx.user_id, [body.concept_id]).get(
        body.concept_id, NEW_STATE
    )
    if correct and state == NEW_STATE:
        set_concept_mark(conn, ctx.user_id, body.concept_id, LEARNING_STATE, evidence="quiz answer")
        state = LEARNING_STATE
    return AnswerOut(correct=correct, state=state)
