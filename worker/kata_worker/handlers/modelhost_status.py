"""Job kind `modelhost.status`: read the model host status through modelctl and attach the capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kata_core.modelhost.spec import STATUS_KIND

from kata_worker.handlers.modelhost_common import run_control

if TYPE_CHECKING:
    from kata_worker.core_client import CoreClient, Job
    from kata_worker.providers.router import Router

KIND = STATUS_KIND


def handle(job: Job, _router: Router, client: CoreClient) -> None:
    """Run modelctl status for one leased job; post {ok, text, capabilities?}."""
    run_control(job, client, KIND, with_capabilities=True)
