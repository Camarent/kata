"""Pins the tier marking done by tests/conftest.py, read through pytest's own collection.

Each check runs `pytest --collect-only` in a subprocess with the same interpreter, from the repo
root, into its own temp dir. The mutation check (swap the core and e2e keys in TIER_MARKS) must
turn this file red.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = "tests/core/"
E2E = "tests/e2e/"
BROWSER = "tests/browser/"
OTHER = ("tests/foundation/", "tests/worker/")


def _collect(*args: str) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--basetemp={tmp}/basetemp",
                *args,
            ],
            cwd=ROOT,
            env={**os.environ, "TMPDIR": tmp},
            capture_output=True,
            text=True,
            check=False,
        )
    assert proc.returncode in (0, 5), proc.stdout + proc.stderr
    return [line for line in proc.stdout.splitlines() if "::" in line]


def _under(items: list[str], prefix: str) -> list[str]:
    return [item for item in items if item.startswith(prefix)]


def test_tier_selection_matches_directories():
    everything = _collect()
    integration = _collect("-m", "integration")
    e2e = _collect("-m", "e2e")

    core_items = _under(everything, CORE)
    e2e_items = _under(everything, E2E)
    assert core_items, "no tests/core items collected"
    assert e2e_items, "no tests/e2e items collected"

    # every tests/core item is integration, and only tests/core is
    assert set(_under(integration, CORE)) == set(core_items)
    assert not _under(integration, E2E)
    assert not any(item.startswith(OTHER) for item in integration)

    # every tests/e2e item is e2e, and only tests/e2e is
    assert set(_under(e2e, E2E)) == set(e2e_items)
    assert not _under(e2e, CORE)
    assert not any(item.startswith(OTHER) for item in e2e)

    # tests/foundation and tests/worker carry neither tier
    other_items = [item for item in everything if item.startswith(OTHER)]
    assert other_items, "no foundation or worker items collected"
    assert not any(item in integration or item in e2e for item in other_items)


def test_smoke_selection_yields_exactly_two_items():
    smoke = _collect("-m", "smoke")
    assert len(smoke) == 2, smoke


def test_browser_tests_are_opt_in():
    # Without -m browser the conftest deselects every tests/browser item; with it, they are collected.
    default = _collect("tests/browser")
    opted_in = _collect("-m", "browser", "tests/browser")
    assert default == [], default
    assert opted_in, "no tests/browser items collected with -m browser"
    assert all(item.startswith(BROWSER) for item in opted_in), opted_in
