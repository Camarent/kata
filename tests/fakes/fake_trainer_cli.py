"""Fake trainer CLI: a python script run as `[sys.executable, <this file>, <subcommand>, ...]`.

Prints one JSON object per call on stdout (the D7 contract). State lives in `<workdir>/items.jsonl`.
An item whose text contains FAKE_INVALID gets a diagnostic from `validate`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ITEMS_FILE = "items.jsonl"
INVALID_MARK = "FAKE_INVALID"


def _option(args: list[str], name: str) -> str:
    prefix = f"--{name}="
    for arg in args:
        if arg.startswith(prefix):
            return arg[len(prefix) :]
    raise SystemExit(f"fake trainer: missing --{name}")


def _read_items(workdir: Path) -> list[dict[str, str]]:
    path = workdir / ITEMS_FILE
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main(argv: list[str]) -> int:
    subcommand, args = argv[0], argv[1:]
    workdir = Path(_option(args, "workdir"))
    if subcommand == "next-id":
        print(json.dumps({"id": f"i{len(_read_items(workdir)) + 1:04d}"}))
    elif subcommand == "add":
        items = _read_items(workdir)
        item_id = f"i{len(items) + 1:04d}"
        items.append({"id": item_id, "item": _option(args, "item")})
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / ITEMS_FILE).write_text("".join(json.dumps(i) + "\n" for i in items))
        print(json.dumps({"id": item_id}))
    elif subcommand == "validate":
        diagnostics = [
            {"item": i["id"], "message": "fake: marked invalid"}
            for i in _read_items(workdir)
            if INVALID_MARK in i["item"]
        ]
        print(json.dumps({"ok": not diagnostics, "diagnostics": diagnostics}))
    elif subcommand == "lock":
        print(json.dumps({"ok": True}))
    elif subcommand == "build":
        outdir = Path(_option(args, "outdir"))
        outdir.mkdir(parents=True, exist_ok=True)
        built = outdir / "course.json"
        built.write_text(json.dumps({"items": _read_items(workdir)}))
        print(json.dumps({"files": [str(built)]}))
    else:
        sys.stderr.write(f"fake trainer: unknown subcommand {subcommand}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
