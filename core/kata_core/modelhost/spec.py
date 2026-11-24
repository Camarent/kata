"""Modelhost job kinds and the payload allow-list checked before a job is queued."""

from __future__ import annotations

import json
from typing import Any

UP_KIND = "modelhost.up"
USE_KIND = "modelhost.use"
MEASURE_KIND = "modelhost.measure"
STATUS_KIND = "modelhost.status"
KINDS: frozenset[str] = frozenset({UP_KIND, USE_KIND, MEASURE_KIND, STATUS_KIND})

ENGINES: frozenset[str] = frozenset({"ollama", "strata", "none"})
MAX_TEXT = 2000


def validate_payload(kind: str, payload: str) -> dict[str, Any]:
    """Return the parsed payload of a modelhost job of `kind`. Raise ValueError when it is not allowed.

    `modelhost.use` needs `{"engine": "ollama" | "strata" | "none"}`. The other kinds need `{}`.
    """
    if kind not in KINDS:
        raise ValueError(f"not a modelhost kind: {kind!r}")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{kind} payload is not JSON: {exc.msg}") from exc
    if type(data) is not dict:
        raise ValueError(f"{kind} payload must be a JSON object")
    if kind == USE_KIND:
        engine = data.get("engine")
        if set(data) != {"engine"} or not isinstance(engine, str) or engine not in ENGINES:
            raise ValueError(f"{kind} payload needs engine in {sorted(ENGINES)}")
    elif data:
        raise ValueError(f"{kind} payload must be an empty object")
    return data
