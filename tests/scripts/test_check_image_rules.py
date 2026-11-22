"""scripts/deploy/check_image_rules.py: real files pass, one mutated copy per rule fails with its name."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "scripts" / "deploy" / "check_image_rules.py"
DOCKERFILE = REPO_ROOT / "deploy" / "Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"


def _run(dockerfile: Path, dockerignore: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            str(SCRIPT),
            "--dockerfile",
            str(dockerfile),
            "--dockerignore",
            str(dockerignore),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _replace_once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, f"expected exactly one {old!r}"
    return text.replace(old, new)


def _drop_healthcheck(text: str) -> str:
    """Remove the HEALTHCHECK instruction and its continuation line."""
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith("HEALTHCHECK ")]
    assert len(starts) == 1
    start = starts[0]
    assert lines[start].rstrip().endswith("\\")
    return "".join(lines[:start] + lines[start + 2 :])


def _drop_line(text: str, line: str) -> str:
    kept = [current for current in text.splitlines(keepends=True) if current.strip() != line]
    assert len(kept) == len(text.splitlines(keepends=True)) - 1
    return "".join(kept)


def test_real_files_pass():
    result = _run(DOCKERFILE, DOCKERIGNORE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hadolint deploy/Dockerfile" in result.stdout


def _mutate_from(text: str) -> str:
    return _replace_once(
        text,
        "FROM ${PY_BASE_IMAGE}@${PY_BASE_DIGEST} AS base",
        "FROM python:latest AS base",
    )


def _mutate_root(text: str) -> str:
    return _replace_once(text, "\nUSER kata\n", "\nUSER root\n")


def _mutate_no_user(text: str) -> str:
    return _drop_line(text, "USER kata")


def _mutate_no_healthcheck(text: str) -> str:
    return _drop_healthcheck(text)


def _keep(text: str) -> str:
    return text


def _mutate_dockerignore_no_git(text: str) -> str:
    return _drop_line(text, ".git")


def _mutate_secret_copy(text: str) -> str:
    return text + "COPY config/.env /app/.env\n"


# rule -> (Dockerfile mutation, .dockerignore mutation); each case changes exactly one rule's input.
MUTATIONS: dict[str, tuple[Callable[[str], str], Callable[[str], str]]] = {
    "unpinned-from": (_mutate_from, _keep),
    "root-user": (_mutate_root, _keep),
    "missing-user": (_mutate_no_user, _keep),
    "missing-healthcheck": (_mutate_no_healthcheck, _keep),
    "dockerignore-missing": (_keep, _mutate_dockerignore_no_git),
    "secret-copy": (_mutate_secret_copy, _keep),
}


@pytest.mark.parametrize("rule", sorted(MUTATIONS))
def test_mutated_copy_fails_with_rule_name(tmp_path: Path, rule: str):
    mutate_dockerfile, mutate_dockerignore = MUTATIONS[rule]
    dockerfile = tmp_path / "Dockerfile"
    dockerignore = tmp_path / ".dockerignore"
    dockerfile.write_text(mutate_dockerfile(DOCKERFILE.read_text(encoding="utf-8")), encoding="utf-8")
    dockerignore.write_text(mutate_dockerignore(DOCKERIGNORE.read_text(encoding="utf-8")), encoding="utf-8")

    result = _run(dockerfile, dockerignore)

    assert result.returncode == 1, result.stdout + result.stderr
    failed = [line.split(":", 1)[0] for line in result.stdout.splitlines() if ":" in line]
    assert failed.count(rule) == 1, result.stdout
    assert "hadolint deploy/Dockerfile" in result.stdout


def test_unreadable_input_exits_two(tmp_path: Path):
    result = _run(tmp_path / "missing", DOCKERIGNORE)
    assert result.returncode == 2
    assert "cannot read input" in result.stderr
