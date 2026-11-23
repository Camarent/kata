"""The trainer CLI wrapper drives the fake trainer script and maps bad runs to TrainerError."""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes import fake_trainer_cli
from kata_core.trainer.cli import Diagnostic, SubprocessTrainerCli, TrainerError


@pytest.fixture
def workdir() -> Iterator[Path]:
    """A throwaway working directory, removed at teardown."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def fake_cli() -> SubprocessTrainerCli:
    """The wrapper pointed at the fake trainer script, run through the current interpreter."""
    return SubprocessTrainerCli(
        argv_prefix=[sys.executable, str(Path(fake_trainer_cli.__file__))], timeout=30
    )


def _inline_cli(code: str, timeout: float = 30) -> SubprocessTrainerCli:
    return SubprocessTrainerCli(argv_prefix=[sys.executable, "-c", code], timeout=timeout)


def test_round_trip_against_fake(fake_cli: SubprocessTrainerCli, workdir: Path) -> None:
    assert fake_cli.next_id(workdir, "geo") == "i0001"
    assert fake_cli.add(workdir, "what is a noun") == "i0001"
    assert fake_cli.next_id(workdir, "geo") == "i0002"
    assert fake_cli.validate(workdir) == []
    fake_cli.lock(workdir)
    outdir = workdir / "out"
    files = fake_cli.build(workdir, outdir)
    assert files == [str(outdir / "course.json")]
    assert Path(files[0]).is_file()


def test_fake_invalid_item_yields_diagnostic(fake_cli: SubprocessTrainerCli, workdir: Path) -> None:
    fake_cli.add(workdir, "fine item")
    bad_id = fake_cli.add(workdir, "broken FAKE_INVALID item")
    assert fake_cli.validate(workdir) == [
        Diagnostic(item=bad_id, message="fake: marked invalid")
    ]


def test_item_text_is_passed_as_one_argument_not_a_shell(
    fake_cli: SubprocessTrainerCli, workdir: Path
) -> None:
    hostile = "x; touch should-not-exist $(echo no) `echo no`"
    fake_cli.add(workdir, hostile)
    stored = (workdir / fake_trainer_cli.ITEMS_FILE).read_text()
    assert hostile in stored
    assert not (Path.cwd() / "should-not-exist").exists()


def test_non_zero_exit_raises(workdir: Path) -> None:
    cli = _inline_cli("import sys; sys.stderr.write('boom'); sys.exit(3)")
    with pytest.raises(TrainerError, match="exited 3: boom"):
        cli.next_id(workdir, "geo")


def test_timeout_raises(workdir: Path) -> None:
    # The child sleeps far past the timeout, so the outcome does not depend on machine speed.
    cli = _inline_cli("import time; time.sleep(60)", timeout=0.5)
    with pytest.raises(TrainerError, match="timed out"):
        cli.lock(workdir)


def test_bad_json_raises(workdir: Path) -> None:
    cli = _inline_cli("print('not json')")
    with pytest.raises(TrainerError, match="invalid JSON"):
        cli.next_id(workdir, "geo")


def test_non_object_json_raises(workdir: Path) -> None:
    cli = _inline_cli("print('[1, 2]')")
    with pytest.raises(TrainerError, match="not an object"):
        cli.next_id(workdir, "geo")


def test_lock_not_ok_raises(workdir: Path) -> None:
    cli = _inline_cli("import json; print(json.dumps({'ok': False}))")
    with pytest.raises(TrainerError, match="lock did not report ok"):
        cli.lock(workdir)


def test_missing_executable_raises(workdir: Path) -> None:
    cli = SubprocessTrainerCli(argv_prefix=[str(workdir / "no-such-trainer")], timeout=5)
    with pytest.raises(TrainerError, match="could not start"):
        cli.next_id(workdir, "geo")
