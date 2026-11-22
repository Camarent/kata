"""Entry point: `python -m kata_core.jobs` runs the core job runner loop.

The config file comes from env KATA_CONFIG (see kata_core.config). The poll interval comes
from `[jobs] runner_poll_seconds`. `python -m kata_core` (the API) is unchanged.
"""

from __future__ import annotations

import logging

from kata_core.config import ConfigError, load_config
from kata_core.jobs.runner import load_registry, run_forever

log = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        cfg = load_config()
    except ConfigError as exc:
        log.error("config: %s", exc)
        return 1
    run_forever(cfg, load_registry())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
