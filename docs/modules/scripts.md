---
paths: [scripts/]
summary: Operator CLI for database create, migrate and drop
---
# scripts

## Purpose
Operator tool for provisioning Postgres databases for kata. Thin wrapper over `kata_core.storage.provision`. Config comes from `--config` or `KATA_CONFIG`.

## Public surface
- `scripts/db/kata_db.py:35` `main(argv)` - subcommands `create NAME`, `migrate [--name NAME]`, `drop NAME`.
- `scripts/db/kata_db.py:20` `_parser()` - argparse setup; `--config` at `:24`.
- `scripts/db/kata_db.py:55` `if __name__ == "__main__"` - run as script.

Run from repo root: `PYTHONPATH=core python3 scripts/db/kata_db.py <subcommand>` (see `docs/api.md`, Database CLI).

## Key files
- `scripts/db/kata_db.py` - the only script.

## Invariants and gotchas
- Needs the `core` package on `PYTHONPATH`; it imports `kata_core` directly.
- `drop NAME` is destructive; it drops the database if it exists.
- `migrate` applies only pending migrations; running it twice is a no-op (tested).

## Depends on / used by
- Depends on: `core/kata_core/config.py` (`load_config`, `ConfigError`), `core/kata_core/storage/provision.py` (`connect`, `create_database`, `drop_database`, `migrate`), psycopg.
- Used by: operators by hand; `tests/core/test_provision.py` covers the CLI parser.
