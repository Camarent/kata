"""Job kind `modelhost.up`: start the local model host through modelctl and post its answer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kata_core.modelhost.spec import UP_KIND

from kata_worker.handlers.modelhost_common import run_control

if TYPE_CHECKING:
    from kata_worker.core_client import CoreClient, Job
    from kata_worker.providers.router import Router

KIND = UP_KIND


def handle(job: Job, _router: Router, client: CoreClient) -> None:
    """Run modelctl up for one leased job; post {ok, text}."""
    run_control(job, client, KIND)
