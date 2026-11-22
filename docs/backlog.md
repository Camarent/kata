# Backlog

Project items after Milestone 0.

## Open items

- [ ] Load the extension in a real browser (side panel, content script, background wiring,
      real sign-in and "I know this" against a running core). Milestone 0 only checked the
      panel with stubs.
- [x] Side panel: check dark-theme contrast and keyboard focus and tab order. Sign-in view only;
      the review screen is not covered (see [`decisions.md`](decisions.md)).
- [x] Coverage: vitest coverage for the extension, pytest-cov for core and worker, a
      recorded baseline and a jscpd duplicate-code report (report only, see
      [`development.md`](development.md)). Still open: a coverage floor (a minimum percentage
      that fails the gate), not yet decided.
- [ ] Narrow the `<all_urls>` content-script permission in `extension/manifest.base.json` before
      any publish. Note: the match is now `http://*/*` and `https://*/*` in
      `extension/manifest.base.json` (see [`decisions.md`](decisions.md)); still host-wide.
- [x] Python dependencies are pinned with `==` and there is no lock file. Decided: keep the
      `==` pins, no `uv lock` (see [`decisions.md`](decisions.md)).
- [ ] Style nits: three `nosec` lines longer than 100 columns; `MarkSink` vs
      `Pick<CoreClient>`.
- [x] Combined pytest run collected badly: three `conftest.py` files shadowed each other
      (`from conftest import ...`). Fixed by moving the shared helper to `tests/support`.
- [ ] Decide whether to track a copy of the project instructions file and the audit tool list,
      which are currently excluded from git.
- [x] Embeddings and the cloud model path (Milestone 3 adapters, policy, scanner, cost cap,
      routing chains). Still out of scope: concept-level marks and the guided screen (see
      [`roadmap.md`](roadmap.md)).
- [ ] Real-provider run on a PC: no live call to a cloud provider has been made; set up the
      key and the `[provider_anthropic]` section on the PC and run one tagged lesson end to end.
- [ ] Anthropic adapter is never called in tests: `tests/worker/test_providers.py` uses an httpx
      mock transport only. Add an opt-in live check before relying on the wire format.
- [ ] Cost cap and warn tuning: `[cost]` `cap_micro_usd` and `warn_micro_usd` are example
      values (see `config/kata.example.toml`); the price table is pinned and unverified against
      live billing.
- [x] Reproducible Postgres test setup: `scripts/dev/pg.sh`, see [`development.md`](development.md).
- [ ] The extension manifest allows only `http://127.0.0.1:8080/*`, so a core reached over a VPN
      or another port needs a manifest change (request the host permission at sign-in).
- [x] `tools/gates.json` uses a pipeline wrapper (`cs-qrun`) that a clean clone does not have.
      Closed: `scripts/dev/check-all.sh` is the clean-clone gate with plain commands;
      `gates.json` now has plain commands too; `pipeline.json` runs `check-all` through `cs-qrun` (see
      [`development.md`](development.md)).
- [ ] Several API tests were pinned to a fixed date and failed once the real clock passed the
      token lifetime; fixed, but check new tests for fixed dates.
- [ ] Cost cap check-then-record is not atomic: `CappedProvider.complete` in
      `worker/kata_worker/providers/cost.py` reads `usage_today()`, calls the provider, then
      records. Two concurrent calls can both pass the check before either records, so the
      cap can overshoot by more than one call. The store write itself (`add_usage` in
      `core/kata_core/storage/usage.py`) is an upsert.
- [ ] `POST /usage` trusts client-reported `micro_usd`: `core/kata_core/api/routes/usage.py`
      adds the value with no server-side price check, so a client can under-report spend.
      Decide whether the server prices the call or the cap stays advisory (see
      [`decisions.md`](decisions.md)).
- [ ] Real editor test: run the VS Code extension in `editor/` against a running core on the
      owner PC (save event, quiet-mark diagnostic, hook installer command). Mocks only so far.
- [ ] Real MCP client test: connect an MCP client to `POST /mcp` with an `mcp`-scope token
      on the owner PC (`initialize`, `tools/list`, `tools/call`). Only the wire tests exist.
- [ ] Real terminal test: run `kata term` in a real terminal on the owner PC (PTY capture,
      mask list, spool flush). Not proven in a live session, see [`decisions.md`](decisions.md).
- [ ] Event retention and journal text: `design/architecture.md` promises 90-day removal of
      stored terminal history; no runner deletes events yet, and the journal text does not say so.
- [ ] Trainer: real trainer binary test. Run the trainer binary against a running core on the
      owner PC; the current tests use stubs only.
- [ ] Trainer: real model test. Run one lesson through a real local or cloud model on the owner
      PC; no test calls a live model yet.
- [ ] Trainer: real-browser checks. Drive the trainer screens in a real browser against a
      running core (sign-in, lesson flow, "I know this"); stubs only so far.
- [ ] Trainer: origin and handoff. Check the trainer origin and the handoff back to the
      extension and core end to end; not covered by any test yet.
- [ ] Trainer: read-only plan/course view (D16). Show the stored plan and course read-only; not
      built yet (decision D16).
