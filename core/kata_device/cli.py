"""Subcommand dispatch for the device `kata` entry point.

REGISTRY maps a command name to "module:function". The module is imported only when its
command runs, so importing this file loads none of the command modules, and a missing command
module fails that one command with a message instead of a traceback. The function takes the
remaining argv and returns an exit code.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import cast

USAGE_EXIT = 2

REGISTRY: dict[str, str] = {
    "precommit": "kata_device.precommit:main",
    "postcommit": "kata_device.postcommit:main",
    "hooks": "kata_device.hooks:main",
    "term": "kata_term.cli:main",
}

Command = Callable[[list[str]], int]


def _load(target: str) -> Command:
    module_name, _, attr = target.partition(":")
    module = importlib.import_module(module_name)
    return cast(Command, getattr(module, attr))


def main(argv: Sequence[str], registry: Mapping[str, str] = REGISTRY) -> int:
    if not argv or argv[0] not in registry:
        print("usage: kata <command>", file=sys.stderr)
        print(f"known commands: {', '.join(sorted(registry))}", file=sys.stderr)
        return USAGE_EXIT
    name = argv[0]
    try:
        command = _load(registry[name])
    except (ModuleNotFoundError, AttributeError) as exc:
        print(f"kata: command {name!r} is not available: {exc}", file=sys.stderr)
        return USAGE_EXIT
    return command(list(argv[1:]))
