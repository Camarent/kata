# kata: design overview

## 1. Purpose

kata is a self-hosted learning companion. It helps each of a small number of users learn a technical field quickly by building on what they already know. It keeps a model of what each user knows, reads the lesson page the user has open, and shows in about 30 seconds which parts of the lesson are new. Later versions add advice inside the user's own projects and short practice courses built from knowledge gaps.

The aim is a companion that feels responsive and context-aware. It assists the learner and does not replace them. Each user has a separate private profile, and the repository contains code only: no study material and no personal data. License: MIT.

## 2. Milestone 0

Milestone 0 delivers one scenario end to end: the lesson scan.

### What it does

- A browser extension (WebExtension, Manifest V3, TypeScript; Firefox first, Chrome later from the same code) scans the open lesson page. Within about 30 seconds it shows which topic blocks the user lacks.
- The result is a card in a side panel plus in-page highlighting: new blocks strong, known blocks muted.
- Each block has an "I know this" button. Pressing it sets the block's topic to known.
- Marks are at topic level only.

### Initial review

The user marks what they already know, using an imported list file. That list becomes the user's starting skill list. After that, the "I know this" button and normal use refine it.

### Tagging

Topic-level labels come from a local model. A minimal worker runs next to that model and polls the core over HTTP on the loopback interface. The core decides in code whether a topic is new or known for a given user, from the topic label and the user's skill list. The model only chooses the topic.

### Core

- A minimal Python/FastAPI core exposing an HTTP API.
- Postgres for storage.
- Token login. Several users, each with a separate profile.

### Not in Milestone 0

- Embeddings and semantic retrieval
- VPN or any remote-access setup
- A cloud model path
- An MCP interface
- A terminal tool
- A VS Code extension
- A phone PWA
- Concept-level marks

## 3. Architecture and stack decisions relevant to Milestone 0

**Core.** Python with FastAPI. It is the single source of truth for the knowledge model, taxonomy and settings. Clients talk to it only through its HTTP API, so other clients can be added later without changing the core.

**Clients.** TypeScript. The browser extension is the only client in Milestone 0. A client never waits on the core for long: it uses a short timeout and then falls back to its cache, and it shows a small "offline" mark when it does.

**Storage.** Postgres, reached through a storage interface (a repository layer) so the backend can change. Every table that holds personal data carries a user id. The taxonomy of categories and topics holds no personal data and is shared. Each user can add private topics and aliases without changing the shared taxonomy.

**Authentication.** A revocable token per user and per device, issued from a one-time enrolment code created by the administrator. There is no self sign-up. The authentication layer is kept replaceable so other login methods can be added later.

**Per-user data separation.** Knowledge model, notes and settings are private to each user and not visible to other users through the application. There is no per-user encryption: the person who runs the system can access the database. Deletion works per user.

**Worker pull model.** A model worker connects out to the core and asks for work with a long-lived HTTP request, runs it on its local model, and posts the answer back. Nothing connects in to the worker, and the core needs no worker address. The same design works on loopback in Milestone 0 and across machines later. Each user's worker serves that user only. The worker owns the model runtime and its resources; the core only sends requests. Background scans yield to any foreground request.

**Local models.** Any local runtime reachable through an OpenAI-compatible HTTP endpoint is supported through one adapter. A small resident model handles page scan and topic tagging; larger models are for later, on-demand tasks.

**Config-driven values.** Thresholds, timeouts, provider choices and similar settings come from a configuration file, not from literals in code. Defaults are documented in the README.

**No external hosted service.** The core and the worker run on machines the user controls. Nothing in Milestone 0 depends on a third-party service, and clients keep working from cache when the core is unreachable.

**Responsiveness targets.** Local actions up to 300 ms. First highlights of a lesson scan up to 2 s. The whole lesson card up to 30 s. A summary, when added, has no deadline.

**Access rules for content.** Pages are read only when the user has them open in the browser; they are never crawled. The scan starts on a click, or automatically on sites the user has added to a private list of URL masks.

## 4. Later versions

- Concept-level knowledge marks and evidence from tests and the user's own code
- Embeddings and hybrid retrieval over ingested material (PDF, slides, articles)
- Cloud model providers behind adapters, with a mandatory secret scanner and a per-user cost cap
- An MCP interface so coding assistants can read the knowledge model
- A VS Code extension for project advice, quiet marks, nudges and a pre-commit secret check
- An opt-in terminal session tool that records masked commands and offers nudges on repeated errors
- Short practice courses generated from gaps, built in an optional external trainer, with results returned into the knowledge model
- Remote access over a private network with no public exposure
- Chrome support, then a phone PWA
- Video transcripts, passkeys and a public path for single pages

Out of scope: voice, a public multi-tenant service, native mobile apps and any redistribution of course material.
