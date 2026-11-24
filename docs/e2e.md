# End-to-end test guide

The end-to-end test in `tests/e2e/` runs the whole Milestone 0 loop in one process tree: the browser extension scans a lesson, the worker tags each block through a fake model, the user presses "I know this" on the first topic, and a second device of the same user reads the mark back.

## What the test covers

1. **Scan.** A Node driver enrols its device with the issued code, then runs the bundled extension code on a lesson page (three paragraphs in the test) and sends each block to the core for tagging.
2. **Tag.** The worker leases each queued job, asks the fake model for a category and topic, and writes the topic back to the core.
3. **I know this.** The driver presses "I know this" on the first block's topic through its offline queue. The core stores a mark with status `known`.
4. **Read back.** A second device of the same user calls `GET /marks` over HTTP, independent of the driver, and must see the same mark.

## Prerequisites

- **Postgres** reachable through the config file named in `KATA_CONFIG`. The database user needs `CREATEDB`, because the tests create and drop their own databases. Set the password environment variable the config names. The test fails, and does not skip, when Postgres is unreachable. See the Tests section of `docs/api.md`.
- **Node and npm** for the extension. The Node version is not pinned in the repo (see `docs/modules/extension.md`).
- **Extension dependencies installed.** Run `npm install` in `extension/` once. The test bundles `tests/e2e/driver.ts` with `extension/node_modules/.bin/esbuild` and needs `jsdom` from `extension/node_modules`.
- **Python dependencies** for `core/`, `worker/` and `tests/`, installed in the same way as for the rest of the suite.

## Command

```
python3 -m pytest tests/e2e
```

`KATA_CONFIG` must point at your `kata.toml` in the environment. Run `KATA_CONFIG=path/to/kata.toml python3 -m pytest tests/e2e` to set it for one run.

Run it from the repository root. To run only the round trip: `python3 -m pytest tests/e2e/test_lesson_round_trip.py`.

## How the pieces connect

- **Live core.** `live_core` in `tests/e2e/conftest.py` serves the core app with uvicorn in a thread, on `127.0.0.1` at a free port, against a scratch database.
- **Enrolment.** `enrolled` and `issue_code` create users and devices through the core, so each device gets a real bearer token.
- **Fake model.** `fake_model` (`tests/fakes/fake_model.py`) is an HTTP server in a thread. It returns scripted replies in order and records each request. The worker reads its URL from `KATA_MODEL_BASE_URL`.
- **Worker.** `running_worker` runs `kata_worker.loop.run_forever` in a thread. It reads `KATA_WORKER_CORE_URL` and polls every second.
- **Node driver.** `run_driver` runs the bundled driver with `node` on a JSON payload (base URL, code, HTML, poll interval, max wait). It prints one JSON line with `results` and `marksAfterPress`.

## What a failure looks like

| Stage | Symptom | Where to look |
| --- | --- | --- |
| Setup | `driver_js` fails with an esbuild error in `assert proc.returncode == 0` | `extension/node_modules` missing, or `npm install` not run |
| Setup | Connection or authentication error before any test step | Postgres unreachable or wrong `KATA_CONFIG` |
| Scan | `proc.returncode` is non-zero; the assertion prints the driver's stderr | the driver stderr, `tests/e2e/driver.ts` |
| Tag | `job <id> not done: {...}` after the poll deadline | the worker thread: is it alive, is `KATA_WORKER_CORE_URL` right |
| Tag | `len(fake_model.requests)` differs from the number of blocks | scripted replies in `fake_model` ran out or a job was tagged twice |
| Topic set | sorted topics differ from the scripted topics | job-to-block mapping in the core, or the reply order |
| I know this | `marksAfterPress` differs from the expected single `known` mark | the driver's `OfflineQueue.markKnown` path and the core marks route (`core/kata_core/api/routes/marks.py`) |
| Read back | `GET /marks` returns a non-200 status, or a list that differs from the press | the core marks route and the device token of the second device |

## Browser tests

`tests/browser/` drives a real browser with selenium: the built extension loads in Firefox, the content script scans a static lesson page served on `127.0.0.1`, and the side panel page loads (`tests/browser/test_panel_flow.py`). It is parametrized over `firefox` and `chrome`. Decision and reasons: `docs/decisions.md`.

Test files:

- `tests/browser/test_panel_a11y.py`: keyboard order and focus indicator of the sign-in view. Asserts the Tab order `code`, `deviceLabel`, submit button, that each focused control is inside `form.signin`, and that each shows an outline or box-shadow.
- `tests/browser/test_panel_contrast.py`: dark-theme WCAG 2.x contrast of the sign-in view. Asserts every text element reaches a 4.5 to 1 ratio against its effective background, with dark mode forced; skips with a reason when the browser does not report dark mode.

Prerequisites:

- **Browser install.** `scripts/dev/install-browsers.sh` installs Firefox 140.0esr and geckodriver 0.36.0 into `$KATA_BROWSERS_DIR` (default `$HOME/.cache/kata-browsers`), with sha256 checks. Run it once; `scripts/dev/install-browsers.sh --status` checks it with no network. Chrome and chromedriver are not installed by the script: they are looked up on `PATH`.
- **Selenium** from `requirements-browser.txt`. `check-all.sh --browser` installs it into `.venv`.
- **Built extension.** `npm run build` in `extension/` writes `extension/dist/firefox/` and `extension/dist/chrome/`. A missing build fails the Browser test, it does not skip.
- **No Postgres** is needed.

Command:

```
scripts/dev/check-all.sh --browser
```

To run only the browser tests by hand: `.venv/bin/python -m pytest tests/browser -m browser`.

Skip behaviour:

- With no Firefox or geckodriver in the install, `check-all.sh --browser` prints `check-all: browser tests skipped: ...` and exits 0. Each Firefox case skips with a reason too.
- A Chrome case skips with a reason when `google-chrome`, `chromium` or `chromedriver` is not on `PATH`.
- A skip is not a pass. Read the skip lines of `pytest tests/browser -m browser -rs`; an all-skipped run is not a browser check.
- The Chrome case has never run against a real Chrome. See `docs/decisions.md` for the open risk.
- The browser marker is excluded from every other gate. CI and the default `check-all.sh` never run these tests.

## Notes

- The end-to-end test in `tests/e2e/` does not skip. A missing prerequisite fails it. The Browser tests above do skip, with a reason.
- Jobs are claimed in no fixed order, so the test compares the set of topics, not their order.
