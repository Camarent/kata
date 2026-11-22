"""Replay a tombstone file on a restored database (design 12.2), so a restore cannot bring back
revoked tokens or deleted data.

  python3 scripts/deploy/replay_tombstone.py --database NAME FILE

File format: append-only text, one entry per line, `<kind> <id> <action> <UTC time>`, e.g.
`device 42 revoked 2026-11-01T10:00:00Z`. Ids only, never content. Blank lines and lines starting
with `#` are skipped. Actions:
  device revoked    set revoked_at on the device row if still unset
  user deleted      delete the user row (children cascade)
  user disabled     treated as deleted until the schema has a disabled flag
Entries of a kind with no table yet (source, document) are counted and skipped. A malformed line
fails the replay (exit 1) naming its line number. Replay is idempotent.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import psycopg
from kata_core.config import ConfigError, load_config
from kata_core.storage.provision import connect

STATEMENTS = {
    ("device", "revoked"): (
        "UPDATE devices SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL"
    ),
    ("user", "deleted"): "DELETE FROM users WHERE id = %s",
    ("user", "disabled"): "DELETE FROM users WHERE id = %s",
}
SKIPPED_KINDS = {"source", "document"}
FIELD_COUNT = 4


def parse(text: str) -> list[tuple[int, str, int, str]]:
    """Entries as (line number, kind, id, action); ValueError names the bad line number."""
    entries = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != FIELD_COUNT or not fields[1].isdigit():
            raise ValueError(f"line {number}: malformed tombstone entry")
        kind, ident, action = fields[0], int(fields[1]), fields[2]
        if (kind, action) not in STATEMENTS and kind not in SKIPPED_KINDS:
            raise ValueError(f"line {number}: unknown entry kind or action")
        entries.append((number, kind, ident, action))
    return entries


def replay(database: str | None, path: Path) -> tuple[int, int]:
    """Apply the file to `database`; returns (entries applied, entries skipped)."""
    entries = parse(path.read_text(encoding="utf-8"))
    applied = skipped = 0
    with connect(load_config(), database) as conn:
        for _number, kind, ident, action in entries:
            statement = STATEMENTS.get((kind, action))
            if statement is None:
                skipped += 1
                continue
            conn.execute(statement, (ident,))
            applied += 1
        conn.commit()
    return applied, skipped


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="replay_tombstone.py")
    parser.add_argument("--database", help="restored database (default: configured name)")
    parser.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    try:
        applied, skipped = replay(args.database, args.file)
    except (ValueError, OSError) as exc:
        print(f"tombstone: {exc}", file=sys.stderr)
        return 1
    except (ConfigError, psycopg.Error) as exc:
        print(f"tombstone: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"tombstone: {applied} applied, {skipped} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
