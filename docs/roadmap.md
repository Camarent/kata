# Roadmap

Milestones are ordered by value. Each has a scope and success criteria. Dates are not
committed; the order is.

## Milestone 0: foundation and lesson scan (done)

**Scope.** Browser extension (side panel, content script, "I know this" button), a minimal
core (Python, FastAPI, Postgres, token login, job queue), a model worker that polls the core,
skill-list import, topic-level marks, a gates configuration (`tools/gates.json`).

**Success criteria (met).** Foundation, core, worker and end-to-end suites pass; the extension
builds and its tests pass; a decision record exists; `npm ci` works.

**Known gaps.** The extension has only been checked with stubs, never loaded in a real
browser. See [`backlog.md`](backlog.md).

## Milestone 1: make it real and portable

**Scope.** Develop from a clean clone on any machine: reproducible Postgres test setup, no
machine paths, CI with a database service, secrets scanning and a privacy check. Load the
extension in a real browser and run the lesson scan against a running core and a real local
model.

**Success criteria.** All gates pass from a clean clone with no files from the original
machine. The end-to-end test runs against a real stack. The extension works in a real
browser with a real sign-in.

## Milestone 2: knowledge model and retrieval

**Scope.** Concept-level marks, three states (known, learning, new) with evidence and dates,
embeddings with hybrid retrieval over the learner's knowledge base, retrieval-based lesson
check, a guided initial review screen.

**Success criteria.** Three-state lookup accuracy and abstain behaviour measured on the
benchmark suite ([`research/benchmarks`](research/benchmarks)); whole-lesson scan card within
30 seconds.

## Milestone 3: cloud path and cost control (done)

**Scope.** Cloud provider adapters, provider policy flags, a mandatory secret scanner before
every cloud call, per-user cost cap with warning, routing chains per task class.

**Success criteria.** No outgoing text that contains a detected secret reaches a cloud
provider. Spend is tracked per call and capped per user.

**Shipped.** Provider protocol with a local provider and an Anthropic adapter over httpx;
cloud policy flags per provider and task class; a pinned-rule secret scanner wrapped in a
guard that runs before every cloud call and before the cost cap; per-user daily spend in
micro-USD (`usage_daily`, `POST`/`GET /usage`) with a cap and a warning; `[routing]` chains
per task class tried in order. The Anthropic adapter is tested against a mock transport only.

**Known gaps.** No real-provider run has been made yet. See [`backlog.md`](backlog.md).

## Milestone 4: advice in the editor and terminal

**Scope.** Editor integration (an assistant over MCP and an own extension), the tracked
terminal session tool, intervention policy and journal (quiet mark, nudge, stop signal,
pre-commit secret check).

**Success criteria.** Every intervention type has a switch and a threshold; every firing is
journaled; a secret in a commit blocks the commit.

**Shipped.** Per-user journal (`GET /v1/journal`); intervention policy engine (`error`, `ok`,
`idle` events to `nudge`, `stop`, `quiet_mark`, from `[policy]`); device event ingest
(`POST /v1/events`, stored once per `event_id`) with message delivery; MCP server
(`POST /mcp`, two read tools, egress gate); git pre-commit and post-commit hooks in
`core/kata_device/` (`python -m kata_device hooks install`); `kata term` terminal tool in
`core/kata_term/`; editor extension in `editor/` (one `editor.save` event per save, quiet mark
as a diagnostic, hook installer command).

**Open.** A real editor run (the extension has only been checked with stubs and in tests); a
real MCP client; a real terminal test on the owner's PC; event retention (no expiry of stored
events yet).

## Milestone 5: practice courses and planning (done)

**Scope.** Gap to mini-course through the trainer tool with a two-way loop, triage of a
syllabus, time-boxed tracks sharing one time budget, decision points between tracks.

**Success criteria.** Results from the trainer update the knowledge model. A syllabus import
yields a per-module action plan that fits the time budget.

## Milestone 6: deployment on a VM (done)

**Scope.** Run kata on the owner's VM (Ubuntu Server LTS, 2 cores, 3 GB memory,
32 GB disk) with Docker, the private network client and no public access. Images for core and migrate, a compose
stack (core, migrate, Postgres, reverse proxy with TLS over the private network), a nightly encrypted
dump, a tested restore drill, a provisioning script and a runbook. Nothing waits for the VM:
everything is tested without it.

**Success criteria.** One documented command sequence turns a fresh Ubuntu Server VM with
Docker and the private network client into a running kata (core, migrate, Postgres, reverse proxy with TLS over
the private network). A deep health check passes. A nightly encrypted dump runs. The restore drill
(design 4.3 steps 3 to 5) is scripted and tested against a temporary Postgres.

**Shipped.** The runbook is in [`deployment.md`](deployment.md) (D17 to D25 in
`decisions.md`). The real VM run is still open in [`backlog.md`](backlog.md).

## Milestone 7 (skipped)

No scope recorded: `decisions.md` and the git history have no entry under M7. The numbering goes
from M6 to M10.

## Milestone 8 (skipped)

No scope recorded: `decisions.md` and the git history have no entry under M8.

## Milestone 9 (skipped)

No scope recorded: `decisions.md` and the git history have no entry under M9.

## Milestone 10: deploy images and ship script (done)

**Scope.** Build the kata image on the dev machine and ship finished images to a VM
over SSH; the VM builds nothing.

**Shipped.** `kata:<git short sha>` built from `deploy/compose.build.yaml`, checked, and shipped
over SSH (D25). Merged to master in `b3bf49d`, with pinned base, Postgres and Caddy digests in
`9faa97d`.

## Milestone 11: real trainer contract and local-model fixes (done)

**Scope.** Replace the assumed trainer JSON contract with the real `dojo` CLI, and fix what the
local model run showed.

**Shipped.** `DojoTrainerCli` runs the real `dojo` CLI without a shell; progress documents are
dojo-native, with a PATCH delta save and an import that writes no evidence; local-model fixes.
Merged to master in `282cba3`. Opt-in Haiku and local-model smoke harnesses are on master in
`4e3da45` and `5fbf115`. The real dojo and real model runs are open in
[`backlog.md`](backlog.md).

## Milestone 12: serve courses and bridge progress through the extension (done)

**Scope.** Serve built courses over HTTP by signed open links, and bridge dojo progress saves
through the extension (`window.claude` stub, split parts reassembled in the bridge, no core
migration).

**Shipped.** Merged to master. The open-link signer, course route, open endpoint, progress round
trip, side panel open action and the bridge content script are on master
(`core/kata_core/trainer/open_link.py`, `core/kata_core/api/routes/course_serve.py`). Decisions:
"Open-link tokens are HMAC-SHA256 signed", "Course bridge design" in `decisions.md`.

## Milestone 13: real dojo contract corrections (done)

**Scope.** Fix the trainer adapter to the real `dojo` CLI: an `init` step, one unit, and
warnings that never fail a build.

**Shipped.** Artifact keys are relative to the course folder, so the root page is served. Decision:
"Real dojo contract corrections (M13)"; its id rule was corrected by M14.

## Milestone 14: real dojo contract corrections, part 2 (done)

**Scope.** Correct the remaining dojo contract points found by the real CLI run.

**Shipped.** `next-id` takes the id prefix (the unit name without `-`), and ids are `<prefix>-<n>`.
Decision: "Real dojo contract corrections, part 2 (M14)" in `decisions.md`.

## Milestone 15: extension has no build-time server config (done)

**Scope.** Remove the fixed core address from the extension build.

**Shipped.** The build has no fixed host; the user types the server URL in the side panel, and the
origin is requested at sign-in. `KATA_EXTENSION_BASE_URL` is removed. Decision: "Extension has no
build-time server config (M15)" in `decisions.md`.

## Milestone 16: course limit and unique names (done)

**Scope.** Limit courses per user and make course names unique per user; the side panel lists,
creates and deletes courses.

**Shipped.** `[trainer] max_courses_per_user` (default 10 in `config/kata.example.toml`; 0 means
unlimited) is enforced by `POST /v1/courses`. Names are unique per user. M26 config keys (`[models]`, `[provider_openai]`, `vision`) add no course behaviour. Decisions: "Course limit
default lives in the example config (M16)" and "Course limit and unique names (M16)".

## Milestone 17: local-first routing (done)

**Scope.** Try local models before cloud, and refuse jobs that need the cloud when no cloud
token is set.

**Shipped.** Default chain is `local,anthropic`; cloud turns on by token alone. Jobs that need the
cloud are refused with 409 `needs_cloud` before they are queued. Decisions: "Routing defaults are
local first, cloud by token (M17)" and "Needs-cloud jobs are refused with 409 before queueing
(M17)". The local capability audit on the PC is still open in [`backlog.md`](backlog.md).

## Milestone 18: local models through a worker on the GPU machine (done)

**Scope.** Run local models on the user's GPU machine and control them from the client.

**Shipped.** One worker program runs on the GPU machine next to Ollama and pulls jobs from core over
outbound HTTP; control jobs `modelhost.up`, `modelhost.use`, `modelhost.measure` and
`modelhost.status` go through the same job queue. The worker runs as the owning user, never as
root, and takes a fixed allow-list of subcommands. Decision: "Local models through a worker on the
user's GPU machine (M18)" in `decisions.md`.

## Milestone 19: concept model (in progress)

**Scope.** Area > Topic > Concept identity and the per-user data the redesigned UI reads:

- Area, topic and concept identity unique on (area, topic, name) (D54); alias table (D53);
  concept definition line (D55).
- Per-user mark new, learning or known, keyed by concept id; block state derived from concepts.
- Added date, last viewed and relevance fields for sorts (D42).
- Ignored list and hard delete (D55).
- Migrate today's `topic_aliases` and block marks. API and tests only.

## Milestone 20: scan (shipped)

**Scope.** Page classification, concept extraction, aliases, the "Which one?" choice and dynamic
rescan (D53, D54, D55). Shipped:

- Job kinds `scan.classify` and `scan.extract`, with core output hooks that rewrite the job output.
- Routes `GET /scan/classification`, `POST /scan/choice`, `POST /scan/reassign` and `GET /scan/overview`.
- Page classification cached per page; the remembered "Which one?" pick per page topic.
- Aliases merged into one concept; concept identity (area, topic, name) with classification first (D53, D54).
- Teachable-content check before a concept is kept (D38).
- Rescan on page change keeps marks by concept id (D55 item d).
- Extension concept scan and rescan by concept id; the old tag job and the old extension scan keep working.
- Classification evaluation set and pass bar.
- Out of scope: uploaded-file filter.

## Milestone 21: learn (shipped)

**Scope.** Lists, tracks (D11 to D16) and courses in the redesigned UI and API (D7, D8, D14, D34,
D35, D48, D49). Shipped:

- Named concept lists: create, rename, delete, add and remove concepts, add a topic, generate a
  course from a list; the list is kept (migration 0019; routes under `/v1/lists`, D7, D8, D34).
- Track goals with sources, progress, velocity and pace, and a list of the open concepts of a goal
  (migration 0020; routes under `/v1/tracks/{id}/goals`, D11 to D15).
- Course regenerate replaces the course in place with carry-over preview and version bump
  (migration 0021; D35).
- Course start rung as a dojo ladder stage: 0 for new, the course `learning_rung` for learning,
  left out when known; stage 4 is learned (D48, D49).
- Reading PDF pages and images (D16) is built in M23: a sandboxed reader, shipped disabled.

## Milestone 22: quiz and exam results (shipped)

**Scope.** Quizzes in kata (quiz pool D45 to D47, answers kept out of the stem D55 item e). Dojo
course exams stay in dojo; kata imports their results with a confirm step (D35, D58). Exam domain
mapping (D51) is deferred. Shipped:

- Quiz source request `POST /quiz/sources` for an allowlisted URL; job kinds `quiz.fetch` and
  `quiz.generate`, with a grounding check and strict JSON output.
- Allowlist with tier 1 and tier 2 sources; each source records its licence.
- Mini quiz `GET /quiz/mini` with at most 5 questions, no answer index, and source, tier and licence.
- Answer check `POST /quiz/answer` in core: a correct answer moves New to Learning only; Known is
  never set there.
- Exam result import with a confirm step; a confirmed result marks Known and sends the dojo
  placement answer (`placement_known`).

Success criteria:

- `check-all.sh --py` green.
- An allowlist miss, a non-https URL, a private address or an over-long text is refused.
- A question whose quote is not in the fetched text, or whose stem holds an answer word, is dropped.
- The client never receives an answer index, and no exam result marks a concept Known without confirm.
- Open for the owner: the licence rows in `decisions.md`, and the model setting wording.

## Milestone 23: jobs (shipped)

**Scope.** Summary, jokes, and PDF and image reading as jobs. Shipped:

- Page summary cache per `(url, text_sha256)`, job `page.summary` (D16 summary path).
- Joke fetch as the core-only job `jokes.fetch`: server-side source list, hardened fetch, plain-text
  sanitiser, cache, `GET /jokes/next` and `GET /jokes/sources` (D24, D26 to D28, D30, D50).
- Document reader `reader.extract` in a sandbox, text only to core (D47); shipped disabled.

Not in M23: the offline fallback list and the joke UI are M25.

## Milestone 24: review and sync (shipped)

**Scope.** Review tree, name search, state filters, "Only this page", shared concept sort, concept list,
the offline mark queue, and the OpenAPI export. Shipped:

- Review tree `GET /v1/review/tree` (areas > topics with new, learning and known counts) and concept list
  `GET /v1/review/concepts`, both filtered by name, state and `ids`; the list also sorts (see
  [`decisions.md`](decisions.md), "Review API and offline mark queue").
- Offline mark queue in the extension: marks made while the core is unreachable wait under `kata.markQueue`
  and flush in order; the panel reads the pending count.
- OpenAPI export of the core schema to `docs/openapi.json`, with a test that fails when it drifts.

## Milestone 25: UI implementation (partial)

**Scope.** Build the extension UI on the backend from M19 to M24: 48 approved screens (D1 to D58) on
the panel tab, floating card, settings, page overlay and course page. The approved design notes
(decisions, glossary, inventory summary) are in [`design/extension-ui.md`](design/extension-ui.md),
section 9; the decision record is in [`decisions.md`](decisions.md). The UI modules are listed in
[`modules/extension.md`](modules/extension.md). The old mockups were removed.

Partial: the UI modules are built and unit-tested, but not all are mounted in the running extension.
- Mounted: the card host (`extension/src/cardHost.ts`, mounted by `content.ts`) with its page-changed
  overlay (`ui/overlay/pageChanged.ts`), the focus confirm (`ui/card/focus.ts`) and the joke cloud
  (`ui/card/jokeCloud.ts`); the pin (`ui/card/pin.ts`), the panel CSS and the card CSS. The panel tab
  screens and their router (`ui/panel/router.ts`) are mounted in `extension/src/sidepanel.ts`.
  Courses and tracks load from the backend (`panel:courses`, `panel:tracks`, wired in
  `extension/src/sidepanelBoot.ts`). Scan results still show placeholder rows (`rows: []` in
  `sidepanel.ts`).
- Unmounted, pending owner decision (no importer outside its group): the page overlays
  `extension/src/ui/overlay/hlMenu.ts` (hover menu), `whichOne.ts`, `blockMenu.ts`, `imageMenu.ts`,
  `listPicker.ts`, `quizPin.ts`; the exam screens `extension/src/ui/panel/examRun.ts` and
  `extension/src/ui/panel/examResult.ts`; the course page `extension/src/ui/panel/coursePage.ts`.
- Unwired track handlers (no-op stubs in `extension/src/sidepanelBoot.ts`): `onAddSource` and `onQuiz` (trackDetail), `onCreate` (trackCreate). Follow-ups, not yet wired.
- Follow-ups are in `.notes/later.md` (local notes, not in the repo) and must land before M26.

## Later

Video transcripts, a phone web app, Chrome packaging, passkeys, deeper terminal tracking,
exam mode hardening, a public path for single pages.

Exam mode recorder: a silent recorder of the owner's exam answers. Design step first (no code until
the design is approved); the milestone comes after M26.

Extension UI: design v2 is approved (2026-11-24; navigation, settings, auto-scan and block states;
see [`design/extension-ui.md`](design/extension-ui.md) and [`decisions.md`](decisions.md)). The UI
implementation is milestone 25.

## Out of scope for now

Voice; a public service (self sign-up, exposure to the public internet); native mobile apps;
publishing any course material; a global review calendar.
