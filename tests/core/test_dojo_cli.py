"""The dojo adapter drives the fake `dojo` script (real text formats) and maps bad runs to TrainerError."""

from __future__ import annotations

import json
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes import fake_dojo
from kata_core.trainer.cli import Diagnostic, TrainerError
from kata_core.trainer.dojo_cli import DojoTrainerCli

GEO_ITEM = '{"type": "gap", "unit": "geo", "prompt": "The capital of Italy is ___.", "answers": ["Rome"]}'


@pytest.fixture
def workdir() -> Iterator[Path]:
    """A throwaway working directory, removed at teardown."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def dojo() -> DojoTrainerCli:
    """The adapter pointed at the fake dojo script, run through the current interpreter."""
    return DojoTrainerCli(argv_prefix=[sys.executable, str(Path(fake_dojo.__file__))], timeout=30)


def _inline(code: str, timeout: float = 30) -> DojoTrainerCli:
    return DojoTrainerCli(argv_prefix=[sys.executable, "-c", code], timeout=timeout)


def _item(prompt: str) -> str:
    return f'{{"type": "gap", "unit": "geo", "prompt": "{prompt}", "answers": ["Rome"]}}'


def test_next_id_reads_text_id(dojo: DojoTrainerCli, workdir: Path) -> None:
    assert dojo.next_id(workdir, "geo") == "geo-1"
    dojo.add(workdir, GEO_ITEM)
    assert dojo.next_id(workdir, "geo") == "geo-2"


def test_next_id_bad_prefix_raises(dojo: DojoTrainerCli, workdir: Path) -> None:
    # The unit is refused before dojo runs, so no dojo exit code is involved.
    with pytest.raises(TrainerError, match="invalid unit"):
        dojo.next_id(workdir, "Bad Prefix")


@pytest.mark.parametrize("unit", ["a/b", "..", "geo x", "geo\tx", "-geo", ""])
def test_unit_outside_name_charset_raises(dojo: DojoTrainerCli, workdir: Path, unit: str) -> None:
    with pytest.raises(TrainerError, match="invalid unit"):
        dojo.next_id(workdir, unit)


def test_add_sends_json_on_stdin_and_parses_id(dojo: DojoTrainerCli, workdir: Path) -> None:
    assert dojo.add(workdir, GEO_ITEM) == "geo-1"
    stored = (workdir / fake_dojo.CONTENT_DIR / "geo.jsonl").read_text()
    assert '"id": "geo-1"' in stored
    assert '"prompt": "The capital of Italy is ___."' in stored


def test_init_returns_course_folder_from_created_line(dojo: DojoTrainerCli, workdir: Path) -> None:
    course = dojo.init(workdir, "geo-course", "Geography")
    assert course == workdir / "geo-course"
    assert (course / fake_dojo.COURSE_FILE).is_file()


def test_init_without_created_line_raises(workdir: Path) -> None:
    with pytest.raises(TrainerError, match="no course folder"):
        _inline("pass").init(workdir, "geo", "Geography")


@pytest.mark.parametrize("course_id", ["--workspace", "a/b", "", "geo x"])
def test_init_course_id_outside_name_charset_raises(dojo: DojoTrainerCli, workdir: Path, course_id: str) -> None:
    with pytest.raises(TrainerError, match="invalid course id"):
        dojo.init(workdir, course_id, "Geography")


def test_add_unit_missing_from_course_json_raises(dojo: DojoTrainerCli, workdir: Path) -> None:
    course = dojo.init(workdir, "geo-course", "Geography")
    unknown = '{"type": "gap", "unit": "unit-2", "prompt": "p", "answers": ["a"]}'
    with pytest.raises(TrainerError, match="does not exist in course.json"):
        dojo.add(course, unknown)


def test_add_known_hyphenated_unit_accepted(dojo: DojoTrainerCli, workdir: Path) -> None:
    course = dojo.init(workdir, "geo-course", "Geography")
    known = '{"type": "gap", "unit": "unit-1", "prompt": "p", "answers": ["a"]}'
    assert dojo.add(course, known) == "unit-1-1"


def test_add_shape_error_raises(dojo: DojoTrainerCli, workdir: Path) -> None:
    with pytest.raises(TrainerError, match="shape error"):
        dojo.add(workdir, '{"unit": "geo"}')


def test_add_without_unit_raises(dojo: DojoTrainerCli, workdir: Path) -> None:
    with pytest.raises(TrainerError, match="no unit"):
        dojo.add(workdir, '{"type": "gap", "prompt": "x", "answers": ["a"]}')


def test_add_non_json_raises(dojo: DojoTrainerCli, workdir: Path) -> None:
    with pytest.raises(TrainerError, match="not JSON"):
        dojo.add(workdir, "geo item")


def test_validate_names_item_id_from_message(dojo: DojoTrainerCli, workdir: Path) -> None:
    bad_id = dojo.add(workdir, _item("broken FAKE_INVALID item"))
    assert dojo.validate(workdir) == [
        Diagnostic(item=bad_id, message=f"{bad_id}: fake marked invalid")
    ]


def test_validate_falls_back_to_file_line(dojo: DojoTrainerCli, workdir: Path) -> None:
    dojo.add(workdir, _item("no id here FAKE_NOID"))
    assert dojo.validate(workdir) == [
        Diagnostic(item="content/geo.jsonl:1", message="answers list is empty")
    ]


def test_validate_warnings_only_exit_zero(dojo: DojoTrainerCli, workdir: Path) -> None:
    warned = dojo.add(workdir, _item("answer in FAKE_WARN prompt"))
    assert dojo.validate(workdir) == [Diagnostic(item=warned, message=f"{warned}: fake warning")]


def test_validate_exit_two_raises(dojo: DojoTrainerCli, workdir: Path) -> None:
    with pytest.raises(TrainerError, match="exited 2"):
        dojo.validate(workdir / "missing")


def test_validate_exit_two_with_diagnostics_still_raises() -> None:
    # A usage failure is never read as diagnostics, even when the output parses.
    code = (
        "import json, sys; print(json.dumps({'ok': False, 'errors': 1, 'diagnostics': "
        "[{'severity': 'error', 'code': 'x', 'file': 'f', 'line': 1, 'message': 'geo-1: bad'}]}));"
        " sys.exit(2)"
    )
    with pytest.raises(TrainerError, match="exited 2"):
        _inline(code).validate(Path("."))


def test_validate_exit_one_without_errors_raises() -> None:
    code = "import json, sys; print(json.dumps({'ok': False, 'errors': 0, 'diagnostics': []})); sys.exit(1)"
    with pytest.raises(TrainerError, match="no errors"):
        _inline(code).validate(Path("."))


def test_lock_ok_writes_ids_lock(dojo: DojoTrainerCli, workdir: Path) -> None:
    dojo.add(workdir, GEO_ITEM)
    dojo.lock(workdir)
    assert (workdir / "ids.lock").is_file()


def test_lock_failure_raises(dojo: DojoTrainerCli, workdir: Path) -> None:
    dojo.add(workdir, _item("bad FAKE_INVALID"))
    with pytest.raises(TrainerError, match="lock exited 1"):
        dojo.lock(workdir)


def test_build_lists_manifest_files_plus_index(dojo: DojoTrainerCli, workdir: Path) -> None:
    dojo.add(workdir, GEO_ITEM)
    outdir = workdir / "out"
    course = workdir.name
    assert dojo.build(workdir, outdir) == [
        f"{course}/data/content.json",
        f"{course}/index.html",
        f"{course}/manifest.json",
    ]


def test_build_without_manifest_files_walks_course_dir(workdir: Path) -> None:
    # The builder writes a manifest with no `files` key: the course dir is walked instead.
    code = (
        "import pathlib, sys; site = pathlib.Path(sys.argv[4]) / 'geo-course'; "
        "(site / 'data').mkdir(parents=True); "
        "(site / 'index.html').write_text('x'); "
        "(site / 'data' / 'content.json').write_text('[]'); "
        "(site / 'manifest.json').write_text('{}')"
    )
    files = _inline(code).build(workdir, workdir / "out")
    assert files == [
        "geo-course/data/content.json",
        "geo-course/index.html",
        "geo-course/manifest.json",
    ]


def test_build_manifest_file_missing_raises(workdir: Path) -> None:
    code = (
        "import json, pathlib, sys; site = pathlib.Path(sys.argv[4]) / 'geo-course'; "
        "site.mkdir(parents=True); (site / 'index.html').write_text('x'); "
        "(site / 'manifest.json').write_text(json.dumps({'files': ['gone.json']}))"
    )
    with pytest.raises(TrainerError, match="gone.json"):
        _inline(code).build(workdir, workdir / "out")


def test_build_zero_course_dirs_raises(workdir: Path) -> None:
    code = "import pathlib, sys; pathlib.Path(sys.argv[4]).mkdir(parents=True)"
    with pytest.raises(TrainerError, match="wrote 0 course dirs"):
        _inline(code).build(workdir, workdir / "out")


def test_build_many_course_dirs_raises(workdir: Path) -> None:
    code = (
        "import pathlib, sys; out = pathlib.Path(sys.argv[4]); "
        "(out / 'a').mkdir(parents=True); (out / 'b').mkdir()"
    )
    with pytest.raises(TrainerError, match="wrote 2 course dirs"):
        _inline(code).build(workdir, workdir / "out")


def test_build_content_error_raises(dojo: DojoTrainerCli, workdir: Path) -> None:
    dojo.add(workdir, _item("bad FAKE_INVALID"))
    with pytest.raises(TrainerError, match="exited 1"):
        dojo.build(workdir, workdir / "out")


def test_unit_with_shell_characters_is_refused(workdir: Path) -> None:
    # Shell metacharacters never reach argv: the unit is refused before any process starts.
    cli = _inline("raise SystemExit('dojo must not run')")
    with pytest.raises(TrainerError, match="invalid unit"):
        cli.next_id(workdir, "geo;$(echo no)")


def test_unit_is_one_argument_not_a_shell(workdir: Path) -> None:
    # The fake-free inline script echoes its last argument: a valid unit arrives unchanged.
    unit = "geo_2-x"
    cli = _inline("import sys; print(sys.argv[-1] + '-1')")
    assert cli.next_id(workdir, unit) == f"{unit}-1"


def test_build_symlink_to_file_outside_course_raises(workdir: Path) -> None:
    secret = workdir / "secret.txt"
    secret.write_text("outside")
    code = (
        "import json, os, pathlib, sys; site = pathlib.Path(sys.argv[4]) / 'geo-course'; "
        "site.mkdir(parents=True); (site / 'index.html').write_text('x'); "
        "os.symlink(" + repr(str(secret)) + ", site / 'linked.txt'); "
        "(site / 'manifest.json').write_text(json.dumps({'files': ['linked.txt']}))"
    )
    with pytest.raises(TrainerError, match="symlink or outside"):
        _inline(code).build(workdir, workdir / "out")


def test_build_symlink_to_file_inside_course_raises(workdir: Path) -> None:
    # Inside the course dir the resolve() check passes: only the symlink check refuses it.
    code = (
        "import json, os, pathlib, sys; site = pathlib.Path(sys.argv[4]) / 'geo-course'; "
        "site.mkdir(parents=True); (site / 'index.html').write_text('x'); "
        "(site / 'real.txt').write_text('inside'); "
        "os.symlink(site / 'real.txt', site / 'alias.txt'); "
        "(site / 'manifest.json').write_text(json.dumps({'files': ['alias.txt']}))"
    )
    with pytest.raises(TrainerError, match="is a symlink"):
        _inline(code).build(workdir, workdir / "out")


def test_build_symlink_found_by_walk_raises(workdir: Path) -> None:
    secret = workdir / "secret.txt"
    secret.write_text("outside")
    code = (
        "import os, pathlib, sys; site = pathlib.Path(sys.argv[4]) / 'geo-course'; "
        "site.mkdir(parents=True); (site / 'index.html').write_text('x'); "
        "os.symlink(" + repr(str(secret)) + ", site / 'linked.txt')"
    )
    with pytest.raises(TrainerError, match="is a symlink"):
        _inline(code).build(workdir, workdir / "out")


def test_timeout_raises(workdir: Path) -> None:
    # The child sleeps far past the timeout, so the outcome does not depend on machine speed.
    cli = _inline("import time; time.sleep(60)", timeout=0.5)
    with pytest.raises(TrainerError, match="timed out"):
        cli.lock(workdir)


def test_missing_executable_raises(workdir: Path) -> None:
    cli = DojoTrainerCli(argv_prefix=[str(workdir / "no-such-dojo")], timeout=5)
    with pytest.raises(TrainerError, match="could not start"):
        cli.next_id(workdir, "geo")


# Records the build argv (JSON, in the workdir) and writes the course folder the adapter expects.
_RECORD_BUILD = (
    "import json, pathlib, sys; "
    "pathlib.Path(sys.argv[2], 'argv.json').write_text(json.dumps(sys.argv[1:])); "
    "site = pathlib.Path(sys.argv[4]) / 'geo-course'; "
    "(site / 'data').mkdir(parents=True); "
    "(site / 'index.html').write_text('x'); "
    "(site / 'data' / 'content.json').write_text('[]'); "
    "(site / 'manifest.json').write_text('{}')"
)


def _build_argv(cli: DojoTrainerCli, workdir: Path) -> list[str]:
    cli.build(workdir, workdir / "out")
    return json.loads((workdir / "argv.json").read_text())


def test_build_omits_asset_flags_when_empty(workdir: Path) -> None:
    cli = _inline(_RECORD_BUILD)
    assert _build_argv(cli, workdir) == ["build", str(workdir), "--out", str(workdir / "out")]


def test_build_passes_asset_flags_when_set(workdir: Path) -> None:
    cli = DojoTrainerCli(
        argv_prefix=[sys.executable, "-c", _RECORD_BUILD],
        timeout=30,
        wasm="assets/wasm",
        web="assets/web",
    )
    assert _build_argv(cli, workdir) == [
        "build",
        str(workdir),
        "--out",
        str(workdir / "out"),
        "--wasm",
        "assets/wasm",
        "--web",
        "assets/web",
    ]
