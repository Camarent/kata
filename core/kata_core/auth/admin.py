"""Admin CLI: create users, issue enrolment codes, revoke devices.

    python -m kata_core.auth.admin create-user NAME
    python -m kata_core.auth.admin enrol USER_NAME
    python -m kata_core.auth.admin mint-mcp-token USER_NAME LABEL
    python -m kata_core.auth.admin revoke DEVICE_ID

Config comes from KATA_CONFIG. `enrol` prints the raw code once; it is not stored.
There is no self sign-up path: users exist only because an admin ran create-user.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import psycopg

from kata_core.auth.service import issue_scoped_token, new_enrolment, revoke
from kata_core.config import Config, ConfigError, load_config
from kata_core.storage.provision import connect
from kata_core.storage.users import create_user, list_users


class AdminError(Exception):
    """A command that cannot be done: unknown user, unknown or already revoked device."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kata_core.auth.admin", description="Kata admin CLI.")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="create a user named NAME")
    create.add_argument("name")
    enrol = commands.add_parser("enrol", help="issue an enrolment code for USER_NAME")
    enrol.add_argument("user_name")
    mint = commands.add_parser("mint-mcp-token", help="issue an MCP token for USER_NAME")
    mint.add_argument("user_name")
    mint.add_argument("label")
    revoke_cmd = commands.add_parser("revoke", help="revoke device DEVICE_ID")
    revoke_cmd.add_argument("device_id", type=int)
    return parser


def _user_id_named(conn: psycopg.Connection[Any], name: str) -> int:
    """Return the id of user `name`. Raises AdminError if no such user."""
    matches = [uid for uid, user in list_users(conn) if user == name]
    if not matches:
        raise AdminError(f"no user named {name}")
    return matches[0]


def run(
    conn: psycopg.Connection[Any],
    argv: Sequence[str],
    cfg: Config,
    now: datetime,
) -> str:
    """Run one admin command on `conn`. Return the text to print. Raises AdminError."""
    args = build_parser().parse_args(argv)
    if args.command == "create-user":
        user_id = create_user(conn, args.name)
        return f"created user {user_id} {args.name}"
    if args.command == "enrol":
        code = new_enrolment(conn, _user_id_named(conn, args.user_name), cfg, now)
        return f"enrolment code for {args.user_name} (shown once): {code}"
    if args.command == "mint-mcp-token":
        token = issue_scoped_token(conn, _user_id_named(conn, args.user_name), args.label, "mcp")
        return f"mcp token for {args.user_name}, label {args.label} (shown once): {token}"
    if not revoke(conn, args.device_id):
        raise AdminError(f"no active device {args.device_id}")
    return f"revoked device {args.device_id}"


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: load config, run one command in its own transaction, print the result."""
    args = sys.argv[1:] if argv is None else list(argv)
    try:
        cfg = load_config()
        with connect(cfg) as conn:
            output = run(conn, args, cfg, datetime.now(UTC))
    except (AdminError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
