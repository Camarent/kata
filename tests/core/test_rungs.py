"""Course start rung mapping (D48, D49) and the config key that sets the default rung."""

from __future__ import annotations

from pathlib import Path

import pytest
from kata_core.config import EXAMPLE_PATH, load_config
from kata_core.trainer.rungs import LEARNED_STAGE, RungError, start_rung, validate_rung

HOST_PATH = EXAMPLE_PATH.parents[1] / "deploy" / "kata.host.toml"


@pytest.mark.parametrize(
    ("state", "learning_rung", "expected"),
    [
        ("new", 0, 0),
        ("new", 3, 0),
        ("learning", 0, 0),
        ("learning", 2, 2),
        ("learning", 3, 3),
        ("known", 2, None),
    ],
)
def test_start_rung_maps_state(state: str, learning_rung: int, expected: int | None) -> None:
    assert start_rung(state, learning_rung) == expected


@pytest.mark.parametrize("rung", [-1, LEARNED_STAGE, 9])
def test_rung_outside_range_is_rejected(rung: int) -> None:
    with pytest.raises(RungError):
        validate_rung(rung)
    with pytest.raises(RungError):
        start_rung("learning", rung)


def test_boolean_is_not_a_rung() -> None:
    with pytest.raises(RungError):
        validate_rung(True)


def test_unknown_state_is_rejected() -> None:
    with pytest.raises(RungError):
        start_rung("mastered", 2)


@pytest.mark.parametrize("path", [EXAMPLE_PATH, HOST_PATH], ids=["example", "host"])
def test_config_files_hold_learning_start_rung(path: Path) -> None:
    cfg = load_config(path, env={})
    rung = int(cfg.get("trainer", "learning_start_rung"))
    assert rung == 2
    assert validate_rung(rung) == rung
