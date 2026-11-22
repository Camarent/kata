"""Migration CLI: apply pending schema migrations, or report them with --check.

    python -m kata_core.migrate          apply pending migrations, exit 0
    python -m kata_core.migrate --check  list pending migrations, apply nothing;
                                         exit 0 when none are pending, 1 otherwise

Config comes from KATA_CONFIG. A config or database error exits 1.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

import psycopg

from kata_core.config import Config, ConfigError, load_config
from kata_core.storage.provision import connect, migrate, pending_migrations

log = logging.getLogger(__name__)


def run(cfg: Config, *, check: bool, database: str | None = None) -> int:
    """Apply pending migrations on `database` (default: configured name), or only report them."""
    with connect(cfg, database) as conn:
        if check:
            missing = pending_migrations(conn)
            for version in missing:
                print(f"pending: {version}")
            if missing:
                print(f"{len(missing)} migration(s) pending")
                return 1
            print("all migrations applied")
            return 0
        applied = migrate(conn)
        for version in applied:
            print(f"applied: {version}")
        print(f"{len(applied)} migration(s) applied")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="python -m kata_core.migrate")
    parser.add_argument(
        "--check",
        action="store_true",
        help="list pending migrations and exit 1 if any; apply nothing",
    )
    args = parser.parse_args(argv)
    try:
        cfg = load_config()
        return run(cfg, check=args.check)
    except ConfigError as exc:
        log.error("config: %s", exc)
        return 1
    except psycopg.Error as exc:
        log.error("database: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
