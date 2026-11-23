"""Event routes: POST /v1/events ingests a batch and piggybacks the caller's pending messages;
GET /v1/messages delivers them on their own.

The user and device ids always come from `current_user`, never from the body or the query.
One bad event is reported in `results` with its reason; it never fails the batch.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.delivery.messages import Message, deliver_pending, enqueue_decisions
from kata_core.events.envelope import Rejection, validate
from kata_core.events.store import ingest
from kata_core.policy.engine import EventKind, Policy

router = APIRouter()

Caller = Annotated[AuthContext, Depends(current_user)]

MAX_EVENTS_PER_BATCH = 100
TERMINAL_ERROR_TYPE = "terminal.error"


class EventsIn(BaseModel):
    events: list[Any] = Field(max_length=MAX_EVENTS_PER_BATCH)


class EventResultOut(BaseModel):
    event_id: str | None
    status: Literal["accepted", "duplicate", "rejected"]
    reason: str | None = None


class MessageOut(BaseModel):
    id: int
    kind: str
    body: dict[str, Any]
    created_at: str


class EventsOut(BaseModel):
    results: list[EventResultOut]
    messages: list[MessageOut]


class MessagesOut(BaseModel):
    messages: list[MessageOut]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _clock(request: Request) -> Callable[[], datetime]:
    """`app.state.clock` when set (tests freeze time there), else the real UTC clock."""
    clock: Callable[[], datetime] | None = getattr(request.app.state, "clock", None)
    return clock if clock is not None else _utc_now


def _policy(request: Request) -> Policy:
    """The app's one Policy, created on first use and cached on `app.state`."""
    policy: Policy | None = getattr(request.app.state, "policy", None)
    if policy is None:
        cfg: Config = request.app.state.cfg
        policy = Policy.from_config(cfg, _clock(request))
        request.app.state.policy = policy
    return policy


def _event_kind(event_type: str) -> EventKind:
    """Kinds reaching here passed `validate`: only terminal.* and editor.* types."""
    return "error" if event_type == TERMINAL_ERROR_TYPE else "ok"


def _raw_event_id(raw: Any) -> str | None:
    if isinstance(raw, Mapping) and isinstance(raw.get("event_id"), str):
        return str(raw["event_id"])
    return None


def _message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        kind=message.kind,
        body=message.body,
        created_at=message.created_at.isoformat(),
    )


@router.post("/v1/events", response_model=EventsOut, response_model_exclude_unset=True)
def post_events(request: Request, ctx: Caller, conn: Conn, body: EventsIn) -> EventsOut:
    """Ingest one batch for the caller. Only accepted events reach the policy; its decisions
    are queued, then the caller's pending messages are delivered in this response.

    `reason` is only sent for rejected events (`exclude_unset`), so accepted results omit it.
    """
    now = _clock(request)()
    policy = _policy(request)
    results: list[EventResultOut] = []
    for raw in body.events:
        checked = validate(raw, now)
        if isinstance(checked, Rejection):
            results.append(
                EventResultOut(
                    event_id=_raw_event_id(raw), status="rejected", reason=checked.reason
                )
            )
            continue
        outcome = ingest(conn, ctx.user_id, ctx.device_id, checked, now)
        results.append(EventResultOut(event_id=checked.event_id, status=outcome))
        if outcome == "accepted":
            decisions = policy.observe(
                str(ctx.user_id), _event_kind(checked.type), checked.occurred_at
            )
            enqueue_decisions(conn, decisions, now)
    messages = deliver_pending(conn, ctx.user_id, now)
    return EventsOut(results=results, messages=[_message_out(m) for m in messages])


@router.get("/v1/messages", response_model=MessagesOut)
def get_messages(request: Request, ctx: Caller, conn: Conn) -> MessagesOut:
    """Deliver and return the caller's pending messages, oldest first. Each is returned once."""
    messages = deliver_pending(conn, ctx.user_id, _clock(request)())
    return MessagesOut(messages=[_message_out(m) for m in messages])
