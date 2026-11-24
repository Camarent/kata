"""scripts/dev/render_design_shots.py: argument handling, missing Chrome, and the Chrome call shape."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "scripts" / "dev" / "render_design_shots.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_design_shots", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


render_design_shots = _load_script()


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _mockups(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "page.html").write_text("<html><body>x</body></html>\n")
    return root


def test_missing_directory_argument_is_usage_error() -> None:
    result = _run()
    assert result.returncode == 2
    assert "mockup_dir" in result.stderr


def test_not_a_directory_is_rejected(tmp_path: Path) -> None:
    result = _run(str(tmp_path / "absent"))
    assert result.returncode == 2
    assert "not a directory" in result.stderr


def test_directory_without_html_is_rejected(tmp_path: Path) -> None:
    result = _run(str(tmp_path))
    assert result.returncode == 2
    assert "no *.html" in result.stderr


def test_missing_chrome_is_reported_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mockups = _mockups(tmp_path / "mockups")
    empty_path = tmp_path / "empty-bin"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    assert render_design_shots.find_chrome() is None
    assert render_design_shots.main([str(mockups)]) == 1
    assert not (mockups / "shots").exists()


def test_find_chrome_takes_first_name_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "chromium"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    assert render_design_shots.find_chrome() == str(fake)


def test_render_writes_light_and_dark_png_per_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mockups = _mockups(tmp_path / "mockups")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        png = next(arg for arg in command if arg.startswith("--screenshot=")).split("=", 1)[1]
        Path(png).write_bytes(b"\x89PNG")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(render_design_shots, "find_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(render_design_shots.subprocess, "run", fake_run)
    assert render_design_shots.main([str(mockups)]) == 0
    shots = mockups / "shots"
    assert sorted(p.name for p in shots.iterdir()) == ["page-dark.png", "page-light.png"]
    assert len(calls) == 2
    for command in calls:
        assert command[0] == "/fake/chrome"
        assert f"--window-size={render_design_shots.WINDOW_SIZE}" in command
        assert command[-1].startswith("file://")
        assert "--no-sandbox" in command


def test_chrome_failure_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mockups = _mockups(tmp_path / "mockups")

    def failing_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "boom")

    monkeypatch.setattr(render_design_shots, "find_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(render_design_shots.subprocess, "run", failing_run)
    assert render_design_shots.main([str(mockups)]) == 1
