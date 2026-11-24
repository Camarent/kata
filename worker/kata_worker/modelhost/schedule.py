"""Swap decision for one target model, from the measured capabilities. Pure: no I/O, no clock.

allowed: the target fits alone (measured True). Anything else, including unknown, is not allowed.
swap: the target is allowed and a loaded model is not measured together with it.
"""

from __future__ import annotations

from dataclasses import dataclass

from kata_worker.modelhost.capabilities import Capabilities


@dataclass(frozen=True)
class Decision:
    allowed: bool
    swap: bool
    reason: str


def decide(model: str, caps: Capabilities) -> Decision:
    """Decide whether `model` may run, and whether loaded models must be swapped out first."""
    alone = caps.fits_alone(model)
    if alone is None:
        return Decision(allowed=False, swap=False, reason=f"{model}: fit not measured; not allowed")
    if alone is False:
        return Decision(allowed=False, swap=False, reason=f"{model}: measured not to fit alone")
    others = [name for name in caps.loaded if name != model and not caps.measured_together(name, model)]
    if others:
        return Decision(
            allowed=True,
            swap=True,
            reason=f"{model}: not measured together with {', '.join(others)}; swap",
        )
    return Decision(allowed=True, swap=False, reason=f"{model}: fits alone; nothing to swap")
