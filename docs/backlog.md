# Backlog

Project items after Milestone 0.

## Open items

- [ ] Load the extension in a real browser (side panel, content script, background wiring,
      real sign-in and "I know this" against a running core). Milestone 0 only checked the
      panel with stubs.
- [ ] Side panel: check dark-theme contrast and keyboard focus and tab order.
- [x] Coverage: vitest coverage for the extension, pytest-cov for core and worker, a
      recorded baseline and a jscpd duplicate-code report (report only, see
      [`development.md`](development.md)). Still open: a coverage floor (a minimum percentage
      that fails the gate), not yet decided.
- [ ] Narrow the `<all_urls>` content-script permission in `extension/manifest.json` before
      any publish.
- [x] Python dependencies are pinned with `==` and there is no lock file. Decided: keep the
      `==` pins, no `uv lock` (see [`decisions.md`](decisions.md)).
- [ ] Style nits: three `nosec` lines longer than 100 columns; `MarkSink` vs
      `Pick<CoreClient>`.
- [x] Combined pytest run collected badly: three `conftest.py` files shadowed each other
      (`from conftest import ...`). Fixed by moving the shared helper to `tests/support`.
- [ ] Decide whether to track a copy of the project instructions file and the audit tool list,
      which are currently excluded from git.
- [ ] Embeddings, cloud model path, concept-level marks and the guided screen are out of scope
      until later milestones (see [`roadmap.md`](roadmap.md)).
- [x] Reproducible Postgres test setup: `scripts/dev/pg.sh`, see [`development.md`](development.md).
- [ ] The extension manifest allows only `http://127.0.0.1:8080/*`, so a core reached over a VPN
      or another port needs a manifest change (request the host permission at sign-in).
- [x] `tools/gates.json` uses a pipeline wrapper (`cs-qrun`) that a clean clone does not have.
      Closed: `scripts/dev/check-all.sh` is the clean-clone gate with plain commands;
      `gates.json` keeps the wrapper for the pipeline runner (see
      [`development.md`](development.md)).
- [ ] Several API tests were pinned to a fixed date and failed once the real clock passed the
      token lifetime; fixed, but check new tests for fixed dates.
