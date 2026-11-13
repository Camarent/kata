"""Entry point: `python -m kata_worker` runs the pull loop until SIGINT or SIGTERM.

The config file comes from env KATA_CONFIG (see kata_core.config).
"""

from __future__ import annotations

import logging
import signal
import threading
from types import FrameType

from kata_core.config import ConfigError, load_config

from kata_worker.loop import run_forever

log = logging.getLogger(__name__)


def _stop_on_signal(stop_event: threading.Event) -> None:
    def handler(signum: int, frame: FrameType | None) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        cfg = load_config()
    except ConfigError as exc:
        log.error("config: %s", exc)
        return 1
    stop_event = threading.Event()
    _stop_on_signal(stop_event)
    run_forever(cfg, stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
