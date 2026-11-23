"""Check the tracked gates file tools/gates.json."""

import json
from pathlib import Path

GATES_FILE = Path(__file__).resolve().parents[2] / "tools" / "gates.json"
EXPECTED_GATES = [
    ("ruff", ".venv/bin/ruff check ."),
    ("mypy", ".venv/bin/mypy core"),
    ("smoke", ".venv/bin/python -m pytest tests -m smoke"),
    ("pytest", ".venv/bin/python -m pytest tests --cov=core --cov=worker --cov-report=term -m 'not flaky'"),
    ("extension-build", "npm --prefix extension run build"),
    ("extension-test", "npm --prefix extension run test:cov"),
]
EXPECTED_NAMES = [name for name, _ in EXPECTED_GATES]


def load_gates() -> dict:
    return json.loads(GATES_FILE.read_text(encoding="utf-8"))


def test_top_level_key_is_gates():
    data = load_gates()
    assert list(data.keys()) == ["gates"]
    assert isinstance(data["gates"], list)


def test_entries_have_str_name_and_cmd():
    for entry in load_gates()["gates"]:
        assert set(entry.keys()) == {"name", "cmd"}
        assert isinstance(entry["name"], str)
        assert isinstance(entry["cmd"], str)


def test_entry_names_are_exact():
    names = [entry["name"] for entry in load_gates()["gates"]]
    assert names == EXPECTED_NAMES


def test_entry_names_and_cmds_are_exact():
    pairs = [(entry["name"], entry["cmd"]) for entry in load_gates()["gates"]]
    assert pairs == EXPECTED_GATES


def test_no_cmd_runs_through_qrun():
    for entry in load_gates()["gates"]:
        assert "cs-qrun" not in entry["cmd"], entry["name"]
