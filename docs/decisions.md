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
- A cost cap is built into the core and spend is tracked per call, per user.
- Chat subscriptions and APIs are billed separately; subscription tokens must not be used in
  application code. The application uses API keys through its adapters.
- The cloud provider is chosen with tests on the real tasks and the provider research
  ([`research/benchmarks`](research/benchmarks)); the adapters keep this a
  configuration change.

## Secret scanner

Two layers behind a scanner interface. Client masking in the terminal session tool uses a
small dependency-free pattern list. The core runs gitleaks in stdin mode as a subprocess on
every outgoing text before any cloud call. TruffleHog is rejected (AGPL licence does not fit
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
- **Pre-commit secret check.** Runs gitleaks locally, so it does not depend on the core.
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

## Lesson check: worker job not wired into loop.py yet

The worker has a `lesson_check` job (`worker/kata_worker/lesson_check.py`) and `CoreClient.lesson_check`, but `worker/kata_worker/loop.py` does not dispatch it yet. Until it does, only the `POST /lesson-check` route runs lesson checks.

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
