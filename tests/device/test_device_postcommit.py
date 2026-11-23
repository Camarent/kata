import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import kata_device
import pytest
from kata_device import gitutil, postcommit, precommit
from kata_device.marker import read_marker
from kata_device.queue import read_queue

AT = datetime(2026, 11, 21, 9, 30, tzinfo=UTC)
CORE_DIR = Path(kata_device.__file__).resolve().parents[1]
BYPASSED = [{"kind": "precommit", "detail": {"result": "bypassed"}, "at": AT.isoformat()}]


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return proc.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "kata test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    return tmp_path


def _write(repo: Path, text: str) -> None:
    (repo / "a.txt").write_text(text, encoding="utf-8")
    _git(repo, "add", "a.txt")


def _commit(repo: Path, *, no_verify: bool = False) -> None:
    args = ["commit", "-q", "-m", "change"]
    if no_verify:
        args.append("--no-verify")
    _git(repo, *args)


def _pre(repo: Path) -> int:
    return precommit.main([], repo=repo, now=lambda: AT)


def _post(repo: Path) -> int:
    return postcommit.main([], repo=repo, now=lambda: AT)


def _queue(repo: Path) -> list[dict[str, object]]:
    return read_queue(gitutil.git_dir(repo))


def _install_hooks(repo: Path) -> None:
    """Install both hooks as shell scripts that call the device module, the way `kata hooks` does."""
    hooks = gitutil.git_dir(repo) / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    for hook, sub in (("pre-commit", "precommit"), ("post-commit", "postcommit")):
        script = (
            "#!/bin/sh\n"
            f"exec env PYTHONPATH={CORE_DIR} {sys.executable} -m kata_device {sub} \"$@\"\n"
        )
        path = hooks / hook
        path.write_text(script, encoding="utf-8")
        path.chmod(0o755)


def test_pass_then_commit_leaves_no_entry_and_no_marker(repo: Path) -> None:
    _write(repo, "one\n")
    assert _pre(repo) == 0
    _commit(repo)

    assert _post(repo) == 0

    assert _queue(repo) == []
    assert read_marker(gitutil.git_dir(repo)) is None


def test_commit_without_precommit_is_one_bypass_entry(repo: Path) -> None:
    _write(repo, "one\n")
    _commit(repo, no_verify=True)

    assert _post(repo) == 0

    assert _queue(repo) == BYPASSED


def test_abort_then_different_tree_is_bypass_and_clears_marker(repo: Path) -> None:
    _write(repo, "one\n")
    assert _pre(repo) == 0
    _write(repo, "two\n")  # the checked tree was abandoned; a different tree is committed
    _commit(repo, no_verify=True)

    assert _post(repo) == 0

    assert _queue(repo) == BYPASSED
    assert read_marker(gitutil.git_dir(repo)) is None


def test_stale_marker_detects_later_bypass_of_the_same_tree(repo: Path) -> None:
    _write(repo, "one\n")
    assert _pre(repo) == 0  # marker holds tree T1, the commit is never made
    _write(repo, "two\n")
    _commit(repo, no_verify=True)  # intermediate commit of tree T2
    assert _post(repo) == 0
    assert _queue(repo) == BYPASSED

    _write(repo, "one\n")  # back to tree T1, committed without the check
    _commit(repo, no_verify=True)
    assert _post(repo) == 0

    assert _queue(repo) == BYPASSED * 2
    assert read_marker(gitutil.git_dir(repo)) is None


@pytest.mark.parametrize(
    "state",
    [
        ("rebase-merge", "dir"),
        ("rebase-apply", "dir"),
        ("MERGE_HEAD", "file"),
        ("CHERRY_PICK_HEAD", "file"),
        ("REVERT_HEAD", "file"),
    ],
)
def test_operation_in_progress_is_skipped_and_marker_kept(repo: Path, state: tuple[str, str]) -> None:
    name, kind = state
    _write(repo, "one\n")
    assert _pre(repo) == 0
    _commit(repo, no_verify=True)
    git_dir = gitutil.git_dir(repo)
    marker_before = read_marker(git_dir)
    assert marker_before is not None
    if kind == "dir":
        (git_dir / name).mkdir()
    else:
        (git_dir / name).write_text("0" * 40 + "\n", encoding="utf-8")

    assert _post(repo) == 0

    assert _queue(repo) == []
    assert read_marker(git_dir) == marker_before


def test_real_git_commit_with_hooks_installed(repo: Path) -> None:
    _install_hooks(repo)
    _write(repo, "one\n")
    _git(repo, "commit", "-q", "-m", "checked")  # pre-commit marks the tree, post-commit clears it
    assert _queue(repo) == []
    assert read_marker(gitutil.git_dir(repo)) is None

    _write(repo, "two\n")
    _git(repo, "commit", "-q", "--no-verify", "-m", "unchecked")  # post-commit alone sees it

    # the hook stamps the wall clock, so only kind and detail are compared
    assert [(r["kind"], r["detail"]) for r in _queue(repo)] == [("precommit", {"result": "bypassed"})]
    assert read_marker(gitutil.git_dir(repo)) is None
