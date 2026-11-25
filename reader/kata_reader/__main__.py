"""python -m kata_reader: serve the spool until SIGTERM.

Config comes from env KATA_CONFIG (default /config/kata.toml, [reader] table). A config error
prints one line to stderr and exits 2. SIGTERM stops the loop after the current poll and exits 0.
This module is the only place real time.sleep is used; serve() takes the sleep as a parameter.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time

from kata_reader import config
from kata_reader.spool import serve

IN_SUBDIR = "in"
OUT_SUBDIR = "out"


def main() -> int:
    try:
        cfg = config.load(os.environ.get(config.CONFIG_ENV, config.DEFAULT_CONFIG))
    except config.ConfigError as exc:
        print(f"kata_reader: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()

    def _on_term(*_: object) -> None:  # signal handler: (signum, frame), both unused
        stop.set()

    signal.signal(signal.SIGTERM, _on_term)
    serve(
        cfg.spool_dir / IN_SUBDIR,
        cfg.spool_dir / OUT_SUBDIR,
        cfg.limits,
        cfg.poll_seconds,
        time.sleep,
        stop.is_set,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
