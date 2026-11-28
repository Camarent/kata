"""scripts/dev/check-all.sh --setup: a fresh .venv also gets requirements-browser.txt, when that file exists.

Runs a copy of the script in a temp sandbox with a stub uv that logs its argument lists (no network,
no real install). The sandbox is removed when each test ends.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "scripts" / "dev" / "check-all.sh"

# Stub uv: appends its argument list to the log, one line per call. "uv venv" creates .venv, as the real one does.
STUB_UV = """#!/usr/bin/env bash
echo "$*" >> "$UV_STUB_LOG"
if [ "$1" = venv ]; then mkdir -p .venv/bin; fi
"""
PYPROJECT = """[project]
dependencies = ["pytest"]

[dependency-groups]
dev = ["ruff"]
"""
BROWSER_REQUIREMENTS = "selenium==4.0.0\n"


def _setup_run(root: Path, browser_requirements: bool) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run check-all.sh --setup in ROOT with no .venv yet; return the result and the uv call log."""
    (root / "scripts" / "dev").mkdir(parents=True)
    (root / "scripts" / "dev" / "check-all.sh").write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    if browser_requirements:
        (root / "requirements-browser.txt").write_text(BROWSER_REQUIREMENTS, encoding="utf-8")
    for rel in ("extension/node_modules", "editor/node_modules"):
        (root / rel).mkdir(parents=True)
    (root / "bin").mkdir()
    uv = root / "bin" / "uv"
    uv.write_text(STUB_UV, encoding="utf-8")
    uv.chmod(0o755)
    log = root / "uv.log"
    env = dict(
        os.environ,
        PATH=f"{root / 'bin'}{os.pathsep}{os.environ['PATH']}",
        UV_STUB_LOG=str(log),
        TMPDIR=str(root),
        XDG_STATE_HOME=str(root),
    )
    result = subprocess.run(
        ["bash", str(root / "scripts" / "dev" / "check-all.sh"), "--setup"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=env,
    )
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    return result, calls


def test_setup_installs_browser_requirements_after_the_project_deps() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result, calls = _setup_run(Path(tmp), browser_requirements=True)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = calls.splitlines()
    project_calls = [i for i, line in enumerate(lines) if "-r .venv/requirements.txt" in line]
    browser_calls = [i for i, line in enumerate(lines) if "-r requirements-browser.txt" in line]
    assert len(project_calls) == 1, calls
    assert len(browser_calls) == 1, calls
    assert "pip install" in lines[browser_calls[0]], calls
    assert project_calls[0] < browser_calls[0], calls


def test_setup_without_browser_requirements_installs_no_browser_deps() -> None:
    # Decoy: with no requirements-browser.txt, the project install still runs but no browser install does.
    with tempfile.TemporaryDirectory() as tmp:
        result, calls = _setup_run(Path(tmp), browser_requirements=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "-r .venv/requirements.txt" in calls, calls
    assert "requirements-browser.txt" not in calls, calls
