"""Swap decision: allowed only when measured to fit alone; swap when a loaded model is not measured together."""

from __future__ import annotations

from typing import Any

import pytest
from kata_worker.modelhost.capabilities import Capabilities, parse
from kata_worker.modelhost.schedule import decide


def _caps(
    models: dict[str, Any] | None = None,
    together: list[list[str]] | None = None,
    loaded: list[str] | None = None,
) -> Capabilities:
    return parse(
        {
            "schema": 2,
            "loaded_now": loaded or [],
            "models": models or {},
            "fits_together": together or [],
        }
    )


def test_fits_alone_with_nothing_loaded_is_allowed_without_swap() -> None:
    caps = _caps(models={"kata-l": {"fits_alone": True}})
    decision = decide("kata-l", caps)
    assert decision.allowed is True
    assert decision.swap is False


def test_null_fits_alone_is_not_allowed() -> None:
    caps = _caps(models={"kata-l": {"fits_alone": None}})
    decision = decide("kata-l", caps)
    assert decision.allowed is False
    assert decision.swap is False


def test_absent_model_is_not_allowed() -> None:
    assert decide("kata-l", _caps()).allowed is False


def test_measured_not_to_fit_alone_is_not_allowed() -> None:
    caps = _caps(models={"kata-l": {"fits_alone": False}})
    assert decide("kata-l", caps).allowed is False


def test_unknown_document_is_not_allowed() -> None:
    caps = parse({"schema": 3, "models": {"kata-l": {"fits_alone": True}}})
    assert decide("kata-l", caps).allowed is False


@pytest.mark.parametrize("together", [[], [["kata-l", "kata-x"]]])
def test_loaded_model_not_measured_together_triggers_swap(together: list[list[str]]) -> None:
    caps = _caps(
        models={"kata-l": {"fits_alone": True}, "kata-m": {"fits_alone": True}},
        together=together,
        loaded=["kata-l"],
    )
    decision = decide("kata-m", caps)
    assert decision.allowed is True
    assert decision.swap is True
    assert "kata-l" in decision.reason


def test_pair_listed_together_means_no_swap() -> None:
    caps = _caps(
        models={"kata-l": {"fits_alone": True}, "kata-m": {"fits_alone": True}},
        together=[["kata-l", "kata-m"]],
        loaded=["kata-l"],
    )
    decision = decide("kata-m", caps)
    assert decision.allowed is True
    assert decision.swap is False


def test_target_already_loaded_does_not_swap_itself() -> None:
    caps = _caps(models={"kata-l": {"fits_alone": True}}, loaded=["kata-l"])
    decision = decide("kata-l", caps)
    assert decision.allowed is True
    assert decision.swap is False
