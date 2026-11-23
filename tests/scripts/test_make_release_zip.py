"""scripts/release/make_zip.py: reproducible zip (sorted entries, fixed mtime and mode, same names as the dist)."""

from __future__ import annotations

import hashlib
import importlib.util
import stat
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "scripts" / "release" / "make_zip.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_zip", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_zip = _load_module()


@pytest.fixture
def work_dir() -> Iterator[Path]:
    """A temp dir removed when the test ends."""
    with tempfile.TemporaryDirectory(prefix="kata-zip-test-") as name:
        yield Path(name)


@pytest.fixture
def dist(work_dir: Path) -> Path:
    """A dist folder with nested files, written in an order that is not sorted."""
    root = work_dir / "dist"
    (root / "js" / "lib").mkdir(parents=True)
    (root / "zeta.txt").write_text("z", encoding="utf-8")
    (root / "js" / "lib" / "b.js").write_text("b()", encoding="utf-8")
    (root / "alpha.json").write_text("{}", encoding="utf-8")
    (root / "js" / "a.js").write_text("a()", encoding="utf-8")
    return root


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_two_runs_give_identical_bytes(dist: Path, work_dir: Path) -> None:
    first = work_dir / "first.zip"
    second = work_dir / "second.zip"
    make_zip.build_zip(dist, first)
    # Touch the files so their real mtimes differ between the runs.
    for path in dist.rglob("*"):
        if path.is_file():
            path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    make_zip.build_zip(dist, second)
    assert _sha256(first) == _sha256(second)


def test_entries_are_sorted_with_fixed_mtime_and_mode(
    dist: Path, work_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force a walk in reverse-sorted order, so the zip order only comes out sorted when
    # dist_files sorts the names itself (filesystem order alone can look sorted by chance).
    original_rglob = Path.rglob

    def reversed_rglob(self: Path, pattern: str) -> Iterator[Path]:
        yield from sorted(original_rglob(self, pattern), reverse=True)

    monkeypatch.setattr(Path, "rglob", reversed_rglob)
    out = work_dir / "out.zip"
    make_zip.build_zip(dist, out)
    with zipfile.ZipFile(out) as archive:
        names = archive.namelist()
        infos = archive.infolist()
    assert names == sorted(names)
    for info in infos:
        assert info.date_time == (1980, 1, 1, 0, 0, 0)
        assert stat.S_IMODE(info.external_attr >> 16) == 0o644


def test_zip_names_equal_dist_file_list(dist: Path, work_dir: Path) -> None:
    out = work_dir / "out.zip"
    make_zip.build_zip(dist, out)
    expected = sorted(
        path.relative_to(dist).as_posix()
        for path in dist.rglob("*")
        if stat.S_ISREG(path.lstat().st_mode)
    )
    with zipfile.ZipFile(out) as archive:
        assert archive.namelist() == expected
        assert archive.read("js/lib/b.js") == b"b()"


def test_cli_builds_zip_and_rejects_missing_dir(dist: Path, work_dir: Path) -> None:
    out = work_dir / "cli.zip"
    ok = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(dist), str(out)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert ok.returncode == 0, ok.stderr
    assert out.is_file()
    missing = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(work_dir / "absent"), str(out)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert missing.returncode == 2
    assert "not a folder" in missing.stderr
