"""Marker: the staged tree hash the pre-commit check last passed, kept in the git directory.

The post-commit hook compares it with the committed tree to spot a commit that skipped the check.
The file holds one line: the tree hash. This module does no network I/O.
"""

from __future__ import annotations

from pathlib import Path

MARKER_DIR = "kata"
MARKER_FILE = "marker"


def _marker_path(git_dir: Path) -> Path:
    return git_dir / MARKER_DIR / MARKER_FILE


def write_marker(git_dir: Path, tree: str) -> None:
    """Record `tree` as the passed tree, creating `<git_dir>/kata` when missing."""
    path = _marker_path(git_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tree + "\n", encoding="utf-8")


def read_marker(git_dir: Path) -> str | None:
    """The recorded tree hash, or None when no marker is set."""
    path = _marker_path(git_dir)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def clear_marker(git_dir: Path) -> None:
    """Remove the marker; a missing marker is not an error."""
    _marker_path(git_dir).unlink(missing_ok=True)
