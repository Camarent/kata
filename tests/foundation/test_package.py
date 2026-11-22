import tomllib
from pathlib import Path

import kata_core

ROOT = Path(__file__).resolve().parents[2]


def _pyproject() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def test_project_metadata() -> None:
    project = _pyproject()["project"]
    assert project["name"] == "kata"
    assert project["version"] == "0.0.0"
    assert project["requires-python"] == ">=3.11"
    assert project["dependencies"] == [
        "fastapi==0.163.2",
        "psycopg[binary]==3.3.9",
        "httpx==0.28.1",
        "uvicorn==0.54.0",
    ]


def test_tool_sections_present() -> None:
    tool = _pyproject()["tool"]
    assert "ruff" in tool
    assert tool["mypy"]["strict"] is True
    pytest_cfg = tool["pytest"]["ini_options"]
    assert pytest_cfg["testpaths"] == ["tests"]
    assert pytest_cfg["pythonpath"] == ["core"]


def test_version_exposed() -> None:
    assert kata_core.__version__ == "0.0.0"
