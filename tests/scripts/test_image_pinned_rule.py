"""scripts/deploy/_rules.py: _image_pinned, the one copy both deploy checks use."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).parents[2]
RULES = REPO_ROOT / "scripts" / "deploy" / "_rules.py"


def _load_rules() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_rules", RULES)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = _load_rules()


@pytest.mark.parametrize(
    ("image", "pinned"),
    [
        ("app", False),
        ("app:latest", False),
        ("app:1.0", True),
        ("app@sha256:" + "a" * 64, True),
        ("app:1.0@sha256:" + "a" * 64, True),
        ("registry:5000/app", False),
        ("registry:5000/app:latest", False),
        ("registry:5000/app:1.0", True),
        ("registry:5000/app@sha256:" + "a" * 64, True),
    ],
)
def test_image_pinned(image: str, pinned: bool) -> None:
    assert rules._image_pinned(image) is pinned


@pytest.mark.parametrize("image", ["app:1.0", "registry:5000/app:1.0"])
def test_tag_1_0_accepted_only_when_not_latest(image: str) -> None:
    assert rules._image_pinned(image) is True
    assert rules._image_pinned(image.rsplit(":", 1)[0] + ":latest") is False
