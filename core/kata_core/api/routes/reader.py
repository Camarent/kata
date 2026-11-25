"""Reader routes: upload a raw document, read its result, and serve its bytes to the worker.

The upload body is the raw file, not JSON. Refusals run in this order: 409 `reader_disabled` (before
the body is read), 415 type, 413 size, 400 magic bytes, 409 `needs_cloud`; a refused upload stores
nothing. The user id always comes from `current_user`. The file route is for the worker: it uses the
same bearer token as the jobs routes, so it serves only the caller's own documents.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from kata_core.api.deps import Conn, current_user, get_cfg, refuse_needs_cloud
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.jobs.queue import enqueue
from kata_core.reader.job_kinds import READER_EXTRACT_KIND
from kata_core.reader.service import magic_matches
from kata_core.storage.reader_documents import get_document, get_file, insert_document

ACCEPTED_TYPES = ("application/pdf", "image/png", "image/jpeg", "image/webp")

router = APIRouter(prefix="/reader")

Caller = Annotated[AuthContext, Depends(current_user)]
Cfg = Annotated[Config, Depends(get_cfg)]


class DocumentAccepted(BaseModel):
    id: int
    document_id: int


class DocumentOut(BaseModel):
    status: str
    page_count: int | None
    text: str | None
    error: str | None


@router.post("/documents", status_code=202, response_model=DocumentAccepted)
async def upload_document(
    request: Request, ctx: Caller, conn: Conn, cfg: Cfg
) -> DocumentAccepted:
    """Store one raw document and queue its `reader.extract` job. The job input is the document id only.

    409 `reader_disabled` while `[reader] enabled` is off; 415 for a type other than the accepted ones;
    413 once the body passes `[reader] max_file_bytes`; 400 when the magic bytes do not match the type;
    409 `needs_cloud` when the vision task needs a cloud token that is not set. Nothing is stored on a refusal.
    """
    if not cfg.get("reader", "enabled"):
        raise HTTPException(
            status_code=409,
            detail={"code": "reader_disabled", "message": "the reader is off: set [reader] enabled"},
        )
    media_type = request.headers.get("content-type", "")
    if media_type not in ACCEPTED_TYPES:
        raise HTTPException(status_code=415, detail="document type is not accepted")
    max_bytes = int(cfg.get("reader", "max_file_bytes"))
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > max_bytes:
            raise HTTPException(status_code=413, detail="document is too large")
        data.extend(chunk)
    content = bytes(data)
    if not magic_matches(media_type, content):
        raise HTTPException(status_code=400, detail="document bytes do not match its type")
    refuse_needs_cloud(cfg, READER_EXTRACT_KIND)
    document_id = insert_document(
        conn,
        ctx.user_id,
        media_type,
        hashlib.sha256(content).hexdigest(),
        content,
    )
    job_id = enqueue(
        conn,
        ctx.user_id,
        json.dumps({"document_id": document_id}),
        kind=READER_EXTRACT_KIND,
    )
    return DocumentAccepted(id=job_id, document_id=document_id)


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document_status(document_id: int, ctx: Caller, conn: Conn) -> DocumentOut:
    """Status, page count, text and error of the caller's document. 404 for other users' documents."""
    row = get_document(conn, document_id, ctx.user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    return DocumentOut(**row)


@router.get("/documents/{document_id}/file")
def get_document_file(document_id: int, ctx: Caller, conn: Conn) -> Response:
    """The raw bytes of the caller's document, for the worker, with its stored media type.

    404 for other users' documents and for documents whose content is already gone.
    """
    found = get_file(conn, document_id, ctx.user_id)
    if found is None:
        raise HTTPException(status_code=404, detail="document not found")
    media_type, content = found
    return Response(content=content, media_type=media_type)
