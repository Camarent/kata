"""deploy/compose.yaml: every third-party image is pinned by digest through deploy/versions.env.

Reads the files as text (no docker): each image line that is not the shipped kata image must be
`${<NAME>_IMAGE:?...}@${<NAME>_DIGEST:?...}`, and deploy/versions.env must define both variables.
The shipped kata image is `kata:${KATA_IMAGE_TAG:?...}`; compose.yaml has no build: key (the build
lives in deploy/compose.build.yaml, which the VM never runs).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
COMPOSE = REPO_ROOT / "deploy" / "compose.yaml"
COMPOSE_BUILD = REPO_ROOT / "deploy" / "compose.build.yaml"
VERSIONS = REPO_ROOT / "deploy" / "versions.env"
LOCAL_IMAGE = re.compile(r"kata:\$\{KATA_IMAGE_TAG:\?[^}]*\}")
BUILT_SERVICES = ("migrate", "core", "worker")
PINNED_IMAGE = re.compile(
    r"\$\{(?P<image>[A-Z_]+)_IMAGE:\?[^}]*\}@\$\{(?P<digest>[A-Z_]+)_DIGEST:\?[^}]*\}"
)


def _image_values(compose_text: str) -> list[str]:
    values = []
    for line in compose_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("image:"):
            values.append(stripped.removeprefix("image:").strip())
    return values


def _unpinned_images(compose_text: str) -> list[str]:
    """Image values that are neither the local kata build nor a versions.env digest reference."""
    bad = []
    for value in _image_values(compose_text):
        if LOCAL_IMAGE.fullmatch(value):
            continue
        match = PINNED_IMAGE.fullmatch(value)
        if match is None or match.group("image") != match.group("digest"):
            bad.append(value)
    return bad


def _defined_variables(versions_text: str) -> set[str]:
    names = set()
    for line in versions_text.splitlines():
        if line.strip().startswith("#") or "=" not in line:
            continue
        names.add(line.split("=", 1)[0].strip())
    return names


def _referenced_variables(compose_text: str) -> set[str]:
    names = set()
    for value in _image_values(compose_text):
        match = PINNED_IMAGE.fullmatch(value)
        if match is not None:
            names.add(match.group("image") + "_IMAGE")
            names.add(match.group("digest") + "_DIGEST")
    return names


def test_every_third_party_image_is_pinned_by_digest():
    assert _unpinned_images(COMPOSE.read_text()) == []


def test_pinned_images_are_present_in_compose():
    assert _referenced_variables(COMPOSE.read_text()), "no digest-pinned image found in compose"


def test_versions_env_defines_every_compose_image_variable():
    defined = _defined_variables(VERSIONS.read_text())
    missing = _referenced_variables(COMPOSE.read_text()) - defined
    assert missing == set()


def test_compose_has_no_build_key():
    build_lines = [line for line in COMPOSE.read_text().splitlines() if line.strip().startswith("build:")]
    assert build_lines == []


def test_build_override_builds_every_stack_image():
    text = COMPOSE_BUILD.read_text()
    for service in BUILT_SERVICES:
        assert f"  {service}:\n    build:\n" in text, f"{service} has no build in compose.build.yaml"
    assert "PY_BASE_DIGEST: ${PY_BASE_DIGEST}" in text


def test_bare_tag_mutation_is_reported():
    text = COMPOSE.read_text()
    old = "    image: ${POSTGRES_IMAGE:?fill in deploy/versions.env}@${POSTGRES_DIGEST:?fill in deploy/versions.env}\n"
    assert text.count(old) == 1, "expected exactly one postgres digest line"
    mutated = text.replace(old, "    image: postgres:17\n")
    assert _unpinned_images(mutated) == ["postgres:17"]
