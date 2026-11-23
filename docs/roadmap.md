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

## Milestone 6: deployment on the web VM (done)

**Scope.** Run kata on the owner's Proxmox VM `web` (Ubuntu Server LTS, 2 cores, 3 GB memory,
32 GB disk) with Docker, Tailscale and no public access. Images for core and migrate, a compose
stack (core, migrate, Postgres, reverse proxy with TLS over the tailnet), a nightly encrypted
dump, a tested restore drill, a provisioning script and a runbook. Nothing waits for the VM:
everything is tested without it.

**Success criteria.** One documented command sequence turns a fresh Ubuntu Server VM with
Docker and Tailscale into a running kata (core, migrate, Postgres, reverse proxy with TLS over
the tailnet). A deep health check passes. A nightly encrypted dump runs. The restore drill
(design 4.3 steps 3 to 5) is scripted and tested against a temporary Postgres.

**Shipped.** The runbook is in [`deployment.md`](deployment.md) (D17 to D25 in
`decisions.md`). The real VM run is still open in [`backlog.md`](backlog.md).

## Milestone 7

No scope recorded: `decisions.md` and the git history have no entry under M7. The numbering goes
from M6 to M10.

## Milestone 8

No scope recorded: `decisions.md` and the git history have no entry under M8.

## Milestone 9

No scope recorded: `decisions.md` and the git history have no entry under M9.

## Milestone 10: deploy images and ship script (done)

**Scope.** Build the kata image on the dev machine and ship finished images to the web VM
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

## Milestone 12: serve courses and bridge progress through the extension (not merged yet)

**Scope.** Serve built courses over HTTP by signed open links, and bridge dojo progress saves
through the extension (`window.claude` stub, split parts reassembled in the bridge, no core
migration).

**Status.** Built on `stage/m12`, not on master yet: the open-link signer, course route,
open endpoint, progress round trip, side panel open action and the bridge content script are
on the stage branch. Done once merged.

## Later

Video transcripts, a phone web app, Chrome packaging, passkeys, deeper terminal tracking,
exam mode hardening, a public path for single pages.

## Out of scope for now

Voice; a public service (self sign-up, exposure to the public internet); native mobile apps;
publishing any course material; a global review calendar.
