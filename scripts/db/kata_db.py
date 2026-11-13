"""Database admin CLI: create, migrate, drop.

Config comes from --config or env KATA_CONFIG; the password from the env var the
config names in [database] password_env. Run from the repo root with the core
package on the path:
    PYTHONPATH=core python3 scripts/db/kata_db.py migrate
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import psycopg
from kata_core.config import ConfigError, load_config
from kata_core.storage.provision import connect, create_database, drop_database, migrate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kata_db", description="Create, migrate or drop kata databases."
    )
    parser.add_argument("--config", help="config file (default: env KATA_CONFIG)")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="create a database")
    create.add_argument("name")
    migrate_cmd = sub.add_parser("migrate", help="apply pending migrations")
    migrate_cmd.add_argument("--name", help="database to migrate (default: configured name)")
    drop = sub.add_parser("drop", help="drop a database if present")
    drop.add_argument("name")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
        if args.command == "create":
            create_database(cfg, args.name)
            print(f"created {args.name}")
        elif args.command == "drop":
            drop_database(cfg, args.name)
            print(f"dropped {args.name}")
        else:
            with connect(cfg, args.name) as conn:
                applied = migrate(conn)
            print(f"applied {len(applied)} migration(s): {', '.join(applied) or 'none'}")
    except (ConfigError, psycopg.Error) as exc:
        print(f"kata_db: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
