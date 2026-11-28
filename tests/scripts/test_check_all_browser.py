"""scripts/dev/check-all.sh: --browser is its own mode, every other pytest -m excludes the browser marker.

Static checks on the script text, one argument-parsing run, and runs of a copy of the script in a
temp sandbox with stub tools (no venv, npm or Postgres). The sandbox is removed when each test ends.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "scripts" / "dev" / "check-all.sh"

# Stub for KATA_QRUN: each step runs nothing and exits 0, except a step whose argument list
# holds the STUB_FAIL value, which exits 1.
STUB_QRUN = """import os
import sys
import time

if os.environ.get("STUB_FAIL") in sys.argv[2:]:
    sys.exit(1)
# A step whose argument list holds STUB_MARK_ARG is slow, then writes STUB_MARK_FILE: the file proves
# the run waited for that job.
if os.environ.get("STUB_MARK_ARG") in sys.argv[2:]:
    time.sleep(1)
    with open(os.environ["STUB_MARK_FILE"], "w", encoding="utf-8") as marker:
        marker.write("done")
"""
STUB_PG = "#!/usr/bin/env bash\nexit 0\n"
# install-browsers.sh: --print-dir prints a path, --status fails (browsers missing).
STUB_BROWSERS = """#!/usr/bin/env bash
case "$1" in
  --print-dir) echo /nonexistent ;;
  *) exit 1 ;;
esac
"""

# The -m argument of a pytest call: an unquoted token or one single-quoted string.
# The lookbehind skips the interpreter flag in "python -m pytest".
M_ARG = re.compile(r"(?<!python)\s-m\s+('[^']*'|\S+)")
BROWSER_VALUE = "browser"


def _m_args(text: str) -> list[str]:
    """Every -m value on the non-comment lines of TEXT, quotes kept."""
    values: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        values.extend(match.group(1) for match in M_ARG.finditer(line))
    return values


def _excludes_browser(value: str) -> bool:
    """True when a -m value is the browser selection itself or excludes the browser marker."""
    return value.strip("'") == BROWSER_VALUE or "not browser" in value


def test_browser_mode_cannot_combine_with_another_mode() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--browser", "--py"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2, result.stderr
    assert "mode flags cannot be combined" in result.stderr


def test_every_other_pytest_marker_excludes_browser() -> None:
    values = _m_args(SCRIPT.read_text(encoding="utf-8"))
    # Non-vacuous: the script has the unit, smoke, py, merge, full and browser selections.
    assert len(values) >= 6, values
    offenders = [value for value in values if not _excludes_browser(value)]
    assert offenders == [], offenders
    assert [v for v in values if v.strip("'") == BROWSER_VALUE] == [BROWSER_VALUE]


def test_check_detects_a_marker_without_browser_exclusion() -> None:
    # Decoy: a line like the old flaky-only selection must be flagged.
    decoy = "    step pytest .venv/bin/python -m pytest tests -m 'not flaky'\n"
    values = _m_args(decoy)
    assert values == ["'not flaky'"]
    assert not _excludes_browser(values[0])


def _sandbox(root: Path, browsers_present: bool = False) -> None:
    """Copy check-all.sh into ROOT with stub pg.sh, install-browsers.sh and qrun, and the dirs it checks.

    BROWSERS_PRESENT makes the install-browsers stub report browsers as installed (--status exits 0).
    """
    (root / "scripts" / "dev").mkdir(parents=True)
    (root / "scripts" / "dev" / "check-all.sh").write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    browsers = STUB_BROWSERS.replace("*) exit 1", "*) exit 0") if browsers_present else STUB_BROWSERS
    for rel, text in (
        ("scripts/dev/pg.sh", STUB_PG),
        ("scripts/dev/install-browsers.sh", browsers),
    ):
        (root / rel).write_text(text, encoding="utf-8")
        (root / rel).chmod(0o755)
    (root / "qrun.py").write_text(STUB_QRUN, encoding="utf-8")
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    (root / ".venv" / "bin" / "python").chmod(0o755)
    for rel in ("extension/node_modules", "editor/node_modules", "extension/tools-js/node_modules"):
        (root / rel).mkdir(parents=True)


def _run_merge_sandbox(
    root: Path, fail_arg: str | None, mode: str = "--merge"
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, KATA_QRUN=str(root / "qrun.py"), TMPDIR=str(root), XDG_STATE_HOME=str(root))
    env.pop("STUB_FAIL", None)
    env["STUB_MARK_ARG"] = "editor"
    env["STUB_MARK_FILE"] = str(root / "editor-marker")
    if fail_arg is not None:
        env["STUB_FAIL"] = fail_arg
    return subprocess.run(
        ["bash", str(root / "scripts" / "dev" / "check-all.sh"), mode],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )


def test_merge_red_job_fails_the_run_after_waiting() -> None:
    # "-n" is an argument of the pytest job only: that job goes red, the other concurrent jobs stay green.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _sandbox(root)
        result = _run_merge_sandbox(root, fail_arg="-n")
        # The editor job is slower than the red pytest job: its marker exists only if the run waited.
        marker_written = (root / "editor-marker").exists()
    assert result.returncode == 1, result.stdout + result.stderr
    assert marker_written, "run ended before the slower editor job finished"
    assert "CHECK-ALL FAILED at pytest" in result.stdout
    assert "CHECK-ALL OK" not in result.stdout
    # The failing job's log shows its step once, and the run prints the FAILED line once.
    assert result.stdout.count("CHECK-ALL FAILED at pytest") == 1, result.stdout


def test_browser_deps_install_runs_before_the_jobs_and_its_failure_ends_the_run() -> None:
    # Browsers present: the install runs in the parent (one installer for .venv). "uv" is an argument of
    # the browser-deps step only, so that install goes red and the run stops before any job starts.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _sandbox(root, browsers_present=True)
        result = _run_merge_sandbox(root, fail_arg="uv")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "CHECK-ALL FAILED at browser-deps" in result.stdout
    assert "CHECK-ALL OK" not in result.stdout


def test_merge_green_run_skips_browser_without_ending_the_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _sandbox(root)
        result = _run_merge_sandbox(root, fail_arg=None)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "check-all: browser tests skipped" in result.stdout
    assert "CHECK-ALL OK (merge)" in result.stdout


def test_browser_pytest_step_runs_under_xdist_with_a_worker_cap() -> None:
    # The browser step runs its cases in parallel workers: -n auto, capped by BROWSER_MAX_WORKERS.
    script = (REPO_ROOT / "scripts" / "dev" / "check-all.sh").read_text(encoding="utf-8")
    lines = [line for line in script.splitlines() if "-m pytest tests/browser" in line]
    assert len(lines) == 1, lines
    assert " -n auto " in lines[0], lines[0]
    assert '--maxprocesses "$BROWSER_MAX_WORKERS"' in lines[0], lines[0]
    assert re.search(r"^BROWSER_MAX_WORKERS=\d+$", script, re.MULTILINE), "worker cap constant missing"


def test_browser_mode_without_browsers_exits_zero_without_building() -> None:
    # The extension build is red here, but without browsers the browser arm builds nothing: rc 0.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _sandbox(root)
        result = _run_merge_sandbox(root, fail_arg="build", mode="--browser")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "check-all: browser tests skipped" in result.stdout
    assert "extension-build" not in result.stdout
