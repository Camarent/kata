"""Scratch-database helper shared by the core test modules (importable as `support.scratch_db`)."""

from __future__ import annotations

from typing import Any

import psycopg
from kata_core.config import Config
from kata_core.storage.provision import connect

# Names of every test database created in this run, for leak checks in test modules.
CREATED_DB_NAMES: list[str] = []


class ScratchDatabase:
    """A migrated database that tests connect to; closed and dropped at teardown."""

    def __init__(self, cfg: Config, name: str) -> None:
        self.cfg = cfg
        self.name = name
        self._conns: list[psycopg.Connection[Any]] = []

    def connect(self) -> psycopg.Connection[Any]:
        conn = connect(self.cfg, self.name)
        self._conns.append(conn)
        return conn

    def close(self) -> None:
        for conn in self._conns:
            conn.close()
        self._conns.clear()
