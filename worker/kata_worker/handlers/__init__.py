"""Worker job handlers: one module per job kind, discovered by pkgutil (D3).

Each module here defines `KIND` (the job kind it takes) and `handle(job, router, client)`, which
reports or fails the job itself. Adding a kind needs no edit elsewhere.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kata_worker.core_client import CoreClient, Job
    from kata_worker.providers.router import Router

Handler = Callable[["Job", "Router", "CoreClient"], None]


def load_handlers() -> dict[str, Handler]:
    """Map each job kind to the `handle` function of the module that defines it."""
    handlers: dict[str, Handler] = {}
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        kind = getattr(module, "KIND", None)
        handle = getattr(module, "handle", None)
        if kind is None or handle is None:
            continue
        if kind in handlers:
            raise RuntimeError(f"two worker handlers claim job kind {kind!r}")
        handlers[kind] = handle
    return handlers
