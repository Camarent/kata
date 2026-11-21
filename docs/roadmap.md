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

## Milestone 5: practice courses and planning

**Scope.** Gap to mini-course through the trainer tool with a two-way loop, triage of a
syllabus, time-boxed tracks sharing one time budget, decision points between tracks.

**Success criteria.** Results from the trainer update the knowledge model. A syllabus import
yields a per-module action plan that fits the time budget.

## Later

Video transcripts, a phone web app, Chrome packaging, passkeys, deeper terminal tracking,
exam mode hardening, a public path for single pages.

## Out of scope for now

Voice; a public service (self sign-up, exposure to the public internet); native mobile apps;
publishing any course material; a global review calendar.
