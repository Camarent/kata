"""scripts/dev/install-browsers.sh: install dir, status exit codes, sha256 check. No network, no leaks."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "scripts" / "dev" / "install-browsers.sh"


def _run(args: list[str], browsers_dir: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "KATA_BROWSERS_DIR": str(browsers_dir)}
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _verify(file: Path, expected: str) -> subprocess.CompletedProcess[str]:
    """Source the script (main does not run) and call verify_sha256 on FILE."""
    return subprocess.run(
        ["bash", "-c", 'source "$1"; verify_sha256 "$2" "$3"', "_", str(SCRIPT), str(file), expected],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_script_is_executable():
    assert os.access(SCRIPT, os.X_OK)


def test_print_dir_uses_env_dir_and_exits_zero(tmp_path: Path):
    result = _run(["--print-dir"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(tmp_path)


def test_status_missing_exits_one(tmp_path: Path):
    result = _run(["--status"], tmp_path)
    assert result.returncode == 1


def test_status_present_exits_zero(tmp_path: Path):
    (tmp_path / "firefox").mkdir()
    firefox = tmp_path / "firefox" / "firefox"
    firefox.write_text("#!/bin/sh\n", encoding="utf-8")
    firefox.chmod(0o755)
    geckodriver = tmp_path / "geckodriver"
    geckodriver.write_text("#!/bin/sh\n", encoding="utf-8")
    geckodriver.chmod(0o755)
    result = _run(["--status"], tmp_path)
    assert result.returncode == 0


def test_status_with_only_firefox_exits_one(tmp_path: Path):
    (tmp_path / "firefox").mkdir()
    firefox = tmp_path / "firefox" / "firefox"
    firefox.write_text("#!/bin/sh\n", encoding="utf-8")
    firefox.chmod(0o755)
    result = _run(["--status"], tmp_path)
    assert result.returncode == 1


def test_verify_accepts_matching_sha256(tmp_path: Path):
    artifact = tmp_path / "artifact.tar"
    artifact.write_bytes(b"pinned payload")
    digest = hashlib.sha256(b"pinned payload").hexdigest()
    result = _verify(artifact, digest)
    assert result.returncode == 0, result.stderr


def test_verify_rejects_tampered_artifact(tmp_path: Path):
    artifact = tmp_path / "artifact.tar"
    artifact.write_bytes(b"tampered payload")
    pinned = hashlib.sha256(b"pinned payload").hexdigest()
    result = _verify(artifact, pinned)
    assert result.returncode != 0
    assert "sha256 mismatch" in result.stderr


def test_verify_refuses_empty_pin(tmp_path: Path):
    artifact = tmp_path / "artifact.tar"
    artifact.write_bytes(b"pinned payload")
    result = _verify(artifact, "")
    assert result.returncode != 0
    assert "refusing to install" in result.stderr


def _make_tarball(root: Path) -> Path:
    """A local tar.gz holding one file, fetched through file:// (no network)."""
    src = root / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "tool").write_text("#!/bin/sh\n", encoding="utf-8")
    archive = root / "pkg.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(src / "pkg", arcname="pkg")
    return archive


def _fetch(archive: Path, sha: str, dest: Path) -> subprocess.CompletedProcess[str]:
    """Source the script, fetch+verify+unpack a FILE:// URL from inside a function, as install_all does.

    The enclosing function returning after fetch is what exposes a RETURN trap that outlives it.
    """
    script = (
        'source "$1"; _install() { fetch_verified_unpack "$1" "$2" "$3"; echo fetched; }; _install "$2" "$3" "$4"'
    )
    return subprocess.run(
        ["bash", "-c", script, "_", str(SCRIPT), archive.as_uri(), sha, str(dest)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_fetch_verified_unpack_installs_and_survives_later_return(tmp_path: Path):
    archive = _make_tarball(tmp_path)
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    dest = tmp_path / "out"
    result = _fetch(archive, sha, dest)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "fetched"
    assert (dest / "pkg" / "tool").is_file()


def test_fetch_verified_unpack_rejects_tampered_archive_before_unpack(tmp_path: Path):
    archive = _make_tarball(tmp_path)
    dest = tmp_path / "out"
    result = _fetch(archive, "0" * 64, dest)
    assert result.returncode != 0
    assert "sha256 mismatch" in result.stderr
    assert not dest.exists()
