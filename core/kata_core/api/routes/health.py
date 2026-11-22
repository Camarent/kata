"""Deep health: GET /v1/health/deep checks the database and that every migration file is applied.

Unauthenticated, so the answer carries only check names and booleans: never row content, config
values or driver error text. 200 when every check passes, 503 with the failed check names otherwise.
"""

from __future__ import annotations

from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from psycopg import sql

from kata_core.api.deps import get_cfg
from kata_core.config import Config
from kata_core.storage.provision import (
    MIGRATION_GLOB,
    MIGRATIONS_DIR,
    MIGRATIONS_TABLE,
    connect,
)

router = APIRouter(prefix="/v1/health")

Cfg = Annotated[Config, Depends(get_cfg)]


def _migrations_current(conn: psycopg.Connection[Any]) -> bool:
    """True when every migration file on disk is recorded as applied."""
    if not MIGRATIONS_DIR.is_dir():
        return False
    try:
        rows = conn.execute(
            sql.SQL("SELECT version FROM {}").format(sql.Identifier(MIGRATIONS_TABLE))
        ).fetchall()
    except psycopg.errors.UndefinedTable:
        return False
    applied = {str(row[0]) for row in rows}
    expected = {path.stem for path in MIGRATIONS_DIR.glob(MIGRATION_GLOB)}
    return expected <= applied


def _run_checks(cfg: Config) -> dict[str, bool]:
    """Each check result; a database that cannot be reached fails both checks."""
    try:
        with connect(cfg) as conn:
            conn.execute("SELECT 1")
            return {"db": True, "migrations": _migrations_current(conn)}
    except (psycopg.Error, OSError):
        return {"db": False, "migrations": False}


@router.get("/deep")
def deep_health(cfg: Cfg) -> JSONResponse:
    checks = _run_checks(cfg)
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        return JSONResponse(
            status_code=503,
            content={"status": "fail", "failed": failed, "checks": checks},
        )
    return JSONResponse(status_code=200, content={"status": "ok", "checks": checks})
