"""Shared body of the four modelhost control handlers: run modelctl for one job, post {ok, text[, capabilities]}.

A runner failure, including a bad payload, posts `ok: False` with the reason as text; it never fails
the job or stops the worker. Only a CoreError from the output call propagates (run_forever logs it).
This module defines no KIND: load_handlers reads KIND from each handler module only.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from kata_core.config import load_config

from kata_worker.modelhost.capabilities import Capabilities, CapabilitiesError, fetch
from kata_worker.modelhost.ctl import default_runner
from kata_worker.providers.scheduled import INFO_URL_KEY, MODELHOST_SECTION, TIMEOUT_KEY

if TYPE_CHECKING:
    from kata_worker.core_client import CoreClient, Job

log = logging.getLogger(__name__)


def capabilities_json(caps: Capabilities) -> dict[str, Any]:
    """The measured capabilities as JSON-ready data: per-model fit, measured pairs, loaded models."""
    return {
        "fits_alone": dict(caps.alone),
        "fits_together": sorted(sorted(pair) for pair in caps.together),
        "loaded_now": list(caps.loaded),
    }


def fetch_capabilities() -> dict[str, Any] | None:
    """Read the capabilities document from the info service; None when it cannot be read."""
    cfg = load_config()
    try:
        caps = fetch(str(cfg.get(MODELHOST_SECTION, INFO_URL_KEY)), float(cfg.get(MODELHOST_SECTION, TIMEOUT_KEY)))
    except CapabilitiesError as exc:
        log.warning("capabilities not attached: %s", exc)
        return None
    return capabilities_json(caps)


def run_control(job: Job, client: CoreClient, kind: str, *, with_capabilities: bool = False) -> None:
    """Run modelctl for `kind` with the job payload and post {ok, text}; add capabilities when asked."""
    try:
        ok, text = default_runner().run(kind, job.payload)
    except Exception as exc:  # noqa: BLE001 - a bad payload or a broken config must fail this job, not stop the worker
        log.warning("job %s: modelctl %s not run: %s", job.id, kind, exc)
        ok, text = False, str(exc)
    result: dict[str, Any] = {"ok": ok, "text": text}
    if with_capabilities:
        capabilities = fetch_capabilities()
        if capabilities is not None:
            result["capabilities"] = capabilities
    client.output(job.id, result)
