# Decisions

## Initial review is by imported list file

The first review of a lesson set uses a list file that the user imports. The tool does not
fetch lesson lists from a site, so no page is crawled and no third-party service is needed.

## Guided screen is out of Milestone 0

A guided screen (step-by-step walk through a lesson) is not built in Milestone 0. Milestone 0
covers the core, config, worker and the card view. A guided screen adds UI work that does not
test the foundation, so it waits for a later milestone.

## Stack

- Core: Python with FastAPI; HTTP plus server-sent events; an MCP server so assistants can
  read the knowledge model. A hot path may move to C++ later if measurements justify it.
- Clients: TypeScript. WebExtension Manifest V3 (Firefox and Chrome), an editor extension, a
  web app for phones.
- Not Go for the core: the document, ML and learning ecosystem is in Python. Go may be used
  later for a narrow service.
- Storage: Postgres with pgvector behind a repository interface; every personal-data table
  carries a user id.
- Embeddings: a small CPU model with hybrid keyword retrieval; re-evaluate multilingual models
  on real data.
- License MIT. The repository is named `kata`; the PyPI name `kata` is taken, so the package
  name would be e.g. `kata-companion`. The repository stays private until it contains
  nothing personal.

## Providers and routing

- Adapters: (a) any OpenAI-compatible endpoint (local runtimes and hosted providers that offer
  that API); (b) a first-party API key; (c) optionally a vendor CLI as a subprocess, only for
  the large task class because start-up takes seconds.
- Cloud is off by default. A cloud call needs both the provider's `allow_cloud` and the global
  `[providers] cloud_enabled` set to true. Task classes are tag, explain, summary and batch.
  The API key is read from the env var named by `api_key_env`, never from the config file.
- A cost cap is built into the core and spend is tracked per call, per user.
- Chat subscriptions and APIs are billed separately; subscription tokens must not be used in
  application code. The application uses API keys through its adapters.
- The cloud provider is chosen with tests on the real tasks and the provider research
  ([`research/benchmarks`](research/benchmarks)); the adapters keep this a
  configuration change.

## Secret scanner

Two layers behind a scanner interface. Client masking in the terminal session tool uses a
small dependency-free pattern list. The core scans
every outgoing text before any cloud call with `core/kata_core/egress/scanner.py`, no subprocess (for the hook, superseded by the section at line 270). TruffleHog is rejected (AGPL licence does not fit
an MIT repository).

## Local model selection

Choose models per task, not globally:

- Resident small model for page scan and topic tagging, judged on tag accuracy and latency.
- The new/known label is computed in code. Models are judged only on topic and concept
  extraction.
- A larger model loaded on demand for explanation and summary, unloaded when idle.
- Batch work (whole decks, project-wide analysis) goes to a larger model or the cloud; time is
  not a target.
- Concurrency: one foreground request has priority and background scans yield; at most two
  parallel slots.
- Retrieval for lesson checks passes the top entries, not the whole base.

Benchmarks and method: [`research/benchmarks`](research/benchmarks).

## Resolved design decisions

- **Cost cap behaviour.** Cap and warning threshold per user and per period, checked before
  each cloud call (an estimate is reserved, corrected afterwards). At the cap the user falls
  back to model-free hints and is told; the administrator can raise the cap.
- **Taxonomy.** The shared tree is read-only for users and curated by the administrator; a
  rename migrates users' states. Each user's private overlay never changes the shared tree.
- **Thresholds.** Intervention thresholds are tuned per user from that user's own journal.
  Global defaults change only by the administrator, from content-free counts.
- **Pre-commit secret check.** Runs the core scanner locally, so it does not depend on the core (superseded for the hook by the section at line 270: the scanner is `core/kata_core/egress/scanner.py`, no subprocess).
- **Automatic scan on page open.** Only on sites the user added, each a URL mask (a pattern
  with wildcards, so one entry can cover a whole platform); elsewhere a scan starts on a
  click. Background prefetch for a user without a worker is a setting, off by default.
- **Scan target.** 30 seconds counts the card (all blocks tagged, counts and top gaps); the
  summary appears when ready, with no deadline.
- **Marks.** Topic marks (`marks`) stay as they are. Concept marks (`concept_marks`) shipped in milestone 2: each user marks a concept `known`, `learning` or `new`, with optional evidence. Concept marks are private to their user.
- **Chunk sharing.** Chunks are shared by content hash; the user-to-chunk link stays private so
  the store does not reveal who studies what.
- **Language.** The vector table is built for a multilingual embedding model from the start.
- **Code to the cloud.** For a user without a worker, code and diffs go to a cloud model only
  after an opt-in per repository; otherwise code checks use model-free rules.
- **Secrets.** A chunk or file with a detected secret stays local (marks, search) and is shown
  as "not sent to cloud", not rejected.
- **Worker link.** Pull-based over plain outbound HTTP; the core never needs the worker's
  address.
- **Terminal tracking.** Opt-in per session through an explicit command, not an always-on shell
  hook. A spike must confirm that capture inside an SSH session works.

## Python dependencies stay pinned with ==, no lock file

Runtime and dev dependencies are pinned with `==` in `pyproject.toml`. `scripts/dev/check-all.sh`
and `.github/workflows/ci.yml` both install from that file, so the pins are the one source. No
`uv lock` file and no new tool are added: a lock file would be a second list to keep in step
with the pins. Revisit only if a transitive dependency must be pinned for reproducible installs.

## Embeddings are real[] with cosine in Python, no pgvector yet

Embeddings are stored in a plain `real[]` column (`core/migrations/0003_retrieval.sql:10`).
The vector side loads the candidate rows and ranks them by cosine in Python
(`core/kata_core/retrieval/retriever.py:72`). pgvector is not added yet: a few entries scan
fast enough. Revisit when an entry count makes the scan slow, and then move the ranking into
Postgres behind the repository interface.

## Full-text search uses the simple FTS configuration

Keyword search uses the `simple` text search configuration, both in the stored `tsv` column
(`core/migrations/0003_retrieval.sql:9`) and in queries (`core/kata_core/retrieval/store.py:44`).
`simple` does no stemming and no stop-word removal, so it does not depend on one language.

## Rank fusion is reciprocal rank fusion with k = 60

Keyword and vector rankings are merged with reciprocal rank fusion: an item at rank r scores
1 / (k + r) in each list (`core/kata_core/retrieval/fusion.py:6`). The shipped `[retrieval] rrf_k`
value is 60 (`config/kata.example.toml:39`). RRF needs no score scale matching between the
keyword and the cosine side, so the two rankings combine without tuning.

## Tests use FakeEmbedder only; the CPU model is never run in CI

`[retrieval] embedder = "fake"` is the shipped default (`config/kata.example.toml:37`). The
tests use `FakeEmbedder`, a deterministic hashing embedder with no model download. The real
model is `embedder = "model"`, a small CPU model loaded through sentence_transformers
(`core/kata_core/retrieval/embedder.py:79`). It is set by configuration only and is never run
in CI, so CI stays fast and needs no model weights.

## Retrieval entries are private per owner or shared

A `retrieval_entries` row with `owner_user_id` set is private to that user. A row with
`owner_user_id` NULL is shared and visible to every user (`core/migrations/0003_retrieval.sql:6`,
`core/kata_core/retrieval/store.py:45`). Both the keyword and the vector side filter on the
caller's id, so a private entry never reaches another user.

## Lesson check: retrieval never yields 'new'

Only a mark can say a concept is `new`. Absence of retrieval entries is not proof that the user has not met the concept, so a concept with no kept evidence gets `abstain`, not `new` (`core/kata_core/lesson_check/checker.py:6`).

## Lesson check: abstain below min_score on the RRF scale

A retrieval hit counts as evidence only when its fused RRF score is at least `[lesson_check] min_score` (`core/kata_core/lesson_check/checker.py:79`). The score is a sum of `1 / (rrf_k + rank)` over the keyword and vector lists. With `rrf_k` 60, one list gives at most 1/61 (about 0.0164), so the example `min_score` 0.02 passes a hit only when both lists rank it. Below the threshold the concept abstains.

## Lesson check: thresholds are placeholders for the benchmark phase

`min_score` 0.02, `known_hits` 3 and `search_limit` 5 in `config/kata.example.toml:43-46` are starting values, not measured ones. They are set for the benchmark phase to check on labelled data; change them in config, not in code.

## Lesson check stays synchronous in the core

Lesson check runs synchronously in the core via `POST /lesson-check`. No worker job runs it. Reason: there is no consumer and no result channel (`POST /jobs/{id}/result` takes only category and topic and creates a shared topic), so a job could not return a check result. Revisit when embedding gets heavy.

## Model config key is `model_name`

The `[model]` section names its model with `model_name` (`config/kata.example.toml:30`). That is the canonical key: the example config, the config tests (`tests/foundation/test_config.py:61`, `:65`, `:86`) and the worker model code all use it. A second spelling would be read by nothing, so config keys must use `model_name` only. `[retrieval]` also has a `model_name` key for the embedder (`config/kata.example.toml:38`); it is a separate section and the same name.

## Core entrypoint runs uvicorn on `[core]` host and port

`python -m kata_core` (`core/kata_core/__main__.py:19-31`) loads the config from `KATA_CONFIG` and calls `uvicorn.run` with `[core] host` and `[core] port`. Signal handling (SIGINT, SIGTERM) is left to uvicorn, so the entrypoint adds no signal code of its own. Run the core with `python -m kata_core`, not with a bare uvicorn command, so the host and port come from config.

## Extension has one manifest base and a per-browser composer

Decided 2026-11-21. The MV3 manifest is `extension/manifest.base.json`: the fields both browsers share. `extension/build/manifest.mjs` (`composeManifest`) adds the browser-specific keys. Reason: two hand-kept manifests drift apart, so a permission or host change would have to be made twice. The composer is a pure function, so the difference between browsers is tested in one place (`extension/tests/manifest.test.ts`). There is no `extension/manifest.json` in the repo any more; the build writes one per browser.

## Browser adapter picks sidePanel or sidebarAction

Decided 2026-11-21. Chrome opens the panel with `chrome.sidePanel`; Firefox opens it with `sidebarAction`. `extension/src/browser.ts` (`openPanel`) hides the difference behind one call and throws when neither API exists. Reason: the background script stays one code path for both browsers, and Firefox first (see the `extension` module doc) needs no separate background file.

## Content script matches http and https only

Decided 2026-11-21. The content script used to match `<all_urls>`. It now matches `http://*/*` and `https://*/*`. Reason: the scanner only reads lesson pages, and `<all_urls>` also injects into `file:`, `ftp:` and other schemes the extension never needs. The narrowing does not finish the job: the script still runs on every http and https page, so the backlog item about the `<all_urls>` permission stays open.

## Firefox gecko id is kata@kata.local, minimum version 128.0

Decided 2026-11-21. `browser_specific_settings.gecko.id` is `kata@kata.local` and `strict_min_version` is `128.0`, both set in `extension/build/manifest.mjs`. The id is a fixed value chosen for this project; 128.0 is the chosen minimum, not a claim about when `sidebar_action` appeared. Change the id and the minimum only together with the Firefox add-on listing, because the id is what Firefox uses to tell installed versions apart.

## Extension build writes each browser to dist/<browser>/

Decided 2026-11-21. `npm run build` in `extension/` runs `build/build.mjs`, which writes `extension/dist/chrome/` and `extension/dist/firefox/`. Each folder holds its own `manifest.json`, the bundled scripts and a copy of `sidepanel.html`, so each folder loads on its own. Reason: one shared `dist/` cannot hold two manifests that differ. `node build/build.mjs firefox` builds one browser only.

## Browser e2e drives the browsers through selenium and geckodriver

Decided 2026-11-21. The real-browser tests in `tests/browser/` use selenium (`requirements-browser.txt`, pinned `selenium==4.53.0`) with a Firefox driver: geckodriver from `scripts/dev/install-browsers.sh`, and Chrome through chromedriver on `PATH`. Reason: the tests run the stock Firefox and geckodriver binaries that the install script pins with sha256, one install path for both the test driver and the browser. Playwright was not chosen: it brings its own browser downloads and a second install path next to the pinned one. The repo does not record a longer comparison; this entry is the decision, not a benchmark.

## Browser tools install per user with pinned sha256

Decided 2026-11-21. `scripts/dev/install-browsers.sh` downloads Firefox 140.0esr and geckodriver 0.36.0 (linux x86_64) into `$KATA_BROWSERS_DIR`, default `$HOME/.cache/kata-browsers`. It needs no sudo, changes nothing system-wide, and verifies each archive against a pinned sha256 before it unpacks. An empty pin refuses the install (fail closed). Reason: a user-level, pinned install is reproducible and leaves the system browser alone. Chromedriver is not pinned: Chrome is looked up on `PATH` instead. `install-browsers.sh --status` checks the install with no network; `--print-dir` prints the directory.

## Browser marker is excluded from every gate except --browser

Decided 2026-11-21. Tests marked `browser` (`pyproject.toml`, marker `browser`) run only through `scripts/dev/check-all.sh --browser`. Every other mode excludes them with `-m 'not browser'`: `--py`, `--unit`, `--merge`, the smoke step and the full run. Reason: CI and the pipeline gate have no browser and no Firefox, so a browser test there would fail or skip for a reason that is not a code fault. The marker keeps the browser tier out of the default gate without deleting its tests.

## Browser tests skip with a message when a browser is missing

Decided 2026-11-21. With no Firefox or geckodriver from the install, `check-all.sh --browser` prints `check-all: browser tests skipped: ...` and exits 0. Each browser case also skips with a reason from `tests/browser/conftest.py` (`pytest.skip`) when its binary is missing. A missing built extension is a failure, not a skip: the case says to run `npm run build`. Reason: a developer without browsers keeps a green run, and a broken build still shows red.

## Chrome browser case is unverified

Decided 2026-11-21. The Chrome param of `tests/browser/test_panel_flow.py` has never run against a real Chrome: the only run so far skipped, because no chromedriver was on `PATH`. The Chrome extension id is derived in the test from a sha256 of the dist path, which is unverified. Branded Chrome 137 and later may ignore `--load-extension`, so the Chrome flow may not load the extension at all. The Firefox case is the one the stage relies on. Reason for recording it here: a green Chrome skip must not be read as a passing Chrome flow.

Update 2026-11-21: with `extension/dist/` built and `/usr/bin/google-chrome` and chromedriver on `PATH`, the Chrome cases of `test_panel_flow.py`, `test_panel_a11y.py` and `test_panel_contrast.py` ran and passed (7 passed, no skip, `pytest tests/browser -m browser`). The points above still hold for other Chrome builds and for a machine without chromedriver.

## Keyboard focus order and focus indicator are checked on the sign-in view

Decided 2026-11-21. `tests/browser/test_panel_a11y.py` opens the side panel sign-in view and presses Tab from the page start. It asserts the order `input[name=code]`, `input[name=deviceLabel]`, `button[type=submit]`, that each focused control sits inside `form.signin`, and that each focused control shows a focus indicator (a non-zero outline or a box-shadow). Outcome: Firefox and Chrome both passed on 2026-11-21. Limit: the sign-in view only. The review screen is not covered. Reason: these are the checks a real browser can prove; a stub cannot show the focus ring the browser draws.

## Dark-theme contrast of the sign-in view is at least 4.5 to 1 in Firefox and Chrome

Decided 2026-11-21. `tests/browser/test_panel_contrast.py` opens the sign-in view with dark mode forced. For each text element (labels, input text, button text, error text) it takes the first non-transparent background up the ancestor chain, or the canvas colour, and computes the WCAG 2.x contrast ratio. It asserts every ratio is at least 4.5 (`MIN_RATIO`). How dark is forced: Firefox sets `layout.css.prefers-color-scheme.content-override` to 0 at launch (`tests/browser/conftest.py`); Chrome uses CDP `Emulation.setEmulatedMedia` from `force_dark_scheme` (`tests/browser/panel_page.py`). The case skips with a reason when `matchMedia('(prefers-color-scheme: dark)')` is false, so a browser that ignores the override does not pass silently. Outcome: Firefox and Chrome both passed on 2026-11-21, not skipped. Limit: the sign-in view only; the review screen and light theme are not covered. Reason: WCAG AA is the bar the backlog names; the threshold is a fixed constant, not tuned to the result.

## Cost cap is per user per day in integer micro-USD

Decided 2026-11-21. Spend is kept in table `usage_daily`, keyed by (user_id, day in UTC). The cap is per user per day. Money is stored as integer micro-USD, so no float rounding enters the sum. The price table is pinned in `worker/kata_worker/providers/cost.py`, not in config, so no config edit can understate a price. An unknown model price fails closed: the call is refused. Cost is recorded from real usage (see the 2026-11-22 entry); the text-length estimate is the pre-call guard only. The cap is checked before the call and the spend is recorded after it, so one call may overshoot the cap by its own cost. The warn threshold is a log line only. Local providers are free and are not checked against the cap. Reason: a config value cannot understate a price, and the cap stays simple to audit. Limit: the pre-call guard is an estimate, and the overshoot is bounded by one call.

## Routing uses one provider chain per task class, with no implicit local fallback

Decided 2026-11-21. `[routing]` in `config/kata.example.toml` lists one comma-ordered chain per task class; `worker/kata_worker/providers/router.py` `Router.route` tries them in order and the first reply wins. A provider the chain does not list is never called, so local is a fallback only when the chain names it (`tests/worker/test_router.py:152`). Each cloud provider is wrapped as `guarded(capped(inner))`: the secret guard runs before the cost cap, so a blocked text never reads the ledger or reaches the API. Task classes stay `tag`, `explain`, `summary` and `batch`. `lesson_check` is not a task class: it is a synchronous core call since phase 01, and no worker job runs it. Reason: the chain makes the order of providers visible in config, and the wrap order keeps secret text out of the spend path. Limit: a chain of only cloud providers fails the job when the cap or the guard refuses, with no local answer.

## Secret scanner has no bypass

Decided 2026-11-21. `worker/kata_worker/providers/guard.py` wraps every cloud provider as `GuardedProvider`. It scans the system and the user text of each cloud completion, and a finding blocks the call before the inner provider runs. No flag, config key or env var skips the scan; `tests/worker/test_scanner_guard.py` checks that `guarded` has no skip parameter (`test_guarded_has_no_skip_parameter`) and walks every provider module with `pkgutil.walk_packages` (`test_cloud_provider_classes_are_not_exposed_outside_guard`), so a cloud class reachable outside the guard fails the test. Local providers pass through unscanned by design. Reason: a bypass switch would let secret text leave the machine with no audit event. Limit: the walk covers modules under `worker/kata_worker/providers`; a cloud client built in another package is not seen by that test.

## Secret scanner lives in core egress

Decided 2026-11-21. The scanner rule set moves to `core/kata_core/egress/scanner.py`, so the worker, the later MCP server and the pre-commit check share one rule set instead of copies. Reason: one place to fix a pattern, and one test suite for it. Landed in task-1 of this stage: no copy remains under `worker/`, and `worker/kata_worker/providers/guard.py` imports `scan` from core.

## M3 leftovers for M4

Checked 2026-11-21 against `docs/backlog.md` open items. Items that block M4:

- Anthropic wire format is untested live: `tests/worker/test_providers.py` uses an httpx mock transport only. M4 needs an opt-in live check before relying on the format.
- Config keys: `[cost]` `cap_micro_usd` and `warn_micro_usd` in `config/kata.example.toml` are example values, and the price table is unverified. Set real values before M4 uses the cap.

Items that do not block M4 and stay in the backlog: the real-provider run on a PC, the non-atomic cost check-then-record, and `POST /usage` trusting client-reported `micro_usd`. Note: the last two are cost-path risks, so review them before any multi-user use.

## MCP server speaks raw JSON-RPC, no SDK

Decided 2026-11-21. `core/kata_core/mcp/rpc.py` implements the JSON-RPC 2.0 methods the kata tools need (`initialize`, `tools/list`, `tools/call`) by hand, with the standard library `json`. No MCP SDK is a dependency. Reason: the surface is two tools and three methods, so the SDK would add a pinned package and its licence for little gain. Limit: a new MCP method or protocol revision means changing `rpc.py` by hand, and batches are refused.

## Devices have a token scope: api or mcp

Decided 2026-11-21. `devices.scope` is `api` or `mcp`, default `api`. An `mcp` token passes only `POST /mcp` (`core/kata_core/api/routes/mcp.py`), and an `api` token gets 401 there. An `mcp` token gets 401 on every `api` route, because `api.deps.current_user` checks scope `api`. Reason: an assistant token that reaches the MCP surface must not also reach the write routes, and the reverse. `mint-mcp-token` (see `docs/api.md`) issues the `mcp` scope.

## MCP gate: quoted data, size limit, secret scan, one rule set

Decided 2026-11-21. `core/kata_core/mcp/gate.py` checks every tool result before it leaves the core, in this order:

1. Size: more than `MAX_RESULT_BYTES` (4096) UTF-8 bytes is blocked with reason `size`.
2. Secret scan: the single scanner in `core/kata_core/egress/scanner.py` runs; a finding blocks with reason `secret:<kind>`.
3. Quoting: an allowed result becomes `DATA_PREFIX` (a fixed sentence that says the block is data, not instructions), then every line prefixed with `> `, so injected text cannot start a new instruction line.

Concept names passed to `kata_concept_state` must match `[\w .\-]{1,80}` (`safe_concept_name`). A blocked result returns empty text and a reason that names the rule only, never the matched text.

Unknown provider: the core does not know which assistant reads a result. The gate therefore applies one fixed rule set to every result. It has no provider or content-class input, so no flag can skip the scan. Reason: critique F33, see `docs/design/critique.md`.

Journal: a blocked result writes one `egress_block` entry with `{"tool", "reason"}` (`core/kata_core/mcp/tools.py:81`). The entry never holds the blocked text.

## Device package lives in core/kata_device

Decided 2026-11-21. The device-side code (`python -m kata_device`, git hooks, local queue, marker; the `kata` entry point is not built yet) is the package `core/kata_device/`, next to `kata_core` and imported with `core` on `PYTHONPATH`. Reason: the hooks and the core share the one secret scanner (`kata_core.egress.scanner`), so one tree and one test run cover both. The package imports `kata_core` only for the scanner; the queue and marker modules import nothing from core.

## Device subcommands load through a lazy registry

Decided 2026-11-21. `core/kata_device/cli.py` maps each command name to a `"module:function"` string in `REGISTRY`. A command module is imported only when its command runs, so a missing module fails that one command with a message. The entry `term` maps to `kata_term.cli:main`; phase 6 adds that package and no change to the dispatcher is needed for it. Reason: the pre-commit hook runs on every commit and must not import the terminal code, and a broken optional command must not break the hook.

## Pre-commit scans staged lines in process with the one scanner

Decided 2026-11-21. `core/kata_device/precommit.py` reads the staged added lines (`gitutil.staged_added_lines`) and scans each with `kata_core.egress.scanner.scan`, in the hook process. It has no time limit. This replaces the gitleaks binary from the earlier design (`docs/design/detailed-architecture.md:668`, "gitleaks locally with a 5 s limit"): the pre-commit hook does not use gitleaks (CI still runs gitleaks in the secrets job), and no external binary is needed. Reason: one rule set for the hook, the worker and the core, so a pattern fixed once is fixed everywhere, and no install step beyond Python. The 5 s limit is dropped because the scan is local and bounded by the staged diff size.

## Block message names the kind and location only

Decided 2026-11-21. A blocked commit prints one line per finding: `kata: blocked: <kind> at <file>:<line>`. The message never prints the matched text or the line. Reason: the terminal and the CI log must not copy the secret the hook found.

## Pre-commit results are queued locally, not uploaded

Decided 2026-11-21. Each pre-commit block and each post-commit bypass appends one JSON record to `<git_dir>/kata/queue.jsonl` (`core/kata_device/queue.py`, `enqueue`). The record holds the result and rule kinds with counts only, never paths or code. The upload is not built (the events API, `POST /v1/events`, has no `precommit` event type, so the queue has no sink yet); the finish phase lists it in `docs/backlog.md`. Reason: the hook must work offline and must not block a commit on the network.

## Marker holds the staged tree hash and is cleared after every commit

Decided 2026-11-21. A passing pre-commit writes the staged tree hash to `<git_dir>/kata/marker` (`core/kata_device/marker.py`). The post-commit hook compares that hash with the committed tree: a different hash, or no marker, queues a `bypassed` record. The marker is cleared after every post-commit, except a post-commit run while a rebase, merge, revert or cherry-pick is in progress (marker kept) or after an unexpected error before the clear (marker kept), so a stale marker never outlives a normal commit. Reason: a tree hash detects a skipped check (for example `--no-verify`) without storing any file content.

## Installer never overwrites a hook or core.hooksPath

Decided 2026-11-21. `python -m kata_device hooks install` (`core/kata_device/hooks.py`; the `kata` entry point is not built yet) writes `pre-commit` and `post-commit` only when neither file exists or the existing file carries its own marker line, and `core.hooksPath` is unset. Otherwise it prints the two command lines for the owner to add by hand and writes nothing. Reason: a hook the owner wrote, or a shared `core.hooksPath`, must not be replaced silently.

## kata term is opt-in and explicit

Decided 2026-11-21. Capture happens only while the owner runs `kata term`. There is no shell hook, no auto-start and no change to the shell rc files. Reason: the owner must know when typing is recorded, and leaving the session ends capture.

## kata term uses a PTY and captures lines, not a shell hook

Decided 2026-11-21. `core/kata_term/session.py` runs the shell in a PTY and reads the typed line buffer and the output stream. Reason: it works with any shell and needs no install into the user's shell config.

## kata term error signal is a kind only

Decided 2026-11-21. Output is scanned for known error patterns and only a kind is emitted (`terminal.error`). Output text is never stored or sent. Reason: output can hold secrets and code.

## kata term mask list is private and never logged

Decided 2026-11-21. Command text is masked before the spool write with built-in patterns plus a private list outside the repo (`KATA_TERM_MASKS`, default `~/.config/kata/term-masks`). Nothing logs the text, the patterns or a load error; a bad list is skipped. Reason: the list itself can reveal secrets, and the repo holds no personal data.

## kata term spool is JSONL with at-least-once flush

Decided 2026-11-21. Events go to a JSONL spool first and are flushed in batches after each command and at exit; sent ids are removed only after the server settles them. The server dedupes by `event_id`. Reason: the tool works offline, and a retry after a crash or failed post never double counts.

## kata term client uses stdlib urllib

Decided 2026-11-21. `core/kata_term/client.py` posts with `urllib`. Reason: the tool must run with no installed dependency.

## kata term SSH capture is not proven

Decided 2026-11-21. This phase does not prove capture over SSH. `docs/open-questions.md` item 7 stays open. Reason: no SSH test exists; claiming it would be unverified.

## Editor stop patterns suppress posting

Decided 2026-11-21. A document whose text matches a `kata.stopPatterns` entry posts nothing (`editor/src/poster.ts:31`). The match runs locally, before any network call; an invalid pattern is skipped (`editor/src/stopPatterns.ts:8-9`). Reason: the owner can keep a file out of the signal without the server ever seeing it.

## Editor payload carries language only

Decided 2026-11-21. The `editor.save` event carries `payload: { language }` (`editor/src/poster.ts:38`). Document text is read only for the stop check and is never sent. Reason: code can hold secrets and personal data, and the core needs only the signal.

## Editor dev dependencies are pinned

Decided 2026-11-21. `editor/package.json` pins `@types/node`, `@vitest/coverage-v8`, `typescript` and `vitest` to exact versions, and `editor/package-lock.json` is committed. Reason: a moving toolchain would change the build and tests without a code change.

## Editor build and test run in check-all --editor

Decided 2026-11-21. `scripts/dev/check-all.sh --editor` runs the editor build and `test:cov` only (`scripts/dev/check-all.sh:146-148`), and the full and merge modes also run it. Reason: the editor needs no Postgres or browser, so the owner can check it alone; CI runs the same steps (`.github/workflows/ci.yml:54-56`).

## D0 Route and phase cut

Decided 2026-11-21. M5 runs on the BIG route in 2 phases: 01-trainer (about 18 tasks) and 02-planning (about 18 tasks). Each phase is one PR. The cut sits at the trainer/planning seam: 02 reads the mastery score that 01 adds, so 02 plans against merged 01 code. Phase owned paths must not overlap: 01 owns `docs/decisions.md`, `docs/api.md`, `config/kata.example.toml` and all config keys of both phases (D15); 02 tasks may still edit `docs/api.md` for planning routes in their own stage. Reason: the pipeline cuts a phase only at a gate or the 30-task cap, and the 7 request phases are 1-8 tasks each.

## D1 M4 leftovers: none block M5

Decided 2026-11-21. No M4 leftover blocks M5. The cost-cap check-then-record race (`docs/backlog.md:46`) stays open in the backlog: the worker loop is single-threaded (`worker/kata_worker/loop.py:49`), and course and syllabus calls run one at a time per worker, so the overshoot stays bounded by the worker count. The `POST /usage` trust issue (`docs/backlog.md:51`) stays open: the cap stays advisory. Reason: both are bounded or already known, so neither blocks the trainer work.

## D2 Job kinds

Decided 2026-11-21. Migration `core/migrations/0008_job_kind.sql` adds `kind text NOT NULL DEFAULT 'tag'` and `output jsonb` to `jobs`, plus an index on `(kind, status)`; existing rows become `tag`. `core/kata_core/jobs/queue.py` gets `enqueue(..., kind='tag')` and `claim_next(..., kinds=('tag',))`. `GET /jobs/next` takes repeated `?kind=`; with no parameter it returns `tag` only, so old workers stay unchanged. Kinds: `tag` (worker), `course.generate` (worker), `syllabus.extract` (worker, phase 02), `course.build` (core). Worker output goes to `POST /jobs/{id}/output` with body `{"output": {...}}`, a JSON object capped by `[jobs] max_output_bytes`. The caller must hold the lease, the same check as the result route (`core/kata_core/api/routes/jobs.py:93`). Core runs the kind's output hook in the same transaction.

## D3 Handler registries (open/closed, no central list)

Decided 2026-11-21. Core `core/kata_core/jobs/runner.py` discovers `kata_core.<pkg>.job_kinds` modules with pkgutil (same pattern as `core/kata_core/api/routes/__init__.py:14`). Each module exposes `HANDLERS: dict[str, Handler]` for core-run kinds and `OUTPUT_HOOKS: dict[str, OutputHook]`. The runner never imports trainer or planning by name. `run_once(conn, registry, now)` claims one core-kind job. The core loop is `python -m kata_core.jobs` (`core/kata_core/jobs/__main__.py`), polling every `[jobs] runner_poll_seconds`; `python -m kata_core` (uvicorn) does not change. Worker handlers live in package `worker/kata_worker/handlers/`, one module per kind exposing `KIND` and `handle(job, router, client)`, discovered by pkgutil. The `tag` kind moves from `loop.py` (`run_once`) into `handlers/tag.py` with unchanged behaviour; the existing `tests/worker/test_loop.py` stays green first. The worker claims only kinds it has handlers for. Reason: new kinds are added by a new module, not by editing a central list.

## D4 Model text goes through the worker only

Decided 2026-11-21. Core has no model access. `course.generate` and `syllabus.extract` run in the worker through `Router.route(task_class, ...)` (`worker/kata_worker/providers/router.py`), so the secret guard, policy and cost cap apply unchanged. The task classes are `generate_course` and `extract_syllabus`, set in config `[routing]` and in provider `task_classes`. Tests use `tests/fakes/fake_provider.py` and `tests/fakes/fake_model.py`, never a real model or key.

## D5 Course flow and tables (migration 0009_trainer.sql)

Decided 2026-11-21. Table `course(id, user_id FK CASCADE, title, status CHECK queued|generating|building|ready|failed, concept_ids bigint[], error text, created_at, updated_at)`. Table `course_file(course_id FK CASCADE, path, content text, PK(course_id, path))` holds the generated source. Table `course_artifact(course_id FK CASCADE, path, media_type, content bytea, PK(course_id, path))` is capped by `[trainer] max_artifact_bytes`. Table `course_item_map(course_id FK CASCADE, item_id text, concept_id FK CASCADE, PK(course_id, item_id))` is append-only. Every query filters by `user_id` through course.user_id; another user's course returns 404. Flow: `POST /v1/courses {concept_ids?, title?}` selects gaps (D6), creates a `queued` course row and a `course.generate` job with payload `{course_id, concepts:[{id,label}]}`. The worker generates item drafts. The output hook validates them (only the text fields `prompt`, `answer`, `concept_id` within the selected set; length cap; character rules), writes `course_file` rows and queues `course.build`. The core runner uses a temp dir and `TrainerCli` (next_id, add, validate, lock, build); failing items are dropped, and the build runs when at least `[trainer] min_items` remain, otherwise the course becomes `failed` with a diagnostics summary. On success it stores artifacts and the item map, sets `ready`, and journals `course.ready` or `course.failed` (`core/kata_core/journal/store.py:28`). Out of M5 (backlog): trainer origin, `POST /v1/courses/{id}/open` handoff, cookie scope, serving pages, `kata progress import`, diagnostics re-rounds to the model.

## D6 Course planning rules (pure, unit tested)

Decided 2026-11-21. A gap is a visible concept whose mastery score (D9) is below `[knowledge] known_threshold`. Explicit `concept_ids` are filtered to visible gaps; unknown or foreign ids are rejected with 422. Order: state `learning` first, then `new`, then by score ascending, ties by concept id. Caps: `[trainer] max_concepts` (10) and `[trainer] items_per_concept` (3). An empty gap list gives 422.

## D7 Trainer CLI wrapper

Decided 2026-11-21. `core/kata_core/trainer/cli.py` defines the `TrainerCli` Protocol: `next_id(workdir) -> str`, `add(workdir, item) -> str`, `validate(workdir) -> list[Diagnostic]`, `lock(workdir)`, `build(workdir, outdir) -> list[str]`. `SubprocessTrainerCli(argv_prefix: list[str], timeout)` takes an argv list, never a shell; the prefix comes from config `[trainer] command` (a TOML array). Trust boundary: the executable is supplied by config; the sec-auditor must note this. A non-zero exit or bad JSON raises `TrainerError`. Machine output contract, also used by the fake: each call prints one JSON object on stdout. next-id `{"id": "i0001"}`; add `{"id": "..."}`; validate `{"ok": bool, "diagnostics": [{"item": id, "message": str}]}`; lock `{"ok": true}`; build `{"files": [paths]}`. The fake is `tests/fakes/fake_trainer_cli.py`, run as `[sys.executable, <path>]` so no exec bit is needed; item text containing `FAKE_INVALID` gets a diagnostic. The real binary format is unverified and goes to the backlog.

## D8 Progress documents (migration 0010_mastery.sql, with D9 tables)

Decided 2026-11-21. Table `trainer_progress(course_id PK FK CASCADE, user_id, revision int NOT NULL, doc jsonb, updated_at)`. Routes sit on the API origin with Bearer auth (trainer origin deferred, D5). `GET /v1/courses/{id}/progress` returns 200 `{"revision": n, "doc": obj|null}` with `ETag: "n"` (n=0 and doc null when none). `PUT /v1/courses/{id}/progress` takes the doc as body and header `If-Match: "n"`: missing header gives 428, malformed body gives 400, mismatch gives 412 with body `{"revision": cur, "doc": cur_doc}` and ETag, success gives 200 `{"revision": n+1, "evidence_written": k, "skipped_items": s}` with ETag. Compare-and-set: `UPDATE ... WHERE course_id AND user_id AND revision = n`; the first save is `INSERT ... ON CONFLICT DO NOTHING` with n=0; zero rows gives 412. One transaction holds the D9 writes too. Doc shape: `{"items": {"<item_id>": {"ok": int>=0, "bad": int>=0, "stage": int}}, "resetAt"?: str}`; other keys are kept verbatim. Size cap `[trainer] max_progress_bytes` gives 413. A course not in `ready` gives 409.

## D9 Knowledge update (decisions in code only)

Decided 2026-11-21. Table `trainer_evidence(id, user_id, course_id FK SET NULL, item_id, concept_id, ok, bad, delta real, created_at, UNIQUE(user_id, course_id, item_id, ok, bad))` is append-only; ON CONFLICT DO NOTHING means a repeated or merged save adds nothing (critique F24). Per accepted save, each item whose `ok` or `bad` rose versus the previous revision is mapped through `course_item_map`; unmapped items are skipped and counted. Falling counters (reset) write nothing. Table `concept_mastery(user_id, concept_id, score real CHECK 0..1, updated_at, PK)`. Base score when absent comes from concept_marks state (known 0.9, learning 0.5, new or none 0.1, all from config). Step: `delta = clamp(step * (d_ok - d_bad), -max_step, +max_step)`, score clamped to [0,1]; config `[knowledge] trainer_step=0.1, trainer_max_step=0.3`; items applied in item-id order. State: score >= `known_threshold` (0.8) is known; >= `learning_threshold` (0.4) is learning; otherwise new. `concept_marks` gets `source text NOT NULL DEFAULT 'user' CHECK (user|trainer)` in 0010. When the mark is absent or its source is trainer, write the new state (source trainer) when it changes. When the source is user and the trainer disagrees, keep the user mark until `[knowledge] assertion_hold` (3) contrary trainer evidence rows exist since the mark's updated_at, then overwrite it. Every state change by the trainer writes journal `knowledge.trainer_update {concept_id, from, to, score}`: nothing changes silently. Deleting a course keeps evidence and mastery (course_id becomes NULL). The full 7.5 model (weights, decay, other evidence types, recompute) stays in the backlog.

## D10 Syllabus import and triage (phase 02, migration 0011_syllabus.sql)

Decided 2026-11-21. Parser `core/kata_core/importer/syllabus.py` sits next to skill_list.py, the existing content ingest. It reads markdown headings `#` and `##`; otherwise numbered lines (`1.`, `Module 1:`); otherwise one module. Model help runs only when `[syllabus] model_extract = true` and no structure is found: job `syllabus.extract` (worker, D4). The output hook accepts a module only if its text is a substring of the source (whitespace-normalized) and its title is at most 120 chars; otherwise it falls back to one module. Tables: `syllabus(id, user_id, title, status, created_at)`, `syllabus_module(id, syllabus_id, position, title, body, words)`, `syllabus_module_concept(module_id, concept_id)`. Matching: visible concept labels (word boundary, case-insensitive) in title and body. Triage per module from mastery scores (D9): no concept gives new; all at or above known gives known; any at or above learning gives partly_known; otherwise new. Action: known gives skip; partly_known gives skim if the known share is at least `[planning] skim_share` (0.5), else practice; new gives learn. Effort minutes = action minutes x units, where units = max(1, ceil(words / `words_per_unit` 400)); minutes are skip 0, skim 15, practice 45, learn 90 (`[planning]`).

## D11 Tracks, budget, allocation (migration 0012_tracks.sql)

Decided 2026-11-21. Table `track(id, user_id, name, deadline date, priority int, status active|paused|dropped)`; table `track_item(track_id, position, module_id NULL, label, action, minutes)`; table `planning_budget(user_id PK, minutes_per_week, updated_at)`. Capacity(d) = floor(minutes_per_week * days(now..d) / 7). Allocation is pure, in `core/kata_core/planning/allocate.py`: active tracks are sorted by (deadline, -priority, id); items go in position order; an item is allocated while the cumulative total stays within capacity(track deadline); the first item that does not fit and every later item of that track are deferred. Invariants (property test, `random.Random(seed)` with seeds 0..199): for every deadline d, the allocated minutes of tracks with deadline <= d are at most capacity(d); the total is at most capacity(max deadline); non-active tracks get 0; items are never split; the same input gives the same output. Clock: `now: Callable[[], datetime]` is injected (same pattern as `core/kata_device/precommit.py:32`); the API gets it from one dependency that tests override.

## D12 Decision points

Decided 2026-11-21. Table `decision_point(id, user_id, track_id, after_position, due_on date, status open|decided, choice continue|switch|drop, target_track_id, decided_at)`. An open point means items after `after_position` are not allocated. continue makes them allocatable; switch pauses the track and activates the target track; drop drops the track. Each decision writes a row and journal `plan.decision`; the next allocation differs (tested).

## D13 API (phase 02 for planning; 01 for courses/progress)

Decided 2026-11-21. Phase 01: `POST /v1/courses` (202 with job id), `GET /v1/courses` (paged), `GET /v1/courses/{id}`, `DELETE /v1/courses/{id}`, and the progress routes (D8). Phase 02: `POST/GET /v1/syllabi`, `GET/DELETE /v1/syllabi/{id}`, `POST/GET /v1/tracks`, `GET/PATCH/DELETE /v1/tracks/{id}`, `POST /v1/tracks/{id}/decision-points`, `POST /v1/decision-points/{id}/decide`, `GET/PUT /v1/plan/budget`, `GET /v1/plan`. Paging uses `limit` and `before_id`, same as `core/kata_core/api/routes/journal.py:35`. Journal entries for plan changes: `plan.track_changed`, `plan.budget_changed`, `plan.decision`.

## D14 Feature switches

Decided 2026-11-21. `[trainer] enabled`, `[syllabus] enabled` and `[planning] enabled` are set to true in the example config. When a feature is off, its routes return 404 `{"detail": "feature disabled: <name>"}` from one dependency, `require_feature`.

## D15 Config keys (all added by one phase-01 task to config/kata.example.toml)

Decided 2026-11-21. Keys added to `config/kata.example.toml`: `[jobs] runner_poll_seconds, max_output_bytes`; `[routing] generate_course, extract_syllabus`, and provider `task_classes` gain the same two; `[trainer] enabled, command, timeout_seconds, max_concepts, items_per_concept, min_items, max_artifact_bytes, max_progress_bytes`; `[knowledge] trainer_step, trainer_max_step, known_threshold, learning_threshold, assertion_hold, base_known, base_learning, base_new`; `[syllabus] enabled, model_extract, max_bytes`; `[planning] enabled, skim_share, words_per_unit, minutes_skip, minutes_skim, minutes_practice, minutes_learn`.

## D16 Info surfaces

Decided 2026-11-21. No existing contract shows courses or plans (extension side panel, editor, MCP tools). M5 adds no view. The backlog gets the entry "read-only plan/course view" (phase 02).

## D17 M6 phases in one stage

Decided 2026-11-22. The seven M6 phases (images, stack, proxy, backup, provision, finish) run as one stage with one task per phase, not one stage each. Reason: the owner is away and the phases share files (compose, config template, scripts); splitting them adds merge steps without a gain. Each phase still lands as its own commit and task, and the success criteria of the roadmap cover all of them.

## D18 No pgvector

Decided 2026-11-22. Postgres runs as the plain `postgres` image without the pgvector extension. Reason: the code does not use it. Embeddings are plain `real[]` (`core/migrations/0003_retrieval.sql:2`). Revisit only if retrieval moves to a vector index.

## D19 Reverse proxy: Caddy bound to the tailnet IP, one name with paths

Decided 2026-11-22. Caddy runs as a compose container and listens on the Tailscale IP of the VM only. Its TLS certificate is a Tailscale certificate for the node name. Caddy in a container cannot use the tailscaled socket, so the host runs `tailscale cert` and writes the files that compose mounts read-only (renewal about every 60 days). Reason: Tailscale gives one name per node, so the two names of design 4.2 become one name with paths. The phone page needs a secure context, and a Tailscale certificate provides it. Tailscale serve was rejected because the proxy settings the design needs (no buffering on stream routes, idle timeout above 15 s and 60 s) are set in one config file in Caddy.

## D20 Nightly backup by a host systemd timer, encrypted with openssl

Decided 2026-11-22. The nightly dump runs from a systemd timer on the host, not from a compose sidecar. Reason: the timer survives a stack restart and needs no extra container. Encryption uses `openssl enc -aes-256-cbc -pbkdf2` with a passphrase file, because no `age` binary is in the gate image. The passphrase file path comes from config and is never committed.

## D21 Memory and CPU profiles as env files

Decided 2026-11-22. Two profiles: `deploy/env/small.env` (for the 3 GB VM) and `deploy/env/large.env` (for a real server). Each sets named variables for container memory and CPU limits; the compose file reads them and the same names can be overridden by the environment. Reason: the design budget (12.5) is larger than the VM, so the small profile is the default and the large one is documented, not tuned.

## D22 Migrate command and deep health route

Decided 2026-11-22. A `kata_core.migrate` module provides the migrate command with a `--check` mode that reports pending migrations without applying them. A deep health route checks the database and the migration state, which the design (health checks) requires. Reason: the migrate one-shot in compose needs a command that can run before core starts, and the deep check needs a route to call.

## D23 Shell and Dockerfile linters are not in the gate

Decided 2026-11-22. shellcheck and hadolint are not in the gate image. Reason: the gate has no network and they are not installed. Tests check the image content rules and the script rules by script (for example, a non-root `USER`, a pinned base image, no `latest` tags). shellcheck and hadolint run as a documented manual step in `docs/deployment.md`.

## D24 Notes are git-excluded and updated by the lead

Decided 2026-11-22. Files under `.notes/` are git-excluded. Reason: they hold owner-local steps (for example `.notes/run-on-vm.md`) that must not reach the repo. Agents do not edit them; the lead updates them when the stage finishes.

## Cloud smoke is opt-in, Haiku only, capped by budget, run by the lead

Decided 2026-11-22. `scripts/smoke/real_model.py` sends the prepared cases to the Anthropic API. It runs only when `KATA_SMOKE_REAL=1` is set, the key is in the env, and the model is on `[smoke] allowed_models` (`claude-haiku-5-5`). Spend is capped by `[smoke] budget_micro_usd` (500000 micro-USD, 0.50 USD in the example config); the run stops at the cap and exits 1. The lead runs it by hand. check-all and CI never run it. Reason: a real call costs money and needs a secret, so it stays out of every automatic gate, and one model with a hard cap keeps the spend bounded. Limit: the smoke checks only that replies are non-empty and that JSON replies parse with their task shape; it does not judge answer quality.

## Ledger counts real usage; the estimate is the pre-call guard and fallback only

Decided 2026-11-22. The worker ledger (`POST /usage`) records the cost of each cloud call from the token counts the API reports (`usage`: input, output, cache write, cache read), priced by `cost_from_usage` in `worker/kata_worker/providers/cost.py`. The text-length estimate (ceil(chars / 4) per side) is used in two places only: the pre-call guard, and the fallback when a provider returns no usage. The pre-call guard raises the estimate by `[cost] estimate_safety_percent` (default 150), so the input side of one call is bounded. Output is not known before the call and is not guarded, so the billed output can overshoot the cap by up to one call's cost; the real usage then records it. Prompt caching is opt-in: `[provider_anthropic] cache_system` defaults to false, and when true the system block carries `cache_control` and its cache counts are priced at 1.25x (write) and 0.1x (read) of the input price. Reason: the first real run billed about a third more than the ledger recorded (M7 smoke, 2026-11-22), so the cap has to count what the API bills. Limit: the guard can refuse a call that would have fit, and caching does not help prompts below the minimum cacheable length (about 2048 tokens for Haiku 4.5 class models, per the Anthropic docs; not checked against the live API here).
