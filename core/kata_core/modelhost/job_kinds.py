"""Modelhost output hooks, found by the job runner through `load_registry`.

The worker reports `{ok, text, capabilities?}` for each modelhost job. The hooks check that
shape and store nothing; a bad output raises ValueError and the job is not done.
"""

from __future__ import annotations

from typing import Any

import psycopg

from kata_core.jobs.queue import Job
from kata_core.jobs.runner import OutputHook
from kata_core.modelhost.spec import KINDS, MAX_TEXT


def check_output(output: dict[str, Any]) -> None:
    """Raise ValueError unless `output` is `{ok: bool, text: str, capabilities?: dict}`."""
    if type(output) is not dict:
        raise ValueError("modelhost output must be a JSON object")
    if type(output.get("ok")) is not bool:
        raise ValueError("modelhost output needs ok: bool")
    text = output.get("text")
    if type(text) is not str:
        raise ValueError("modelhost output needs text: str")
    if len(text) > MAX_TEXT:
        raise ValueError(f"modelhost output text is over {MAX_TEXT} characters")
    if "capabilities" in output and not isinstance(output["capabilities"], dict):
        raise ValueError("modelhost output capabilities must be an object")


def _hook(conn: psycopg.Connection[Any], job: Job, output: dict[str, Any]) -> None:
    check_output(output)


OUTPUT_HOOKS: dict[str, OutputHook] = {kind: _hook for kind in sorted(KINDS)}
