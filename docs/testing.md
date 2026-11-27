# Testing: timings

This page records how long the local gates take. It is a baseline, not a target.

## Before

Baseline taken after the cleanup-m25 tasks and before the speed task 16. Measured 2026-11-27.

Command: `scripts/dev/check-all.sh --py` (ruff, mypy, pytest with coverage, `-m 'not browser'`,
flaky tests included). No driver or stage was running. Machine: 8 cores, load average 0.45 to
0.68 before the run and 0.58 after (1-minute value, idle enough that the timings are not skewed).

| Phase | Wall time |
|---|---|
| ruff (`.venv/bin/ruff check .`) | about 2.0 s |
| mypy (`env MYPYPATH=worker .venv/bin/mypy core scripts/smoke/...`) | about 3.4 s |
| pytest (2686 passed, 38 deselected, 1 warning) | 178.1 s (pytest's own clock) |
| **Total, one bare `check-all.sh --py` run** | **181.7 s** |

The ruff and mypy times are from separate timed runs of the same commands, wrapped by the
`cs-qrun` runner. They include runner overhead, so the three phases do not add up exactly to the
total.

### Slowest tests

`pytest --durations=15` output, same selection as the `--py` gate. Paths are repo-relative:

```
7.52s call     tests/foundation/test_conftest_tiers.py::test_tier_selection_matches_directories
2.49s call     tests/foundation/test_conftest_tiers.py::test_smoke_selection_yields_exactly_two_items
1.50s call     tests/worker/test_loop.py::test_run_forever_survives_unreachable_core
1.49s call     tests/scripts/test_restore.py::test_restore_with_counts_file_fails_on_mismatch
1.34s call     tests/core/test_api_progress_wire.py::test_second_put_with_same_counters_writes_no_evidence
1.14s call     tests/e2e/test_lesson_round_trip.py::test_lesson_round_trip
1.11s call     tests/core/test_course_limit_race.py::test_limit_lets_one_of_two_concurrent_creates_through
1.11s call     tests/e2e/test_fixtures.py::test_running_worker_tags_a_queued_job
1.03s call     tests/scripts/test_relocate.py::test_real_run_copies_files_by_path_and_verifies
1.03s call     tests/scripts/test_restore.py::test_restore_then_verify_passes_and_row_delete_fails
1.02s call     tests/core/test_api_course_progress.py::test_patch_merges_delta_and_writes_evidence_for_delta_item...
1.01s call     tests/worker/test_providers.py::test_local_timeout_raises_provider_error
1.00s call     tests/reader/test_sandbox.py::test_hung_child_times_out
1.00s call     tests/worker/test_modelhost_ctl.py::test_timeout_holds_even_when_grandchild_keeps_stdout
1.00s teardown tests/worker/test_loop.py::test_model_error_fails_job_and_loop_continues
```

The last line is a teardown phase, not a call phase. The list is pytest's output as printed.
Pytest truncates long node ids with `...`.
