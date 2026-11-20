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
- **Marks.** Milestone 0 marks at topic level; concept-level marks come in a later slice.
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
