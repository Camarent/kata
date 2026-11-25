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
- Cloud is on by token alone: a cloud call needs the API key env var named by `api_key_env`
  to be set, and the class listed in the provider's `task_classes` (see "Routing defaults are
  local first, cloud by token (M17)"). The API key is read from that env var, never from the config file.
- A cost cap is built into the core and spend is tracked per call, per user.
- Chat subscriptions and APIs are billed separately; subscription tokens must not be used in
  application code. The application uses API keys through its adapters.
- The cloud provider is chosen with tests on the real tasks and the provider research
  ([`research/benchmarks`](research/benchmarks)); the adapters keep this a
  configuration change.

## Secret scanner

Two layers behind a scanner interface. Client masking in the terminal session tool uses a
small dependency-free pattern list. The core scans
every outgoing text before any cloud call with `core/kata_core/egress/scanner.py`, no subprocess (for the hook, superseded by "Pre-commit scans staged lines in process with the one scanner"). TruffleHog is rejected (AGPL licence does not fit
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
- **Pre-commit secret check.** Runs the core scanner locally, so it does not depend on the core (superseded for the hook by "Pre-commit scans staged lines in process with the one scanner": the scanner is `core/kata_core/egress/scanner.py`, no subprocess).
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

## Firefox gecko id was kata@kata.local (now kata@kata.invalid), minimum version 128.0

Decided 2026-11-21. `browser_specific_settings.gecko.id` is `kata@kata.invalid` and `strict_min_version` is `128.0`, both set in `extension/build/manifest.mjs`. The id is a fixed value chosen for this project; 128.0 is the chosen minimum, not a claim about when `sidebar_action` appeared. Change the id and the minimum only together with the Firefox add-on listing, because the id is what Firefox uses to tell installed versions apart.

Superseded in part by "Extension has no build-time server config (M15)" (2026-11-23): the gecko id is `kata@kata.invalid`. The minimum 128.0 is unchanged.

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

Superseded in part by "Routing defaults are local first, cloud by token (M17)" (2026-11-24): the chain order is `local,anthropic` by default, and the cloud is on by token alone, not by `cloud_enabled`. The one chain per class and the wrap order still hold.

## Routing defaults are local first, cloud by token (M17)

Decided 2026-11-24. Every task class in `[routing]` of `config/kata.example.toml` (`tag`, `explain`, `summary`, `batch`, `generate_course`, `extract_syllabus`) lists `local,anthropic`: the local model answers first, the cloud is the second try. `[local_capability]` gives each class a verdict: a local model name (`kata-l` for every class for now) or `cloud-only`. A class marked `cloud-only` is never sent to the local provider; `worker/kata_worker/providers/policy.py` skips it there. The cloud is on when the env var named by `[provider_anthropic] api_key_env` is set and not empty. There is no `cloud_enabled` switch any more: text leaves the machine only when the token is set and the class is in the cloud provider's `task_classes`. Reason: the local model is the default, and the token is the one switch the owner already controls. Limit: the `kata-l` verdicts are a placeholder until the capability audit (`docs/research/benchmarks/LOCAL_AUDIT.md`) sets them; no live cloud call is made by the tests.

## Needs-cloud jobs are refused with 409 before queueing (M17)

Decided 2026-11-24. A job whose class is `cloud-only` in `[local_capability]`, with no cloud token in the environment, is not queued. `core/kata_core/jobs/needs_cloud.py` maps job kinds to task classes (`JOB_KIND_CLASS`; a kind not in it never needs the cloud). The API answers 409 with `detail.code` `needs_cloud` on `POST /v1/jobs` (`core/kata_core/api/routes/jobs.py:92`), on `POST /v1/courses` (`core/kata_core/api/routes/courses.py:148`) and on the syllabus extract route (`core/kata_core/api/routes/syllabi.py:131`). The check is `refuse_needs_cloud` (`core/kata_core/api/deps.py:61`). The extension shows a short needs-cloud text for that code (`extension/src/coreClient.ts:141`). Reason: a job that cannot run should fail at the request, not sit in the queue. Limit: the check reads the token from the core's environment only; a token set on the worker alone does not clear it.

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

Decided 2026-11-21. `core/kata_core/trainer/cli.py` defines the `TrainerCli` Protocol: `next_id(workdir) -> str`, `add(workdir, item) -> str`, `validate(workdir) -> list[Diagnostic]`, `lock(workdir)`, `build(workdir, outdir) -> list[str]`. `SubprocessTrainerCli(argv_prefix: list[str], timeout)` takes an argv list, never a shell; the prefix comes from config `[trainer] command` (a TOML array). Trust boundary: the executable is supplied by config; the sec-auditor must note this. A non-zero exit or bad JSON raises `TrainerError`. Machine output contract, also used by the fake: each call prints one JSON object on stdout. next-id `{"id": "i0001"}`; add `{"id": "..."}`; validate `{"ok": bool, "diagnostics": [{"item": id, "message": str}]}`; lock `{"ok": true}`; build `{"files": [paths]}`. The fake was `tests/fakes/fake_trainer_cli.py` (no longer in tests/fakes), run as `[sys.executable, <path>]` so no exec bit is needed; item text containing `FAKE_INVALID` gets a diagnostic. The real binary format is unverified and goes to the backlog.

Superseded by "Dojo CLI adapter replaces the D7 JSON contract" (2026-11-23): the real `dojo` CLI prints text, not JSON. Also superseded by "Real dojo contract corrections, part 2 (M14)" (2026-11-23): the id prefix and the `next-id` argument changed.

## D8 Progress documents (migration 0010_mastery.sql, with D9 tables)

Decided 2026-11-21. Table `trainer_progress(course_id PK FK CASCADE, user_id, revision int NOT NULL, doc jsonb, updated_at)`. Routes sit on the API origin with Bearer auth (trainer origin deferred, D5). `GET /v1/courses/{id}/progress` returns 200 `{"revision": n, "doc": obj|null}` with `ETag: "n"` (n=0 and doc null when none). `PUT /v1/courses/{id}/progress` takes the doc as body and header `If-Match: "n"`: missing header gives 428, malformed body gives 400, mismatch gives 412 with body `{"revision": cur, "doc": cur_doc}` and ETag, success gives 200 `{"revision": n+1, "evidence_written": k, "skipped_items": s}` with ETag. Compare-and-set: `UPDATE ... WHERE course_id AND user_id AND revision = n`; the first save is `INSERT ... ON CONFLICT DO NOTHING` with n=0; zero rows gives 412. One transaction holds the D9 writes too. Doc shape: `{"items": {"<item_id>": {"ok": int>=0, "bad": int>=0, "stage": int}}, "resetAt"?: str}`; other keys are kept verbatim. Size cap `[trainer] max_progress_bytes` gives 413. A course not in `ready` gives 409.

Superseded by "Progress documents are dojo-native" (2026-11-23): the doc shape and the 4 MiB cap changed.

## D9 Knowledge update (decisions in code only)

Decided 2026-11-21. Table `trainer_evidence(id, user_id, course_id FK SET NULL, item_id, concept_id, ok, bad, delta real, created_at, UNIQUE(user_id, course_id, item_id, ok, bad))` is append-only; ON CONFLICT DO NOTHING means a repeated or merged save adds nothing (critique F24). Per accepted save, each item whose `ok` or `bad` rose versus the previous revision is mapped through `course_item_map`; unmapped items are skipped and counted. Falling counters (reset) write nothing. Table `concept_mastery(user_id, concept_id, score real CHECK 0..1, updated_at, PK)`. Base score when absent comes from concept_marks state (known 0.9, learning 0.5, new or none 0.1, all from config). Step: `delta = clamp(step * (d_ok - d_bad), -max_step, +max_step)`, score clamped to [0,1]; config `[knowledge] trainer_step=0.1, trainer_max_step=0.3`; items applied in item-id order. State: score >= `known_threshold` (0.8) is known; >= `learning_threshold` (0.4) is learning; otherwise new. `concept_marks` gets `source text NOT NULL DEFAULT 'user' CHECK (user|trainer)` in 0010. When the mark is absent or its source is trainer, write the new state (source trainer) when it changes. When the source is user and the trainer disagrees, keep the user mark until `[knowledge] assertion_hold` (3) contrary trainer evidence rows exist since the mark's updated_at, then overwrite it. Every state change by the trainer writes journal `knowledge.trainer_update {concept_id, from, to, score}`: nothing changes silently. Deleting a course keeps evidence and mastery (course_id becomes NULL). The full 7.5 model (weights, decay, other evidence types, recompute) stays in the backlog.

## D10 Syllabus import and triage (phase 02, migration 0012_syllabus.sql)

Decided 2026-11-21. Parser `core/kata_core/importer/syllabus.py` sits next to skill_list.py, the existing content ingest. It reads markdown headings `#` and `##`; otherwise numbered lines (`1.`, `Module 1:`); otherwise one module. Model help runs only when `[syllabus] model_extract = true` and no structure is found: job `syllabus.extract` (worker, D4). The output hook accepts a module only if its text is a substring of the source (whitespace-normalized) and its title is at most 120 chars; otherwise it falls back to one module. Tables: `syllabus(id, user_id, title, status, created_at)`, `syllabus_module(id, syllabus_id, position, title, body, words)`, `syllabus_module_concept(module_id, concept_id)`. Matching: visible concept labels (word boundary, case-insensitive) in title and body. Triage per module from mastery scores (D9): no concept gives new; all at or above known gives known; any at or above learning gives partly_known; otherwise new. Action: known gives skip; partly_known gives skim if the known share is at least `[planning] skim_share` (0.5), else practice; new gives learn. Effort minutes = action minutes x units, where units = max(1, ceil(words / `words_per_unit` 400)); minutes are skip 0, skim 15, practice 45, learn 90 (`[planning]`).

## D11 Tracks, budget, allocation (migration 0013_tracks.sql)

Decided 2026-11-21. Table `track(id, user_id, name, deadline date, priority int, status active|paused|dropped)`; table `track_item(track_id, position, module_id NULL, label, action, minutes)`; table `planning_budget(user_id PK, minutes_per_week, updated_at)`. Capacity(d) = floor(minutes_per_week * days(now..d) / 7). Allocation is pure, in `core/kata_core/planning/allocate.py`: active tracks are sorted by (deadline, -priority, id); items go in position order; an item is allocated while the cumulative total stays within capacity(track deadline); the first item that does not fit and every later item of that track are deferred. Invariants (property test, `random.Random(seed)` with seeds 0..199): for every deadline d, the allocated minutes of tracks with deadline <= d are at most capacity(d); the total is at most capacity(max deadline); non-active tracks get 0; items are never split; the same input gives the same output. Clock: `now: Callable[[], datetime]` is injected (same pattern as `core/kata_device/precommit.py:32`); the API gets it from one dependency that tests override.

## D12 Decision points

Decided 2026-11-21. Table `decision_point(id, user_id, track_id, after_position, due_on date, status open|decided, choice continue|switch|drop, target_track_id, decided_at)`. An open point means items after `after_position` are not allocated. continue makes them allocatable; switch pauses the track and activates the target track; drop drops the track. Each decision writes a row and journal `plan.decision`; the next allocation differs (tested).

## D13 API (phase 02 for planning; 01 for courses/progress)

Decided 2026-11-21. Phase 01: `POST /v1/courses` (202 with job id), `GET /v1/courses` (paged), `GET /v1/courses/{id}`, `DELETE /v1/courses/{id}`, and the progress routes (D8). Phase 02: `POST/GET /v1/syllabi`, `GET/DELETE /v1/syllabi/{id}`, `POST/GET /v1/tracks`, `GET/PATCH/DELETE /v1/tracks/{id}`, `POST /v1/tracks/{id}/decision-points`, `POST /v1/decision-points/{id}/decide`, `GET/PUT /v1/plan/budget`, `GET /v1/plan`. Paging uses `limit` and `before_id`, same as `core/kata_core/api/routes/journal.py:35`. Journal entries for plan changes: `plan.track_changed`, `plan.budget_changed`, `plan.decision`.

## D14 Feature switches

Decided 2026-11-21. `[trainer] enabled`, `[syllabus] enabled` and `[planning] enabled` are set to true in the example config. When a feature is off, its routes return 404 `{"detail": "feature disabled: <name>"}` from one dependency, `require_feature`.

## D15 Config keys (all added by one phase-01 task to config/kata.example.toml)

Decided 2026-11-21. Keys added to `config/kata.example.toml`: `[jobs] runner_poll_seconds, max_output_bytes`; `[routing] generate_course, extract_syllabus`, and provider `task_classes` gain the same two; `[trainer] enabled, command, timeout_seconds, max_concepts, min_items, max_artifact_bytes, max_progress_bytes`; `[knowledge] trainer_step, trainer_max_step, known_threshold, learning_threshold, assertion_hold, base_known, base_learning, base_new`; `[syllabus] enabled, model_extract, max_bytes`; `[planning] enabled, skim_share, words_per_unit, minutes_skip, minutes_skim, minutes_practice, minutes_learn`. Keys added later: `[trainer] max_courses_per_user` (M16), and `open_link_ttl_seconds` and `open_link_key_file` (see "Open-link tokens are HMAC-SHA256 signed").

## D16 Info surfaces

Decided 2026-11-21. No existing contract shows courses or plans (extension side panel, editor, MCP tools). M5 adds no view. The backlog gets the entry "read-only plan/course view" (phase 02).

Superseded in part by "Course limit and unique names (M16)" (2026-11-23): the side panel now lists, creates and deletes courses. The plan view is still in the backlog.

## D17 M6 phases in one stage

Decided 2026-11-22. The seven M6 phases (images, stack, proxy, backup, provision, finish) run as one stage with one task per phase, not one stage each. Reason: the owner is away and the phases share files (compose, config template, scripts); splitting them adds merge steps without a gain. Each phase still lands as its own commit and task, and the success criteria of the roadmap cover all of them.

## D18 No pgvector

Decided 2026-11-22. Postgres runs as the plain `postgres` image without the pgvector extension. Reason: the code does not use it. Embeddings are plain `real[]` (`core/migrations/0003_retrieval.sql:2`). Revisit only if retrieval moves to a vector index.

## D19 Reverse proxy: Caddy bound to the private network address, one name with paths

Decided 2026-11-22. Caddy runs as a compose container and listens on the private network address of the VM only. Its TLS certificate is a certificate for the node name, issued by the private network. Caddy in a container cannot use the network client's socket, so the host requests the certificate and writes the files that compose mounts read-only (renewed every 30 days by `kata-cert.timer`, see D25). Reason: the network gives one name per node, so the two names of design 4.2 become one name with paths. The phone page needs a secure context, and that certificate provides it. The network's serve feature was rejected because the proxy settings the design needs (no buffering on stream routes, idle timeout above 15 s and 60 s) are set in one config file in Caddy.

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

## D25 Build on dev, ship images to the VM; the VM runs no builds

Decided 2026-11-23. The kata image is built on the dev machine as `kata:<git short sha>` (`deploy/compose.build.yaml`), checked, and shipped over SSH with `deploy/ship.sh` (`docker save | ssh docker load`). The VM gets the deploy files (`compose.yaml`, `Caddyfile`, `kata.host.toml`, `env/`, `versions.env`, scripts, `systemd/`) and runs `docker compose up -d` on the loaded tag. Compose never builds on the VM. The certificate renewal timer (`deploy/systemd/kata-cert.timer`) renews every 30 days. The extension gets its core base URL at build time from `KATA_EXTENSION_BASE_URL`. Reasons: a small attack surface on the VM (no toolchain, no compilers, no package builds on a host that serves the owner's data); the 3 GB VM does not have the memory for a build next to Postgres and the core; pins (base digest, gitleaks and trainer checksums) are checked where the image is built, so the VM only receives the result; and one image tag per commit makes rollback a re-ship of an image already built. Limit: the image is only as fresh as the last ship, and secrets and the Dockerfile never leave dev or the VM's `secrets/` directory.

Superseded in part by "Extension has no build-time server config (M15)" (2026-11-23): the extension takes no core URL at build time any more, so `KATA_EXTENSION_BASE_URL` is removed. The user types the server URL in the side panel.

## Cloud smoke is opt-in, Haiku only, capped by budget, run by the lead

Decided 2026-11-22. `scripts/smoke/real_model.py` sends the prepared cases to the Anthropic API. It runs only when `KATA_SMOKE_REAL=1` is set, the key is in the env, and the model is on `[smoke] allowed_models` (`claude-haiku-5-5`). Spend is capped by `[smoke] budget_micro_usd` (500000 micro-USD, 0.50 USD in the example config); the run stops at the cap and exits 1. The lead runs it by hand. check-all and CI never run it. Reason: a real call costs money and needs a secret, so it stays out of every automatic gate, and one model with a hard cap keeps the spend bounded. Limit: the smoke checks only that replies are non-empty and that JSON replies parse with their task shape; it does not judge answer quality.

## Local-model smoke is opt-in, run by the lead, shape only

Decided 2026-11-22. `scripts/smoke/local_model.py` sends the prepared cases to the local OpenAI-compatible runtime through `LocalProvider`, one warm-up request per model first, then each case timed. It runs only when `KATA_SMOKE_LOCAL=1` is set and a base URL is given (`--base-url` or `KATA_SMOKE_LOCAL_BASE_URL`). The lead runs it by hand. check-all and CI never run it. Local-first routing stays the default: the `tag` class still tries `local` first and no cloud call is added. Reason: a local model run needs a host that only the lead reaches, and the base URL must stay out of logs and the repo. Limit: the smoke checks only that replies are non-empty and that JSON replies parse with their task shape; it does not judge answer quality.

## Ledger counts real usage; the estimate is the pre-call guard and fallback only

Decided 2026-11-22. The worker ledger (`POST /usage`) records the cost of each cloud call from the token counts the API reports (`usage`: input, output, cache write, cache read), priced by `cost_from_usage` in `worker/kata_worker/providers/cost.py`. The text-length estimate (ceil(chars / 4) per side) is used in two places only: the pre-call guard, and the fallback when a provider returns no usage. The pre-call guard raises the estimate by `[cost] estimate_safety_percent` (default 150), so the input side of one call is bounded. Output is not known before the call and is not guarded, so the billed output can overshoot the cap by up to one call's cost; the real usage then records it. Prompt caching is opt-in: `[provider_anthropic] cache_system` defaults to false, and when true the system block carries `cache_control` and its cache counts are priced at 1.25x (write) and 0.1x (read) of the input price. Reason: the first real run billed about a third more than the ledger recorded (M7 smoke, 2026-11-22), so the cap has to count what the API bills. Limit: the guard can refuse a call that would have fit, and caching does not help prompts below the minimum cacheable length (about 2048 tokens for Haiku 4.5 class models, per the Anthropic docs; not checked against the live API here).

## Dojo CLI adapter replaces the D7 JSON contract

Decided 2026-11-23. `core/kata_core/trainer/dojo_cli.py` (`DojoTrainerCli`) runs the real `dojo` CLI (dojo-kit release) as `[trainer] command` plus `<subcommand> <dir> ...`, never through a shell. Output is text, not JSON: `next-id` takes the unit as a positional argument and prints the id; `add` prints `added N items to content/<unit>.jsonl: <first> .. <last>` and the ids (`ADDED_HEADER`); `validate` reports diagnostics on stdout. Exit codes: 0 ok; 1 content errors (diagnostics on stdout, or stderr for shape errors); 2 usage or I/O errors, which raise `TrainerError`. An exit 1 with no error count raises `TrainerError`. Ids come from the output, never computed: a dojo id is `<unit>-<n>`. The `TrainerCli` Protocol gains a `unit` argument to `next_id`. The draft to dojo item mapping lives in `core/kata_core/trainer/build.py` (`_dojo_item`): type `gap` (`DOJO_ITEM_TYPE`), unit `kata` (`DOJO_UNIT`), `answers=[answer]`, no `concept_id`. Reason: the D7 JSON contract was never measured; the binary is now measured. Limit: the text parser depends on the dojo-kit release pinned in the install; a new release may change the text.

Superseded in part by "Real dojo contract corrections, part 2 (M14)" (2026-11-23): `next-id` takes the id prefix (the unit name without `-`), not the unit name, and ids are `<prefix>-<n>`.

## Progress documents are dojo-native

Decided 2026-11-23. A progress document is the dojo-native shape: `items` maps each item id to `{"ok": int>=0, "bad": int>=0, "s": ...}`, `resetAt` is a number (epoch milliseconds, not a string), and any other key is kept verbatim on save and read. The core validates only `items` (`_doc_problem` in `core/kata_core/api/routes/course_progress.py:59`): a non-object document or a bad count gives 400. The size cap is `[trainer] max_progress_bytes = 4194304` (4 MiB; was 262144 in D8's shape) and gives 413 above it. Reason: the dojo CLI writes these keys, and the core must keep them unchanged. Limit: `s` is not checked by the core.

## PATCH delta save

Decided 2026-11-23. `PATCH /v1/courses/{id}/progress` merges a delta into the stored document: `items` entries replace stored entries by id, other stored items are kept, and other top-level keys replace stored ones. It uses the same `If-Match` compare-and-set and the same codes as PUT (428, 400, 413, 412, 409, 404). Evidence is written for the delta's items only (`save_delta` in `core/kata_core/trainer/progress.py:178`). On revision 0 or no stored document it returns 412 with body `{"revision": 0, "doc": null}`: the client uses PUT first. Reason: a save of only the changed items keeps the other items unchanged without resending them. Limit: a delta cannot remove an item; a full PUT is the only way to do that.

## Import without evidence

Decided 2026-11-23. `PUT /v1/courses/{id}/progress?import=1` stores the document and writes no `trainer_evidence` rows, so the response has `evidence_written: 0`. The revision still moves and `skipped_items` is reported as before. Reason: importing an old progress file must not change mastery or the marks. Use it only for a one-time migration of old progress; ordinary saves do not set the flag.

## Course artifact serving contract

Decided 2026-11-23. The build writes one course folder `D/<course_id>/`, where `D` is the build out dir and `<course_id>` is that folder's name (`_only_course_dir` in `core/kata_core/trainer/dojo_cli.py:155`). The files are served as static files: relative URLs only, and the page needs HTTP (it does not work from `file://`). Core keeps the files in `course_file`-style artifact rows (`add_artifacts`, `core/kata_core/trainer/build.py`), capped by `[trainer] max_artifact_bytes`. How the files reach the browser is decided in the next stage: signed open links and `GET /c/{token}/{path}`, both through the proxy (see `docs/api.md`, "Open links"). Limit: until that stage, a built course cannot be opened in a browser.

Superseded by "Serving CSP and headers are fixed in code" (2026-11-23): `GET /c/{token}/{path}` serves the files now, so a built course can be opened in a browser.

Artifact keys changed (M13 task-6): they are relative to the course folder (`index.html`, `data/content.json`), not `<course_id>/index.html`, so the root page is served. Rows stored under the old keys are not served at the root. No course built before this change is stored: the first deploy (M6) has not run. If one exists, rebuild it; there is no migration.

## Open-link tokens are HMAC-SHA256 signed

Decided 2026-11-23. An open link is `base64url(payload).base64url(mac)`, payload `[user_id, course_id, expires_at]`, mac = HMAC-SHA256 over the payload (`sign` and `verify` in `core/kata_core/trainer/open_link.py`; `verify` compares with `hmac.compare_digest`). The key is read from the file named by `[trainer] open_link_key_file`; it must be at least 32 bytes (`MIN_KEY_BYTES`). `main` exits 1 at startup, logging `open link key: ...`, when `[trainer] enabled` is true and the key file is missing, empty or short (`core/kata_core/__main__.py:27`). The link lifetime is `[trainer] open_link_ttl_seconds` (43200 in the example config). The link base is `[core] public_url` when set, else the URL the request came in on (`core/kata_core/api/routes/course_open.py:33`). Tests inject the key as `app.state.open_link_key`; when it is unset the routes load the key file. Reason: the link carries its own credential, so the course page needs no bearer token. Limit: one key signs and checks every link; rotating it invalidates all open links at once.

## Serving CSP and headers are fixed in code

Decided 2026-11-23. `GET /c/{token}/{path}` (`core/kata_core/api/routes/course_serve.py:55`) sends every file with `SERVED_HEADERS` (line 27): `Cache-Control: private, max-age=0, must-revalidate`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `Content-Security-Policy` set to the constant `CONTENT_SECURITY_POLICY` (line 23): `default-src 'none'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'`. An empty path serves `index.html`. Every failure (bad token, wrong course, course not `READY`, missing file) gives the same 404 with the same headers. Reason: the course page needs inline script for the bridge stub, and the rest of the policy stays closed. Limit: `'unsafe-inline'` scripts are allowed, so the CSP does not block injected inline script; the signed token is the access control.

## Course bridge design

Decided 2026-11-23. The extension bridge (`runBridge`, `extension/src/bridge.ts:93`) does nothing unless the page origin equals the saved session's origin (`originOf(session.baseUrl)`, `extension/src/bridge.ts:105`). It injects the page stub as inline script text (`injectStub`) with a fresh channel id (`newChannel`: 16 random bytes, 32 hex characters) and removes the element at once. The bridge answers only requests whose `channel` matches, whose `event.source` is the page window and whose `event.origin` is the page origin (`startBridge`, `extension/src/bridge.ts:60-67`). Requests use `dir: "req"`, replies `dir: "res"`. Registration: `registerBridge` (`extension/src/bridgeRegister.ts:47`) registers script id `kata-bridge` on every host of the origin's scheme with path `/c/*` (`bridgeMatchPatterns`); the bridge itself checks the exact origin. The session token stays in the background service worker and never reaches the page. The page user id is fixed to `kata` (`extension/src/pageStub.ts:186`). A progress save that gets 412 is retried once with the fresh revision when the stored document equals the one last seen (`extension/src/progressBridge.ts:136`); otherwise the save fails with `conflict: stored progress changed`. Reason: the course page saves progress without holding a credential. Limit: the user id `kata` is fixed, so it is not a per-user identity.

Superseded in part by "Extension has no build-time server config (M15)" (2026-11-23): the bridge origin is no longer derived from `DEFAULT_BASE_URL`, which is removed. The bridge runs only when the page origin equals `originOf(session.baseUrl)`, the server URL the user saved in the side panel (`extension/src/bridge.ts:105`). The rest of this entry stands.

## Aux documents are reassembled in the bridge

Decided 2026-11-23. A split document is a main path whose body has `parts: k` (1..64, `MAX_PARTS` in `extension/src/pageStub.ts:20`), stored with the parts `<main>.part1` .. `<main>.part<k>`. The page stub (`installStub`, `extension/src/pageStub.ts:19`) merges the parts' `items` into the main body and saves the whole document once every part is present (`complete`). Core sees only the whole document: no core change and no migration of stored rows. Reason: a save happens once per page save, so the D9 evidence is written once, and core has no dojo document format. Failure mode: when the main document arrives before its parts, it waits in `partsByMain` (`extension/src/pageStub.ts:35`) and is saved after the last part; a plain set of the same path supersedes a waiting main set (`extension/src/pageStub.ts:155`). Limit: the waiting set is held in page memory only, so a page reload drops it.

## Real dojo contract corrections (M13)

Decided 2026-11-23. The dojo adapter follows the real dojo CLI: a course starts with an `init` step (`dojo init <id> --title T --workspace <dir>`, the course folder is `<workspace>/<id>`, read from the printed line; `DojoTrainerCli.init` `core/kata_core/trainer/dojo_cli.py:62`). Every item goes into one unit, `unit-1` (`DOJO_UNIT` `core/kata_core/trainer/build.py:40`); dojo ids come back as `unit-1-<n>`. The course id is `kata-<id>`. Warnings never fail a build: `validate` returns only `severity=error` diagnostics (`core/kata_core/trainer/dojo_cli.py:110`). The artifact cap is 16 MiB (`[trainer] max_artifact_bytes = 16777216`). `wasm` and `web` are optional config assets, passed to `dojo build --wasm` and `--web` only when set (`core/kata_core/trainer/dojo_cli.py:122`, `:124`). Reason: the real dojo rejects the old argv and id shape, and a warning must not drop a whole course. Limit: the measured id rules (what dojo accepts in an id) are recorded by the next id-probe task, not here.

Superseded in part by "Real dojo contract corrections, part 2 (M14)" (2026-11-23): dojo ids are `unit1-<n>` for unit `unit-1` (hyphen removed from the prefix), not `unit-1-<n>`.

## Real dojo contract corrections, part 2 (M14)

Decided 2026-11-23. The adapter, the fake (`tests/fakes/fake_dojo.py`) and the real-dojo smoke follow three more real dojo shapes.
- Prefix rule: the id prefix is the unit name without `-` (`_id_prefix` `core/kata_core/trainer/dojo_cli.py:134`). The real dojo accepts only letters and digits in it. `next-id` takes the prefix; `next_id` and `add` check the ids against it. Unit `unit-1` gives ids `unit1-<n>`.
- content.json shape: `data/content.json` is an object, not a list: `v`, `course` (`id`, `title`, `uiLanguage`, `contentLanguage`, `units`), `items` (the item list), `version`, `lock` (`v`, `ids`, `retired`). The smoke (`scripts/smoke/dojo_real.py:117-129`) checks `version` against the manifest, the course id, the items list and the lock ids.
- manifest shape: `files` entries are objects `{"path", "bytes"}`; a plain string entry is still read (`_manifest_files` `core/kata_core/trainer/dojo_cli.py:225`). The manifest also has `version`, `totalBytes`, `wasmBytes` and `lang`. The build writes `manifest.json` and `THIRD_PARTY_NOTICES.md` but leaves both out of `files`; `_artifact_files` (`:200`) adds them to the artifact list when they exist.

Reason: the real dojo writes these shapes, and the earlier list and string shapes did not match it. Limit: the fake copies the shapes from one measured build; fields the core does not read (`lang`, `wasmBytes`, `retired`) are not checked.

## Extension has no build-time server config (M15)

Decided 2026-11-23. The extension has no core URL at build time. `KATA_EXTENSION_BASE_URL` is gone from `extension/build/build.mjs`, `extension/manifest.base.json` grants no host for one server, and `extension/src/config.ts` has no default base URL. The user types the server URL in the side panel sign-in form. `validateServerUrl` (`extension/src/serverUrl.ts`) accepts http and https only, with no credentials, query or fragment; it drops trailing slashes and keeps a base path. Reason: one build serves every core (a laptop, the VM over the private network, a port other than 8080). A build-time URL would need one zip per server, and the owner would have to rebuild to move a core.

Runtime permission flow: Connect first asks the browser for the origin pattern `<origin>/*` (`extension/src/sidepanelBoot.ts`, `onSignIn`). The request is the first awaited call, so it stays inside the click. A declined request saves nothing. Then the background `signIn` (`extension/src/background.ts`) probes `GET /v1/health/deep` (the kata health document, or the error text), redeems the enrolment code once and saves `{baseUrl, token}`. The enrolment code is never stored. A failure after the grant removes the new origin, unless it is the current session's origin. Change server grants the new origin first and removes the old one after the new session is saved. Disconnect removes the origin and clears the session. Removing the origin in the browser UI drops the panel back to first run (`permissions.onRemoved`).

No default server: a fresh install has no saved session and no granted origin. The panel shows the sign-in form only, with no URL filled in.

Bridge lifecycle: the bridge script `bridge.js` is registered with id `kata-bridge` for `<scheme>://*/c/*` of the saved origin (`extension/src/bridgeRegister.ts`, `bridgeMatchPatterns`, `registerBridge`). It is re-synced on install and browser start (`wireBridgeRegistration`) and after sign-in and disconnect (`syncBridge`). It is unregistered when no session is saved or when the origin permission is removed. The exact origin is still checked at runtime in `runBridge`.

Gecko id: `kata@kata.invalid` (a reserved domain, so it never collides with a real add-on), set in `extension/build/manifest.mjs`. The minimum stays 128.0. Change the id only together with the Firefox add-on listing.

Version source: `KATA_EXTENSION_VERSION` when set (it must be `x.y.z`, else the build fails); otherwise the `version` of `extension/package.json` (`extension/build/build.mjs`). The manifest version is stamped by the build, never read from the base file.

Health route: the first-run probe calls `GET /v1/health/deep` (`extension/src/coreClient.ts`, the unauthenticated deep check). A network failure or timeout and an answer that is not the kata health document are separate errors, so the panel shows which one happened.

Release assets: a `v*` tag runs `.github/workflows/release-extension.yml`. It runs the extension tests, builds both browsers, writes `kata-extension-<version>-firefox.zip`, `kata-extension-<version>-chrome.zip` and `SHA256SUMS`, and publishes them as a GitHub release. The actions are pinned by major tag (`@v7`), the same as `.github/workflows/ci.yml`. Reason: one unbranded build per browser serves every server, so the owner installs the zip and types the server URL.

Limit: none of these flows is tested in a real browser. Not covered: the origin permission prompt, the `kata-bridge` registration and the course-page bridge. Vitest checks them with fake browser APIs (`extension/tests/`); the browser tests load the built extension but do not drive a real core through these steps.

## Course limit default lives in the example config (M16)

Decided 2026-11-23. `trainer.max_courses_per_user` defaults to 10 only in `config/kata.example.toml` (and its copy `deploy/kata.host.toml`). `core/kata_core/config.py` holds no default. `MAX_COURSES_UNLIMITED = 0` is the single named constant for the unlimited value; the negative check and the later API route use it. Deviation from the brief, which asked for a named constant for the default: the config file is the one default home, as the other `[trainer]` keys are. Values must be integers; a negative value, a string, a bool or a float raises `ConfigError` at startup, from file or env override.

Reason: one default home keeps the example and the host config in sync (the host file copies the example by hand, its header says so). A second default in code would drift from both.

Limit: the course limit is only validated here; no route enforces it yet (later task).

Superseded in part by "Course limit and unique names (M16)" (2026-11-23): `POST /v1/courses` enforces the limit now.

## Course limit and unique names (M16)

Decided 2026-11-23. A user holds at most `[trainer] max_courses_per_user` courses. The default, 10, is set in `config/kata.example.toml` (and `deploy/kata.host.toml`); 0 means unlimited. Deviation from the brief, which asked for a named constant: the default lives in the config file, as recorded in "Course limit default lives in the example config (M16)". The only named constant is `MAX_COURSES_UNLIMITED = 0` (`core/kata_core/config.py:26`).
- Limit: `POST /v1/courses` answers 409 `course_limit` when the user already holds the limit (`core/kata_core/api/routes/courses.py:149`). The count includes every status, so a failed course keeps its slot until it is deleted.
- Unique names: a title is unique per user after normalisation (lower case, trimmed, runs of whitespace as one space). A duplicate answers 409 `course_name_taken`. The check is `title_taken` (`core/kata_core/trainer/store.py:68`); the unique index `course_user_id_title_norm_uidx` (`core/migrations/0014_course_unique_title.sql`) backs it, and a race that the check misses maps to the same 409 (`DuplicateCourseTitle`, `core/kata_core/trainer/store.py:22`).
- Empty titles: an empty or whitespace-only title answers 422 `course_title_empty` (`_check_title` `core/kata_core/api/routes/courses.py:90`) before any write. The new 409 and 422 bodies are `{"code", "message"}` in `detail`; the 404 `course not found` keeps its plain text.
- Migration 0014 renames existing duplicates: the oldest course of each normalised title keeps its name; each later duplicate gets the lowest ` (k)` suffix (k >= 2) that no course of the user uses. A rerun changes nothing.
- Race: the count and the insert run under a row lock on the user (`lock_user` `core/kata_core/trainer/store.py:78`), so two creates of one user cannot both pass the limit.
- Delete: `DELETE /v1/courses/{course_id}` (204) frees the slot and the title. The side panel asks for a second click ("Confirm delete") first; the server does not ask.
- No rename route: a title is set at create and kept. A rename would need the same unique check; it is not built.
- Panel: the side panel shows "n of limit" when the limit is above 0, and a create form. A failed create shows the text from `courseErrorText` (`extension/src/coreClient.ts:132`).

Reason: each course runs a generate job and a build job, so the limit caps that work per user; unique titles let the list tell courses apart.

Limit: the limit and the title rule are checked by the API tests and the Vitest panel tests with fake browser APIs; no real browser run drives them.

## Local models through a worker on the user's GPU machine (M18)

Decided 2026-11-23.

- The worker is user-side. It pulls jobs from core over plain outbound HTTP, and core never needs its address (see "Worker link"). For local models, one worker runs on the GPU machine next to Ollama and talks to `127.0.0.1`. The Ollama port and the model-host info service port both come from settings. The web server never reaches the GPU machine, so it needs no network grant to it.
- It is the same worker program as on the web server, with its own device token for the user. The web server's worker stays for cloud jobs.
- The extension is the single entry point, meaning whichever client the user runs (browser extension or VS Code extension). Both use the same core control jobs. A browser cannot run `modelctl`, and core is remote, so control goes client, core, job queue, GPU-machine worker, `modelctl`. Control jobs: `modelhost.up`, `modelhost.use`, `modelhost.measure`, `modelhost.status`.
- Permissions: the worker runs as the normal user that owns the model-host folder and its `data/` (this avoids root-owned `data/` errors) and is in the docker group; it never runs as root. It accepts a fixed allow-list of subcommands with validated arguments, never a shell string. A control job runs only for the user whose device token the worker holds.
- kata never calculates what fits. It asks `GET /capabilities` and reads `schema` 2: `fits_alone` is the measured answer and `fits_together` the measured pairs. `null` means unknown, never "fits". `kata-l` and `kata-m` never fit together, so the scheduler swaps them.
- Cloud turns on when its token is configured (see the routing entry). The per-repository code opt-in stays for now.
- No machine-specific numbers (sizes, headroom) appear in code, docs or tests.

Reason: the GPU machine sits behind the user's own network, so it must reach out; keeping one worker program and one job queue avoids a second control path.

## D39 Review is self-rating, with "Quiz me"

Decided 2026-11-24. Status: design decision, UI not built yet. No "due" concept and no "you missed this" nagging: progress and velocity are the signals. Review is self-rating: the three buttons (Known, Learning, New) set the state directly (today `setConcept` in `extension/src/background.ts:52`). "Quiz me" gives up to 5 prefilled questions for one topic. A correct quiz answer moves New up to Learning (D19). Open: which concepts Review lists when nothing is due.

## D40 Mark known after a quiz

Decided 2026-11-24. Status: design decision, UI not built yet. At the end of a quiz each concept has a manual "Mark as Known" button, so the owner can confirm and the system holds that state with source `user`. A quiz alone moves only New to Learning (D19).

## D41 Knowledge sources for quizzes (superseded)

Decided 2026-11-24. Superseded by D45 (2026-11-24): the owner's own materials are not enough for quiz questions, so kata needs a source of general knowledge. The first option was the model's own knowledge or fetched reference sources, to decide with a research pass. Untrusted-text rules (D27) apply to anything fetched.

## D42 Sorting in lists

Decided 2026-11-24. Status: design decision, UI not built yet. Lists in the UI (concepts, topics, lists, courses, tracks, sources) offer sort by name, added date, last viewed, and relevance (kata decides from the tracks), each in direct or inverse order. Backend: added date and last viewed fields, and a relevance score from tracks. Review lists concepts as a tree the owner picks from, with these sorts; nothing is pre-selected.

## D43 Offline marking with a persistent queue

Decided 2026-11-24. Status: design decision, UI not built yet. Marks made while the server is down show at once with a "not synced" dot. They are stored in the extension's `storage.local`, so they survive browser close, restart and page switch, and are sent in order when the server answers. The connection indicator shows the count ("server down, 3 not synced"). A queued user mark wins over a trainer update (D9). To verify before the UI implementation milestone: whether the extension has an outbox today.

## D44 Settings page

Decided 2026-11-24. Status: design decision, UI not built yet. The settings page holds the connection and sign-out, the auto-scan site list with remove, jokes (on/off, frequency, source), and appearance. Server down disables Scan, Quiz and Generate. Signed out shows only the sign-in form.

## D45 Quiz question sources

Decided 2026-11-24. Status: design decision, UI not built yet. Reference sources give better quality than the model's own knowledge; the model only writes questions from fetched text. Pipeline: core fetches (not the model); allowlisted domains only; plain text kept; size cap; no link following; private and internal IP addresses blocked (SSRF). The model gets the text as marked data, with no tools, no keys and no access to marks. Its output is strict JSON (question, 3-4 choices, answer index, source quote); core rejects other shapes, URLs and over-long text. Grounding check: the quote must appear verbatim in the fetched text. The extension renders with `textContent` only. Model choice reuses the existing routing (a job type plus a setting). Questions are cached per source. Open: the owner's sign-off wording on the model setting.

## D46 Allowlist tiers for reference sources

Decided 2026-11-24. Status: design decision, UI not built yet. Tier 1, authoritative (RFCs and standards, official product docs, the owner's own materials): practice and exams. Tier 2, general reference (Wikipedia and similar, pinned revision, cached): practice only, labelled "general reference", never exams. Defaults are fixed in code. The owner adds domains per area in Settings; they land in Tier 2 with a warning and can be promoted by hand. Only free sources that read without an account; no paid or paywalled sources. Each default source's licence is checked before it is listed. Wikipedia (CC BY-SA) needs attribution and a link. Quotes are short, with a link; full text is never stored or republished.

## D47 Isolation of fetch and document reading

Decided 2026-11-24. Status: design decision, UI not built yet. Fetch and HTML run with no container: a separate low-privilege process, no secrets, SSRF block, caps. The PDF and image reader runs in a sandboxed container (no network, read-only filesystem, no keys, file in and text out), built with that reader.

## D48 Ladder belongs to dojo

Decided 2026-11-24. Status: design decision, UI not built yet. The review ladder belongs to dojo. Kata has no due concept and does no scheduling. At course generation a concept's mark picks its starting rung: new gives the first rung, known is left out, learning gives the default rung, which the owner can choose per course. Verified in dojo-kit (see the dojo-kit facts entry below): the starting rung is a dojo stage number, not "3 to 7 days". This corrects my earlier reading of D13.

## D49 Starting rung for learning concepts

Decided 2026-11-24. Status: design decision, UI not built yet. One setting on the Generate course screen, "Learning concepts start at" (default: the 3-7 day rung in the first draft; to be a dojo stage number per the facts entry below). It applies to the whole course. A single concept can be changed afterwards in the course preview.

## D50 Jokes and focus mode

Decided 2026-11-24. Status: design decision, UI not built yet. Jokes default ON, at most once per 2 hours, never during a quiz, while marking, or in focus mode. Settings: off switch, interval, and source (D24, D26, D28). Focus / Exam mode is one manual toggle button (floating card and panel). While on there are no jokes, no pin nudges, no inline quiz offers, no page highlights and no inline mark buttons (marking is off). Scanning still works and its results show only in the panel. The connection indicator stays. Focus mode ends by itself after a chosen time (default 3 hours) so it is not forgotten. Exam mode is not auto-detected. The "This is exam results" button records an exam result on the track goal (see D51). Open: option A (record only) or B (record plus per-domain proposals). Advice: build A first.

## D51 Exam results

Decided 2026-11-24. Status: design decision, UI not built yet. The owner wants option B: record the result (date, pass/fail, score) plus optional per-domain scores. Kata proposes moving concepts of weak domains from Known to Learning, and the owner confirms each one. Build order: record first, then per-domain proposals. This needs a mapping from exam domains to areas, topics or concepts. Where no mapping exists, the owner picks topics by hand. Open: where the domain list comes from.

## D52 One Summary button

Decided 2026-11-24. Status: design decision, UI not built yet. The floating card has ONE "Summary" button. Its view holds both the knowledge summary and the page text summary, each labelled. The glossary ban on a bare "Summary" applies to text that does not say which view it means.

## D53 Concepts and aliases

Decided 2026-11-24. Status: design decision, UI not built yet. A segment-level term that only combines two concepts is not a concept of its own. SYN and ACK stay separate concepts, because each is one flag and ACK recurs in every later segment. "SYN-ACK" and "Three-way handshake" are one concept, Three-way handshake. "SYN-ACK" is an alias: it highlights on the page and opens that concept. Consequence: SYN-ACK cannot be marked Known alone. Concept extraction merges aliases into one concept. This applies to the prototype sample, the glossary (term Alias) and the backend concept extraction.

Backend: today only topics have aliases (`topic_aliases`, `core/kata_core/storage/taxonomy.py`). The milestone adds concept aliases: a per-concept alias list (case-insensitive lookup, shared or private like topics). Extraction returns the canonical name plus alias words and merges them into the existing concept. The scan output carries the written word plus the concept id.

## D54 Concept identity is area, topic and name

Decided 2026-11-24. Status: design decision, UI not built yet. A concept is identified by area, topic and name together. The same word under a different area or topic is a different concept with its own mark. Scan first classifies the page into area and topic (candidates: the user's existing taxonomy, then new ones), then extracts concepts and resolves aliases within that area and topic. When the model cannot decide, the hover menu shows "Which one?" with the candidates, and the pick is remembered for that page's topic. The menu item "Not this meaning" reassigns a highlight to another concept and teaches the alias. Backend: unique key (area, topic, name); alias unique per (area, topic); page classification cached per page; classification is the first model step of a scan and needs an evaluation set. This supersedes "topic only groups" where identity is concerned: a topic still does not decide block state.

## D55 Prototype review round 1

Decided 2026-11-24. Status: design decision, UI not built yet. Colours, style and block order are approved. Changes: (a) state buttons are icons (Known, Learning, New) with a tooltip and an accessible label, everywhere. (b) The concept menu shows a one-line definition (generated at extraction); "Not this meaning" stays as an icon and shows only when a definition is present. (c) Blocks, borders and menus never shift or cover page text. (d) Pages are dynamic: the extension rescans on page change (mutation watch, debounced) and keeps marks by concept id. (e) Quiz questions must not contain or imply the answer. Generator rule: answer words and obvious derivations must not appear in the question stem, checked after grounding. (f) All actions are local: next to the clicked item, with no cursor travel across the screen; the list picker opens beside its button. (g) Spacing of dropdowns and menus is fixed everywhere, including Focus mode. (h) Scan result concept rows are at most 2 lines, with icon buttons. (i) The Review tree is collapsed by default with counts, except the area and topic of the open page; it has Collapse all and Expand all; clicking a concept never expands the tree. (j) Wrong items: "Delete" removes from data (a later scan may bring it back as New); "Ignore from now on" hides it, it is never detected again, and it is managed in a list in Settings with restore. Both apply to concepts and topics, with undo. (k) Scale to 1000+ concepts: a search box, state filter icons, and an "Only this page" filter.

## Concept aliases are unique per topic and owner

Decided 2026-11-24. Table `concept_aliases` (migration `core/migrations/0015_concept_model.sql`) holds alternative names of a concept, with the concept's `topic_id`. Lookup is case-insensitive. An alias is unique per topic and owner; a shared alias has no owner. `resolve_concept` (`core/kata_core/storage/concept_aliases.py`) maps a word to one concept of a topic: the caller's own match beats a shared one, and a label beats an alias. Reason: D53 merges an alias into one concept, so a word must resolve to one id within its topic.

## Concept identity is area, topic and name on the concept row

Decided 2026-11-24. The `concepts` table keeps the identity of a concept (D54): the name is `label`, the topic is `topic_id`, the area is the category of that topic, and the owner is `owner_user_id`. No migration moves the identity. Reason: a second identity table would hold the same three values twice.

## Concept definition, last view and ignore

Decided 2026-11-24. Migration 0015 adds `concepts.definition` (empty by default), `concepts.added_at` and `concepts.last_viewed_at`. The definition and the last-viewed time sit on the concept row, so every user who sees the concept sees the same values. Ignore is per user: table `concept_ignored` hides a concept from that user's lists and keeps its marks (D55). Hard delete removes a concept the caller owns, with its marks, aliases and ignore rows; a shared concept gives 403. Reason: D55 separates "Ignore from now on", which keeps data, from "Delete", which removes it.

## Sort fields and derived block state

Decided 2026-11-24. The sort fields of D42 are name, added date, last viewed and relevance, each `asc` or `desc`. A concept never viewed sorts as the oldest time. Relevance is the sum of `priority + 1` over the caller's active tracks whose modules cover the concept; paused and dropped tracks add nothing (`core/kata_core/storage/concept_rank.py`). The state of a block comes from its concepts' marks: all new or unmarked gives `new`, all learning gives `learning`, all known gives `known`, anything else gives `mixed`. A topic never decides a block state. Reason: the block state must follow the concepts a user marked, not the grouping.

## Topic data moves to concepts in migration 0016

Decided 2026-11-24. Migration `core/migrations/0016_topic_to_concept.sql` copies data only. Each topic with a known mark or an alias gets one concept with the topic's name, known topic marks become known concept marks, and topic aliases become concept aliases. The visibility rule of the topic code applies: a private row moves only for its owner. Every insert has an `ON CONFLICT` guard, so a rerun adds no rows. Topic tables and the topic routes stay. Reason: the copy lets the concept routes read the existing marks while the old routes keep working.

## dojo-kit facts (verified 2026-11-24)

Verified in the dojo-kit docs (audit, 2026-11-24). The default review ladder is 0, 1, 5, 10 and 30 days (5 stages; `DEFAULT_LADDER` in dojo-kit's `srs/mod.rs`, not in this repo; per-unit override via `srs.ladder`). Stages are numbered, not named. A unit counts as learned at stage 4 (dojo-kit's `docs/AUTHORING.md`, not in this repo). The known signal is the placement answer known or again (`ARCHITECTURE.md:37`, `applyPlacement`) and the session setting `knownDistinct`; there is no other known status. No separate exam question pool is documented: `examOnly` units and `poolAspects` topics are different features. Effect on D48 and D49: the starting rung at course generation is a dojo stage number, not "3 to 7 days". D35 exam support needs a dojo change or a kata-side exam flow.

## Scan merges aliases into one concept

Decided 2026-11-24. Status: design decision, implemented in M20. A word that the page uses for a concept already known under another name is an alias, not a second concept (D53). The extraction step returns the canonical name and the alias words, and merges them into the existing concept of that area and topic. The scan output carries the written word and the concept id. Reason: one concept has one mark, so "SYN-ACK" and "Three-way handshake" cannot disagree about whether the user knows them.

## Scan identity is area, topic and name, classified first

Decided 2026-11-24. Status: design decision, implemented in M20. The scan classifies each page into area and topic before it extracts concepts (D54). The candidates are the user's existing taxonomy first, then new names. The classification is cached per page, so a page is classified once and a rescan of the same page reuses the result. Aliases are resolved only inside the area and topic found by the classification. Reason: the same word in another area is another concept with its own mark, so resolution must not cross areas.

## Scan quality: evaluation set and pass bar

Decided 2026-11-24. Status: design decision, implemented in M20. The classification step has a fixed evaluation set of labelled pages and a pass bar that the run must meet before the classification is used for a page. The set and the bar live in the repository next to the scan tests, so a change to the classifier is checked against the same pages every time. Reason: a classifier that drifts without a test shows up first as wrong marks for the user.

## Rescan keeps marks by concept id

Decided 2026-11-24. Status: design decision, implemented in M20 (D55 item d). When the page changes, the extension runs a concept scan again and keeps every mark by concept id. A concept that disappears from the page keeps its mark; a concept that is new on the page starts as New. Reason: the mark belongs to the concept, not to the position of the word on the page.

## Teachable-content check before a concept is kept (D38)

Decided 2026-11-24. Status: design decision, implemented in M20. The extraction step drops a candidate that is not teachable content, such as a menu label, a navigation word or a line of page chrome, before the concept is stored. The check runs on the extraction output in core, not in the extension. Reason: a concept the user cannot learn from the page only fills the review list.

## "Which one?" and "Not this meaning" behaviour

Decided 2026-11-24. Status: design decision, implemented in M20 (D54, D55 item b). When the model cannot pick one concept for a highlight, the hover menu shows "Which one?" with the candidates. The user's pick is remembered for that page's topic, so the same page does not ask again. The menu item "Not this meaning" moves the highlight to another concept and records the alias, so the next scan of the same word picks the right concept. "Not this meaning" shows only when a definition is present (D55 item b). Reason: the choice is taught once and used by every later scan.

## Uploaded-file filter is out of scope for M20

Decided 2026-11-24. Status: scope decision. Filtering scanned content by an uploaded file is not part of M20. The scan works on the page the user is viewing only. Reason: the upload path has no design yet, and a filter on it would change the scan contract twice.
