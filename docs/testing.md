# Testing: timings

This page records how long the local gates take before and after the speed-up, and checks each
level against its target.

## Targets

The gate levels must fit these wall-time limits:

| Level | Command | Target |
|---|---|---|
| unit | `scripts/dev/check-all.sh --unit` | 2 min (120 s) |
| merge | `scripts/dev/check-all.sh --merge` | 5 min (300 s) |
| full | `scripts/dev/check-all.sh` | 9 min (540 s) |

## Before

Baseline taken after the cleanup-m25 tasks and before the speed task 16. Measured 2026-11-27.

Command: `scripts/dev/check-all.sh --py` (ruff, mypy, pytest with coverage, `-m 'not browser'`,
flaky tests included). No driver or stage was running. Machine: 8 cores, load average 0.45 to
0.68 before the run and 0.58 after (1-minute value, idle enough that the timings are not skewed).

| Phase | Wall time |
|---|---|
| ruff (`.venv/bin/ruff check .`) | about 2.0 s |
| mypy (`env MYPYPATH=worker .venv/bin/mypy core scripts/smoke/...`) | about 3.4 s |
| pytest | 178.1 s (pytest's own clock) |
| **Total, one bare `check-all.sh --py` run** | **181.7 s** |

The ruff and mypy times are from separate timed runs of the same commands, wrapped by the
timing wrapper. They include wrapper overhead, so the three phases do not add up exactly to the
total.

Per level, one bare run each, on the same machine class, from a temporary checkout of `f0f551e`
(the commit just before the speed-up). That checkout had `.venv` and `extension/node_modules`
set up by `--setup`. Load average was not sampled for these runs. The columns match After.

| Level | Wall time | pytest (own clock) | Other | Target | Met |
|---|---|---|---|---|---|
| unit | 51.3 s | 48.6 s | 2.7 s | 120 s | yes |
| merge | 200.5 s | 176.7 s | 23.8 s | 300 s | yes |
| full | 204.8 s | 177.0 s (plus 4.4 s smoke) | 23.4 s | 540 s | yes |

## After

Measured after task 16 on the same machine class, one bare run per level, no driver running.
Each run was started from a plain subprocess call (wall time), and pytest's own clock is taken
from the pytest summary line in the run log. "Other" is the wall time minus pytest and minus the
smoke step (only the full level runs smoke). The table splits pytest from the rest; it does not
time each non-pytest phase alone. What each level's "Other" contains:

- unit: ruff and mypy.
- py: Postgres start, ruff and mypy.
- merge: Postgres start, extension build and test (with the JS audit), editor build and test. No lint.
- full: Postgres start, ruff and mypy, extension build and test (with the JS audit), editor build and
  test, jscpd report.

The Before phase table (ruff about 2.0 s, mypy about 3.4 s, cold caches) is a separate timing and
is not re-timed per level after task 16. The py "Other" of 2.4 s is smaller than that cold lint
cost (about 5.4 s), so the lint share of the After "Other" values is not established. Do not
subtract the Before lint figures from the After "Other" values.

| Level | Wall time | pytest (own clock) | Other | Target | Met |
|---|---|---|---|---|---|
| unit | 26.2 s | 20.7 s | 5.5 s | 120 s | yes |
| merge | 100.9 s | 77.1 s | 23.8 s | 300 s | yes |
| full | 103.3 s | 74.1 s (plus 4.6 s smoke) | 24.6 s | 540 s | yes |
| py (not a gate level) | 85.0 s | 82.6 s | 2.4 s | none | n/a |

All three gate levels meet their targets. Browser tests are not in any of these levels.
The remaining slowest phase is pytest in merge and full, about 75 s each.

### Slowest tests (pre-speed run)

The slowest tests below are from the pre-speed `--py` run (see Before), not re-measured after task 16.
`pytest --durations=15` output, same selection as the `--py` gate. Paths are repo-relative.

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
