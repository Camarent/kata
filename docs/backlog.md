# Backlog

Project items after Milestone 0.

## Open items

- M5 leftovers blocking deployment: none. The open items below are not on the VM deploy path
  (the core runs on the VM and is reached over the private network); the manifest host permission
  item only matters when the extension talks to a private network name.

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
      The bridge content script is registered for `<core scheme>://*/c/*` only
      (`extension/src/bridgeRegister.ts`); the exact configured origin is checked at runtime in
      `runBridge`; the scan content script stays host-wide.
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
- [x] The extension manifest allows only `http://127.0.0.1:8080/*`, so a core reached over a VPN
      or another port needs a manifest change (request the host permission at sign-in).
      Closed in M15: the build has no fixed host; the origin is requested at sign-in
      (see [`decisions.md`](decisions.md), "Extension has no build-time server config (M15)").
- [ ] Real-browser run of the extension's first run: the origin permission prompt, the
      `kata-bridge` registration and the course-page bridge are checked only with fake browser
      APIs (vitest). Run them in Firefox and Chrome against a real core.
- [x] `tools/gates.json` used a wrapper that a clean clone does not have.
      Closed: `scripts/dev/check-all.sh` is the clean-clone gate with plain commands;
      `gates.json` now has plain commands too (see [`development.md`](development.md)).
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
- [ ] Trainer: real dojo CLI test. Run the dojo CLI against a running core on the
      owner PC; the default tests use the fake dojo (`tests/fakes/fake_dojo.py`) only. The
      opt-in smoke runs the real dojo CLI when `KATA_TEST_DOJO` is set.
- [ ] Trainer: real model test. Run one lesson through a real local or cloud model on the owner
      PC; no test calls a live model yet.
- [ ] Trainer: real-browser checks. Drive the trainer screens in a real browser against a
      running core (sign-in, lesson flow, "I know this"); stubs only so far.
- [ ] Trainer: origin and handoff. Check the trainer origin and the handoff back to the
      extension and core end to end; not covered by any test yet.
- [ ] Trainer: read-only plan/course view (D16). Show the stored plan and course read-only; not
      built yet (decision D16).
- [ ] Trainer: course rename route (M16). No route renames a course; a title is set at create.
      A rename needs the same per-user unique check as create (decision "Course limit and unique names (M16)").
- [ ] Trainer: real-browser check of the course panel (M16): create, delete with confirm, "n of
      limit" and the error texts. Vitest checks them with fake browser APIs only.

## Local models (M17)

- [ ] Capability audit on the PC: the lead runs `scripts/smoke/local_audit.py` with
      `KATA_SMOKE_LOCAL=1` against the local model and records one row per model and class in
      [`research/benchmarks/LOCAL_AUDIT.md`](research/benchmarks/LOCAL_AUDIT.md). Not run yet.
- [ ] Set `[local_capability]` from the audit verdicts in `config/kata.example.toml` and
      `deploy/kata.host.toml`: a class gets `cloud-only` where no local model is good enough. M26 added `[models]`, `[provider_openai]` and `vision` keys to both files; this item is unchanged by them.
      Until then every class is `kata-l` (see [`decisions.md`](decisions.md), "Routing defaults
      are local first, cloud by token (M17)").
- [ ] M11 note, thinking on/off numbers for the local models (`kata-l` is not a thinking model,
      `kata-m` is). Still open: the audit template does not answer it yet; close it once
      `LOCAL_AUDIT.md` gives the on/off numbers.
- [ ] Real cloud run for a cloud-only class: with the API key set, run one job of a `cloud-only`
      class end to end (the 409 `needs_cloud` path is tested only with the token unset).

## Exam pages (experimental)

Open question for the extension UI design (see [`design/extension-ui.md`](design/extension-ui.md)).
A page marked as an exam must not give hints. Safe default until decided: no marks and no
highlights on exam pages, from page open until the person has finished answering.

- [ ] Exam page detection: how a page is marked as an exam (site hint, user flag, or a
      per-site rule). Not decided.
- [ ] Result detection (pass or fail): can come later and may set topics to Known. Results are
      only known after the answer is submitted, so this needs experiments on real exam pages
      before any design. Until then the default above holds.

## Extension distribution

- [ ] Store listing and self-updating extension: publish the extension to the Firefox and Chrome
      stores and let it update itself. Needs store accounts; do it later, when the plugin works
      properly in a real browser (see the real-browser items above).

## Deployment (M6) follow-ups

- [ ] Real VM test: build the VM as in `docs/deployment.md` (Ubuntu Server LTS), run
      `deploy/provision-vm.sh` and the stack on it, and pass the deep health check. Owner steps are
      kept owner-local, outside the repo. Not proven until run on the real VM.
- [ ] Real private network test: join the VM and the phone to the network, reach the node name over
      TLS from a phone (secure context for the phone page), and check that nothing listens on a
      public interface.
- [ ] Backup to a second location: the nightly encrypted dump stays on the VM only. Copy it off
      the host (a second machine or bucket) with its own retention; see `docs/deployment.md`.
- [ ] TLS renewal: the node certificate comes from the network client on the host and needs a
      refresh timer or a manual step; confirm the renewal path on the real VM.
- [ ] Monitoring: alert when `GET /v1/health/deep` fails or the backup timer does not run; no
      monitoring exists yet.
- [ ] Run shellcheck and hadolint in CI: the gate image does not have them yet, so the Dockerfile
      and the shell scripts are checked by hand and by the rules tests only.
