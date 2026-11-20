# Architecture

System-level design. `ARCHITECTURE.md` (upper case) is the generated map of the code; this
document is the intended design. Status labels: **Decided**, **Assumed** (proposal to
confirm), **Open**. Stack and decision records are in [`../decisions.md`](../decisions.md).

## Deployment

- A few users, each with a separate private profile. Data is private from the application and
  from other users, not from whoever administers the server. No per-user encryption. No
  public service.
- The core runs on a machine the administrator owns and is the single source of truth. It sits
  behind a private mesh VPN with nothing exposed to the public internet. (Decided)
- Authentication: a revocable token per user and per device, issued from a one-time enrolment
  code created by the administrator. No self sign-up. A further device is added only with a
  confirmation from a full-scope device of the same user; a narrow-scope device cannot enrol
  others. The identity layer stays replaceable. (Decided)
- Local models run on users' own GPU machines as **model workers**. A worker connects out to
  the core, asks for work with a long HTTP request, runs it on its local model and posts the
  answer back. Nothing connects in to the worker. (Decided)

## Components

- **Core service**: knowledge model, taxonomy, ingestion, index, model router, secret
  scanner, intervention policy and journal, sync, authentication, HTTP and SSE API, MCP server.
- **Browser extension**: side panel (summary, highlighting, new/known marks, questions,
  "I know this"); a content script reads the page text. WebExtension, Manifest V3.
- **Editor integration**: an assistant connected to the core over MCP, and an own extension
  for typing-time behaviour (quiet marks, nudges, a stop signal, a pre-commit check).
- **Terminal session tool**: a command the user starts per session; wraps a local shell or SSH
  session and sends the masked command, exit code and time. Nothing runs in terminals the user
  did not start this way.
- **Model worker**: polls the core, runs jobs on a local model through an OpenAI-compatible
  endpoint.
- **Phone web app** (later, Assumed): questions, practice, "send a link to the knowledge base".

All clients reach the same data through the core API.

## Knowledge model

- Unit: a concept with one of three states (known, learning, new) over an internal score,
  an evidence source (test, reading, code, button) and a date.
- Taxonomy: a tree of categories and topics seeded from programs (syllabi, slide outlines,
  exam guides) and extended from materials. The shared tree is read-only for users and curated
  by the administrator; each user has a private overlay (own topics, aliases). (Decided)
- Cold start: a skill list as the starting hypothesis, refined by tests and use. (Decided)
- Scheduling of repetition stays inside the trainer tool; the core reads its results and uses
  no scheduling library in version 1. (Assumed)

## Content ingestion

- Sources: course pages in the browser, PDF and slide files, articles and documentation.
  Video transcripts later.
- Access rules: open public material may be fetched, respecting robots.txt and site terms.
  Pages of a course platform are read only when the user has them open, never crawled. Study
  material is stored on the core host and never enters the repository. Chunks are shared by
  content hash; the link from a user to a chunk is private. (Decided)

## AI layer

- Task classes. **L**: small local model (tagging, command classification, hint text).
  **M**: larger local on demand, or cloud (summary, explanation, questions over many files).
  **H**: large cloud (generating a mini-course, hard questions, batch analysis).
- The new/known label and the decision to show a nudge are computed in code, not by a model.
- Routing: one provider chain per task class per user. The first available provider wins: the
  user's own worker if connected, otherwise cloud. No generative model runs on the core host.
  Code goes to cloud only after an opt-in per repository. (Decided)
- Tutor behaviour: explanations can switch language on request while technical terms stay in
  English; silence on graded pages. Detection of graded pages is Assumed.

## Data, privacy, security

- Sync: the core is the source of truth; clients keep a cache and a local event queue.
- Retention: detailed history of commands and read pages for 90 days, then compressed to
  summaries. Deletion at any level: one page, one source, everything.
- Terminal commands are stored with tokens and passwords masked by pattern. Masking runs on
  the client before anything is sent.
- A secret scanner checks every outgoing text before any cloud call. A chunk or file with a
  detected secret stays local and is shown as "not sent to cloud".
- Each provider has a policy flag (may train on requests, jurisdiction, local); sensitive
  content goes only to providers whose policy allows it.

## Non-functional requirements

- Local actions up to 300 ms; first highlights of a lesson scan up to 2 s; whole lesson scan
  card up to 30 s (the summary has no deadline). (Decided)
- If the core or a model is unavailable, clients show the cache and model-free hints with an
  "offline" mark. Work is never blocked.
- Interventions never hard-block, except that a secret found in a commit blocks it. Every
  intervention type has a switch and a threshold; every firing is journaled with the learner's
  feedback, and thresholds are tuned per user from that journal.
- No dependence on an external hosted service.

## Trainer integration

A separate trainer tool builds a single-page trainer from a course folder, with spaced
repetition. The loop is two-way: kata generates items from gaps, the trainer builds, results
return into the knowledge model through a storage adapter that saves progress via the core
API. Trainer pages are served on their own address with a narrower cookie. kata owns the
taxonomy and maps it to the trainer's flat topic tags.

Further detail: [`overview.md`](overview.md) (milestone 0 design).
