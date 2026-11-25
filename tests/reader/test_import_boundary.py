"""The core and the worker never import kata_reader: the reader runs as its own process, behind the spool."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
READER_PACKAGE = "kata_reader"
BOUNDED_TREES = (REPO_ROOT / "core", REPO_ROOT / "worker")


def _imports_reader(module: ast.AST) -> bool:
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        if any(name.split(".")[0] == READER_PACKAGE for name in names):
            return True
    return False


def _files_importing_reader(*roots: Path) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if _imports_reader(tree):
                found.append(path)
    return found


def test_core_and_worker_never_import_kata_reader():
    assert _files_importing_reader(*BOUNDED_TREES) == []


def test_boundary_helper_detects_reader_import(tmp_path: Path):
    (tmp_path / "plain.py").write_text("import json\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def run():\n    from kata_reader.extract import extract\n", encoding="utf-8")
    (tmp_path / "bad_plain.py").write_text("import kata_reader\n", encoding="utf-8")
    assert _files_importing_reader(tmp_path) == [tmp_path / "bad.py", tmp_path / "bad_plain.py"]
