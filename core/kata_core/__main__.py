"""Entry point: `python -m kata_core` serves the core API with uvicorn.

The config file comes from env KATA_CONFIG (see kata_core.config). Host and port come from
the `[core]` section.
"""

from __future__ import annotations

import logging

import uvicorn

from kata_core.api.app import create_app
from kata_core.config import ConfigError, load_config

log = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        cfg = load_config()
    except ConfigError as exc:
        log.error("config: %s", exc)
        return 1
    uvicorn.run(create_app(cfg), host=cfg.get("core", "host"), port=cfg.get("core", "port"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
