"""Postgres provisioning: connections from config, database create/drop, migrations.

Every value comes from the loaded config: no default literals live here. The
password is never stored in config; config names the env var that holds it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from kata_core.config import Config, ConfigError

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
MIGRATIONS_TABLE = "schema_migrations"
MIGRATION_GLOB = "[0-9][0-9][0-9][0-9]_*.sql"
# Wire encoding for every session. Without it a server defaulting to SQL_ASCII
# hands text columns back as bytes. Fixed protocol setting, not a config default.
CLIENT_ENCODING = "UTF8"


def _password(cfg: Config) -> str:
    env_name = cfg.get("database", "password_env")
    if env_name not in os.environ:
        raise ConfigError(f"database password env var {env_name} is not set")
    return os.environ[env_name]


def connect(
    cfg: Config,
    name: str | None = None,
    *,
    autocommit: bool = False,
) -> psycopg.Connection[Any]:
    """Open a connection to database `name` (default: [database] name) on the configured server."""
    conninfo = make_conninfo(
        host=cfg.get("database", "host"),
        port=str(cfg.get("database", "port")),
        dbname=name if name is not None else cfg.get("database", "name"),
        user=cfg.get("database", "user"),
        password=_password(cfg),
        client_encoding=CLIENT_ENCODING,
    )
    return psycopg.connect(conninfo, autocommit=autocommit)


def create_database(cfg: Config, name: str) -> None:
    """Create database `name`, issued over a connection to the configured database."""
    with connect(cfg, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def drop_database(cfg: Config, name: str) -> None:
    """Drop database `name` if present. Fails while other sessions still hold it open."""
    with connect(cfg, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


def _migration_files(migrations_dir: Path) -> list[Path]:
    if not migrations_dir.is_dir():
        raise FileNotFoundError(f"migrations dir not found: {migrations_dir}")
    return sorted(migrations_dir.glob(MIGRATION_GLOB), key=lambda path: path.name)


def pending_migrations(
    conn: psycopg.Connection[Any],
    migrations_dir: Path | None = None,
) -> list[str]:
    """Versions in the migrations dir not yet recorded in the migrations table, in name order.

    Read only. A missing migrations table means every version is pending; a missing
    migrations dir raises FileNotFoundError.
    """
    directory = MIGRATIONS_DIR if migrations_dir is None else migrations_dir
    available = [path.stem for path in _migration_files(directory)]
    table_exists = conn.execute("SELECT to_regclass(%s)", (MIGRATIONS_TABLE,)).fetchone()
    if table_exists is None or table_exists[0] is None:
        return available
    rows = conn.execute(
        sql.SQL("SELECT version FROM {}").format(sql.Identifier(MIGRATIONS_TABLE))
    ).fetchall()
    done = {str(row[0]) for row in rows}
    return [version for version in available if version not in done]


def migrate(
    conn: psycopg.Connection[Any],
    migrations_dir: Path = MIGRATIONS_DIR,
) -> list[str]:
    """Apply pending migrations in name order, one transaction each.

    Commits any open transaction on `conn` first. Returns the versions applied by
    this call; a rerun applies nothing.
    """
    conn.commit()
    conn.execute(
        sql.SQL(
            "CREATE TABLE IF NOT EXISTS {} "
            "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        ).format(sql.Identifier(MIGRATIONS_TABLE))
    )
    rows = conn.execute(
        sql.SQL("SELECT version FROM {}").format(sql.Identifier(MIGRATIONS_TABLE))
    ).fetchall()
    conn.commit()
    done = {row[0] for row in rows}

    applied: list[str] = []
    for path in _migration_files(migrations_dir):
        version = path.stem
        if version in done:
            continue
        with conn.transaction():
            # Multi-statement script, sent unparameterised as one batch.
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                sql.SQL("INSERT INTO {} (version) VALUES (%s)").format(
                    sql.Identifier(MIGRATIONS_TABLE)
                ),
                (version,),
            )
        applied.append(version)
    return applied
