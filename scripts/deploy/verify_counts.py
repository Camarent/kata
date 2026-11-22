"""Content-free row counts per table, compared with a counts file (design 4.3 step 5).

  python3 scripts/deploy/verify_counts.py [--database NAME] [--write FILE] [--compare FILE]
                                          [--catalogue-test PATH]

Prints {"<table>": <rows>} as JSON for every table in the public schema. With --write the same
JSON goes to FILE (taken before a dump). With --compare the counts are checked against FILE: on a
difference the output names the tables only (never a value) and the exit code is 1. With
--catalogue-test the row-rule catalogue test file runs with pytest; its failure gives exit 1.
Connection settings come from kata_core.config (KATA_DATABASE_* env, password in the env var named
by [database] password_env).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import psycopg
from kata_core.config import ConfigError, load_config
from kata_core.storage.provision import connect
from psycopg import sql

TABLES_QUERY = (
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
)


def table_counts(database: str | None) -> dict[str, int]:
    """Row count of every public table in `database` (default: the configured one)."""
    with connect(load_config(), database) as conn:
        names = [row[0] for row in conn.execute(TABLES_QUERY).fetchall()]
        counts: dict[str, int] = {}
        for name in names:
            row = conn.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(name))
            ).fetchone()
            counts[name] = int(row[0]) if row else 0
    return counts


def differing_tables(expected: dict[str, int], actual: dict[str, int]) -> list[str]:
    """Names of tables missing on one side or with a different count, sorted."""
    return sorted(
        name for name in expected.keys() | actual.keys() if expected.get(name) != actual.get(name)
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_counts.py")
    parser.add_argument("--database", help="database to count (default: configured name)")
    parser.add_argument("--write", type=Path, help="write the counts JSON to this file")
    parser.add_argument("--compare", type=Path, help="counts file to compare with")
    parser.add_argument("--catalogue-test", type=Path, help="row-rule catalogue test to run")
    args = parser.parse_args(argv)
    try:
        counts = table_counts(args.database)
    except (ConfigError, psycopg.Error) as exc:
        print(f"verify: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(counts, sort_keys=True))
    if args.write:
        args.write.write_text(json.dumps(counts, sort_keys=True) + "\n", encoding="utf-8")
    status = 0
    if args.compare:
        try:
            expected = json.loads(args.compare.read_text(encoding="utf-8"))
            if not isinstance(expected, dict):
                raise TypeError("not a JSON object")
        except (OSError, ValueError, TypeError) as exc:
            print(f"verify: cannot read counts file: {type(exc).__name__}", file=sys.stderr)
            return 1
        diff = differing_tables(expected, counts)
        if diff:
            print("verify: counts differ in: " + ", ".join(diff), file=sys.stderr)
            status = 1
    if args.catalogue_test:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(args.catalogue_test)], check=False
        )
        if result.returncode != 0:
            print("verify: row-rule catalogue test failed", file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
