"""Auth routes: enrol a device with a code, who am I, revoke one of my devices."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from kata_core.api.deps import current_user, get_cfg, get_conn
from kata_core.auth.service import AuthContext, redeem, revoke
from kata_core.config import Config
from kata_core.storage.devices import list_devices
from kata_core.storage.users import get_user

router = APIRouter(prefix="/auth")

Conn = Annotated[psycopg.Connection[Any], Depends(get_conn, scope="function")]


class EnrolRequest(BaseModel):
    code: str
    label: str


class EnrolResponse(BaseModel):
    token: str
    expires_in: int  # noqa: V107 - serialised to JSON by FastAPI, no code reads it


class MeResponse(BaseModel):
    user_id: int
    name: str


@router.post("/enrol", response_model=EnrolResponse)
def enrol(
    body: EnrolRequest,
    conn: Conn,
    cfg: Annotated[Config, Depends(get_cfg)],
) -> EnrolResponse:
    """Redeem an enrolment code once; return the raw device token (shown once)."""
    token = redeem(conn, body.code, body.label, datetime.now(UTC))
    if token is None:
        raise HTTPException(status_code=401, detail="invalid or used enrolment code")
    return EnrolResponse(token=token, expires_in=int(cfg.get("auth", "token_ttl_seconds")))


@router.get("/me", response_model=MeResponse)
def me(ctx: Annotated[AuthContext, Depends(current_user)], conn: Conn) -> MeResponse:
    user = get_user(conn, ctx.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="user no longer exists")
    return MeResponse(user_id=user[0], name=user[1])


@router.delete("/devices/{device_id}", status_code=204)
def revoke_own_device(
    device_id: int,
    ctx: Annotated[AuthContext, Depends(current_user)],
    conn: Conn,
) -> Response:
    """Revoke one of the caller's own devices. 404 for unknown, foreign or already revoked ones."""
    owned = {dev_id for dev_id, _label, revoked in list_devices(conn, ctx.user_id) if not revoked}
    if device_id not in owned or not revoke(conn, device_id):
        raise HTTPException(status_code=404, detail="device not found")
    return Response(status_code=204)
