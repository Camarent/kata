"""API app factory. Routers are discovered from the routes package (see routes/__init__.py)."""

from __future__ import annotations

from fastapi import FastAPI

from kata_core.api.routes import include_routers
from kata_core.config import Config


def create_app(cfg: Config) -> FastAPI:  # noqa: V103 - app factory, called by tests and uvicorn
    app = FastAPI()
    app.state.cfg = cfg
    include_routers(app)
    return app
