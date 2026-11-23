"""Real-dojo smoke: add, validate, lock and build one synthetic gap item with the `dojo` binary.

Opt-in and started by hand only: never run by check-all.sh or CI. Refused (exit 2, no run) unless
KATA_TEST_DOJO is set to an executable file. The run works in a temp dir that is removed at the end.
Exit 0 only when every step succeeds with no diagnostics; the built file list is printed.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

from kata_core.trainer.cli import TrainerError
from kata_core.trainer.dojo_cli import DojoTrainerCli

GATE_ENV = "KATA_TEST_DOJO"
COURSE_DIR = "course"
OUT_DIR = "out"
UNIT = "geo"
SYNTHETIC_ITEM = {
    "type": "gap",
    "unit": UNIT,
    "prompt": "The capital of Italy is ___.",
    "answers": ["Rome"],
}
TIMEOUT_SECONDS = 60.0
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2


def _refuse(message: str) -> int:
    print(message, file=sys.stderr)
    return EXIT_REFUSED


def _smoke(cli: DojoTrainerCli) -> int:
    """Run the four steps in a temp dir; the dir is removed when the run ends."""
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp) / COURSE_DIR
        outdir = Path(tmp) / OUT_DIR
        workdir.mkdir()
        item_id = cli.add(workdir, json.dumps(SYNTHETIC_ITEM))
        print(f"added {item_id}")
        diagnostics = cli.validate(workdir)
        if diagnostics:
            for diagnostic in diagnostics:
                print(f"diagnostic: {diagnostic.message}", file=sys.stderr)
            return EXIT_FAILED
        cli.lock(workdir)
        for name in cli.build(workdir, outdir):
            print(name)
    return EXIT_OK


def main(env: Mapping[str, str]) -> int:
    """Run the real-dojo smoke against the binary named in KATA_TEST_DOJO. Returns the exit code."""
    binary = env.get(GATE_ENV, "")
    if not binary:
        return _refuse(f"refused: set {GATE_ENV} to the path of an executable dojo binary")
    if not (Path(binary).is_file() and os.access(binary, os.X_OK)):
        return _refuse(f"refused: {GATE_ENV} is not an executable file: {binary}")
    cli = DojoTrainerCli(argv_prefix=[binary], timeout=TIMEOUT_SECONDS)
    try:
        return _smoke(cli)
    except TrainerError as exc:
        print(f"dojo smoke failed: {exc}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main(os.environ))
