"""Route modules. Every module here that defines `router` is included by include_routers.

Adding a route file needs no edit elsewhere.
"""

from __future__ import annotations

import importlib
import pkgutil

from fastapi import APIRouter, FastAPI


def include_routers(app: FastAPI) -> None:
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            app.include_router(router)
