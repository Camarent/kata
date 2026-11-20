# Detailed architecture

Benchmark figures cited here are in [`../research/benchmarks/RESULTS.md`](../research/benchmarks/RESULTS.md).

Detailed design behind [`architecture.md`](architecture.md): scope and quality targets, deployment views, components, interfaces, data model, key flows, model orchestration, failure behaviour, security, operations, testing, third-party parts and the build order. Status labels: Decided, Assumed, Open, Verify.

### 1. Scope, goals, non-goals, quality targets

#### 1.1 Scope

A learning companion for a few users (a small group): a central core with a browser extension, an editor extension, a terminal session tool, a phone page, a trainer integration (the trainer tool) and model workers.

#### 1.2 Goals

| # | Goal | Source |
|---|---|---|
| G1 | Lesson scan: in about 30 seconds the user sees what a lesson is about and which blocks are new | S1 |
| G2 | One knowledge model per user, fed by button, tests, own code, trainer results | See architecture.md |
| G3 | Advice in the editor and terminal that never blocks work (one exception: a secret in a commit) | Interventions |
| G4 | Gaps become a short practice course in the trainer; results return | S4 Trainer return path |
| G5 | Several users with private profiles on one core | Users |
| G6 | The core can move between machines by dump and restore | See architecture.md |
| G7 | Works degraded when the core, a worker or the cloud is absent | Offline behavior |

#### 1.3 Non-goals

| Non-goal | Source |
|---|---|
| A public service: self sign-up, exposure to the public internet, more than a small group of users | See architecture.md |
| A generative model on the core host | See architecture.md |
| High availability, horizontal scaling, more than one `kata-core` process, rolling upgrades with mixed versions | proposed |
| Voice, native phone apps, a global review calendar, publishing course material | See architecture.md |
| Client-side label computation, offline model inference on phone or in the browser | proposed; `landscape` risk 3 |
| Privacy from whoever runs the core host; per-user encryption | See architecture.md |
| An always-on hook in the shell profile; tracking of terminals the user did not start through `kata term` | See architecture.md |
| Storing prompts or model outputs in logs | proposed |
| Crawling course platforms | See architecture.md |
| Dashboards and a metrics server in version 1 | proposed (12.4) |

#### 1.4 Quality targets

| Target | Value | Measured from, to | How it is met | Status |
|---|---|---|---|---|
| Local action | 300 ms | user action to visible result, for: cached card and marks, a button press, a stop-signal pattern hit, opening a panel | no network on the path: client cache, optimistic update, local pattern lists | proposed mechanism |
| First highlights of a lesson scan | 2 s, small model | scan start to the first block marks on the page | cached annotations by chunk hash show at once; visible blocks are tagged first by class L and each finished block is streamed and marked; on sites the user added the scan starts on page open (prefetch) | unmeasured end to end; class L alone: first token 0.2 s, about 0.4 s per block |
| Whole lesson scan | 30 s | scan start to the `tags_done` stream event: every block has a label. The 30 s counts the card only (all blocks tagged, counts and top gaps). The summary is not inside the 30 s; it appears when ready and has no deadline | topic-only tagging (the benchmarked task), two class L slots, nothing else generating on the GPU while tagging runs (the summary starts after `tags_done`), annotation cache by chunk hash | benchmark for the chosen configuration (class L model, two slots, lesson of 55 blocks): 21.1 s (benchmark results: parallel slots), so about 9 s of margin for extraction and network; single runs, and differences under about 25 percent are noise there. Confirmed or refuted by the first spike (section 15, S-1) |
| Client wait on the core | never blocks | request start to fallback | 1.5 s to the first response byte for interactive calls, then cache; terminal session tool 1 s in the background; pre-commit 5 s total | proposed values |
| Privacy | personal data private from the app and from other users, not from whoever runs the core host; no per-user encryption | n/a | database row rules plus a storage interface that cannot be used without a user (section 7.2); content-free logs; no admin read path in the product | decided |
| Offline | clients keep working | n/a | cache, model-free hints with an "offline" mark, local event queue | section 10 |

Scope of the two scan targets: they are stated for the reference GPU with the chosen class L model and two slots. Another user's smaller GPU and the cloud path have no measurement; for them the targets are goals, not claims. The summary and the first text of an explanation have no target of their own. Production measurement: clients record the perceived times and send them as content-free `client.timing` events (section 12.4).

### 2. Principles

1. One core, many thin clients; clients talk to the core only through the versioned API.
2. A client never waits on the core: short timeout, then cache; events queue locally.
3. Every private row carries a user id and is unreachable through the app without that user's context; this is enforced in the database, not by convention. It protects users from the app and from each other, not from whoever runs the core host.
4. Relocatable: Postgres is the only durable store, everything beside it is a cache that can be rebuilt, and every address, path, timeout and model name comes from configuration.
5. Nothing is scanned or stored automatically except on sites the user added; everywhere else a scan needs a click. A "site the user added" is a URL mask the user entered (5.3), so one entry can cover a whole platform.
6. Models propose topics and concepts; code decides labels, states and interventions.
7. Nothing reaches a cloud provider without passing one egress gate: policy flags, secret scan, cost check.
8. A model worker is optional and may vanish at any moment; absence is a normal state, not an error.
9. Nothing blocks the user except a secret in a commit.
10. Every model task has a defined degraded behaviour (a model-free result, a wait, or a skip, section 9.3) and a regression test that needs no GPU.

### 3. System context

#### 3.1 Actors

| Actor | Role |
|---|---|
| User | Learner with a private profile; owns devices and optionally one model worker |
| Admin | A user who also creates users, issues enrolment codes, sets cost caps, curates the shared taxonomy. Has no access to other users' private data through the product; as the person who runs the core host, can reach the machine and its data |
| AI coding assistant | External MCP client acting for one user in the editor; has tools of its own and its own cloud provider |

#### 3.2 Devices and what runs on them

| Device | Runs | Notes |
|---|---|---|
| Workstation with GPU | browser extension, editor extension, `kata` device tool (terminal sessions, git hooks), minimal model worker (polls the core over loopback); in M0 also the core and Postgres | See architecture.md |
| Home server (no GPU) | core (with its job runner), kata's own Postgres with pgvector, reverse proxy; also unrelated services | See architecture.md |
| Other user's PC with GPU | same clients, own model worker | See architecture.md |
| Device without GPU (phone, tablet, PC) | phone page or extension; cloud for models | See architecture.md |
| Remote machine reached by SSH (course VM) | nothing installed permanently, no token; seen only inside a `kata term` session the user starts (section 5.4) | S3; |

#### 3.3 External systems

| System | Used for | Direction |
|---|---|---|
| Cloud model providers (API key) | tagging, explanation, generation for users without a worker, or as a later chain step where the user allows it | core out |
| The assistant's own cloud provider | receives whatever the MCP client forwards; unknown to the core | assistant out (6.4) |
| Course platform and other web pages | content read from the open tab by the extension; never fetched by the core for restricted pages | browser only |
| Open web pages | fetched by the core on request (articles, docs) | core out |
| Mesh VPN | the only network path to the core in the target deployment | all clients |
| the trainer tool | trainer build tool and runtime, a separate repository | bundled binary, hosted pages |
| Public code repository and CI | code only; lint, tests, secret scan, licence check | n/a |

### 4. Deployment views

#### 4.1 M0: the workstation is everything

| Part | Where | Network |
|---|---|---|
| Postgres, a container used only by kata (no pgvector needed yet) | workstation | container network only |
| `kata-core` | container on the workstation | published on loopback only |
| `kata-migrate` | one-shot container before core start | container network |
| Nightly dump | host timer on the workstation, encrypted file in a local directory | none |
| Browser extension | workstation browser | loopback to the core |
| Model path | a minimal `kata-worker` on the workstation with one class L local model; it polls the core over loopback (pull link, 6.3), descriptor flag `trusted`, no egress gate | worker to core, outbound on loopback |

Not in M0: VPN, reverse proxy, the full worker daemon (class M, model swap, idle unload, availability switch, modes), job runner, embeddings, cloud path. Token login and row rules are on from the first day, also on loopback, so the move changes no client logic.

#### 4.2 Target

| Part | Where | Network |
|---|---|---|
| Reverse proxy, TLS, two names: one for the API and app pages, one for trainer pages | server | mesh VPN interface only |
| `kata-core`, `kata-migrate` | containers on the server | behind the proxy |
| Postgres with pgvector in a container used only by kata | server | container network only |
| Backup: nightly dump, tombstone file (12.2) | external disk plus a second location (open) | local |
| Model worker (daemon, model endpoints, later the batch engine) | each user's GPU machine | only outbound HTTP to the core: registers, polls for work, posts results (pull link,; section 6.3); nothing connects to it, with or without a VPN |
| Extension, editor extension, device tool | each user's computers | VPN to the core |
| Phone page | phone browser, installed to the home screen | VPN to the core |
| Remote SSH machine | no kata part | SSH out from the user's terminal, started by `kata term` |
| Cloud providers | internet | outbound from the core only |

Notes:

- A dedicated Postgres container refines "kata gets its own Postgres database and role": it keeps kata off the upgrade cycle and the superuser of the unrelated services on the same host. Proposed.
- Proxy settings that the design relies on: no response buffering on stream routes; idle timeout longer than the stream keep-alive (streams send a comment line every 15 s) and longer than the worker long-poll timeout (25 s proposed; give worker routes 60 s, proposed); upload size limit equal to the core's; both names only on the VPN interface.
- TLS is required in the target view: the phone page needs a secure context for its service worker. The certificate source depends on the VPN product.

#### 4.3 Relocation procedure (workstation to server; also the restore drill)

Preconditions: same Postgres major version and same pgvector version on both hosts; the same core image tag; a configuration file for the new host.

1. New host: install the container runtime, the Postgres container, the kata database and roles, the configuration and secret files, and (target only) the proxy, VPN and certificate.
2. Old host: switch the core to maintenance mode. API answers `503` with code `maintenance`; clients fall back to cache and queue events within their bounds (6.2). Running jobs stop at their next checkpoint.
3. Old host: dump the kata database in custom format, encrypted like every backup.
4. New host: restore the dump; replay the tombstone file (12.2); run `kata-migrate --check` (schema version equals the image's expected version).
5. New host: run the verify command: content-free row counts per table compared with counts taken before the dump; the row-rule catalogue test (section 7.2) must pass.
6. New host: start the core; the deep health check must pass (database, scanner binary, trainer binary, embedding model present).
7. Switch the address. With a VPN name: repoint the name, clients change nothing. From the M0 loopback address: each client and the worker change one setting, `core_url`. This step happens on the clients.
8. Old host: keep the stopped database for a fixed number of days, then wipe it.

What moves: the database dump, the tombstone file and the configuration with its secret files (provider keys). What does not move and is rebuilt: model file caches, the embedding model cache. Bearer device tokens stay valid because their hashes are in the database; web sessions (cookies) are bound to a name and enrol again if the name changes.

Failure branches:

- Before step 7: the old host leaves maintenance mode and continues; nothing was changed on it.
- After step 7: clients may already have written to the new host. The old host may be started again only after a reverse move (steps 2 to 6 from the new host to the old one). Starting the old host from its own stopped database would split the data and is forbidden by the procedure; its core refuses to start while a "moved away" marker row is present.

### 5. Components

#### 5.1 Core modules

One Python package. A module depends only on modules named in its "depends on" cell (downward, or sideways where listed).

| Module | Responsibility | Owns (tables, section 7) | Depends on |
|---|---|---|---|
| `ops` | configuration, logging, health, maintenance mode, the `doctor` report | none | none |
| `storage` | repository layer, user scope, shared scope, system scope, migrations | all tables (access), `schema_meta` | `ops` |
| `auth` | users, enrolment codes, devices, tokens and scopes, web sessions, pending confirmations | `app_user`, `enrolment_code`, `device`, `device_token`, `pending_action` | `storage` |
| `jobs` | job table, one runner loop, checkpoints; a registry: other modules register a handler per job kind | `job` | `storage` |
| `journal` | record of every intervention and egress block | `journal_entry` | `storage` |
| `events` | event intake, deduplication, fan-out to consumers, compaction | `event`, `event_summary` | `storage` |
| `taxonomy` | shared tree, aliases, per-user overlay | `tax_node`, `tax_alias`, `user_node`, `user_alias` | `storage` |
| `knowledge` | evidence, state computation, the label rules, gaps, cold start | `evidence`, `knowledge_state` | `taxonomy`, `events` |
| `content` | sources, documents, private chunk links, shared chunks, annotations, scan verdicts, segmentation rule, file parsing, page fetcher | `source`, `source_file`, `document`, `document_chunk`, `chunk`, `chunk_annotation`, `chunk_scan`, `site_mask` | `storage`, `jobs` |
| `retrieval` | embedder, keyword search, rank fusion behind one `Retriever` interface | `embedding_model`, `emb_<model>` | `content` |
| `egress` | content classes, provider policy check, secret scanner interface, cost check | `spend_period`, `spend_entry`, `repo_setting` | `storage`, `journal` |
| `models` | provider adapter contract and adapters, chain resolution, scheduler, worker registry | `worker`, `provider_chain` | `egress` |
| `tasks` | one unit per model task: prompt version, input builder, output schema, parser, degraded behaviour | none | `models`, `retrieval`, `knowledge` |
| `delivery` | messages to devices: piggyback on event posts and a poll endpoint | `message` | `journal` |
| `scan` | lesson scan and lesson check orchestration, per-user resolution, card building | `scan` | `tasks`, `content`, `knowledge` |
| `ask` | on-demand explanation and questions | `ask`, `note` | `tasks`, `retrieval`, `knowledge` |
| `policy` | intervention rules, thresholds, rate limits | `policy_state` | `events`, `knowledge`, `tasks`, `journal`, `delivery` |
| `trainer` | course sources, trainer CLI wrapper, built pages, progress documents, item map | `course`, `course_file`, `course_artifact`, `course_item_map`, `trainer_progress` | `jobs`, `tasks`, `knowledge` |
| `mcp` | MCP server, a thin view over `knowledge`, `retrieval`, `taxonomy` | none | those modules, `egress` |
| `admin` | user management, caps, shared taxonomy curation, content-free counts | `user_limit` | `auth`, `taxonomy`, `egress` |
| `api` | HTTP routers, scope check, error mapping, streaming | none | all |

Job handlers live in the module that owns the work (`content` registers `ingest.document`, `trainer` registers `course.build`); the runner in `jobs` calls registered handlers and never imports those modules.

#### 5.2 Processes

| Process | Runs on | Contains | Count |
|---|---|---|---|
| `kata-core` | core host | `api`, scheduler, worker registry, MCP, the job runner loop with a process pool for parsing and embedding, periodic tasks (retention, chunk collection) | exactly one (queue and registry are in memory) |
| `kata-migrate` | core host | schema migrations under the administrator role, then exits | one-shot |
| Postgres | core host | database, container used only by kata | one |
| Reverse proxy | core host | TLS, routing by name | one (target only) |
| Backup timer | core host | nightly dump script | host timer |
| `kata-worker` | worker machine | worker daemon (pull client of the core); minimal form in M0 on loopback | one per worker machine (minimal from slice S2, full from S4b) |
| Model endpoints | worker machine | one process per loaded model (class L, class M) | started and stopped by the daemon |
| Batch engine | worker machine | heavy engine, started and stopped through configured commands | on demand (slice S13) |

A separate job process (`kata-jobs`) is not built at first. It is split out when the parsing measurement (section 18 R7) shows memory or CPU that stalls the API; job handlers are written without access to in-memory API state so the split is a deployment change.

#### 5.3 Clients

| Client | Language | Parts | Local state | Talks to |
|---|---|---|---|---|
| Browser extension | TypeScript, WebExtension MV3, Firefox first | content script (text extraction with Readability, segmenter, block marks, "silent here" switch, navigation detection); side panel (card, summary, questions, "I know this", character; opens scan and ask streams itself); background part (short API calls, cache, outbox) | page cards and marks by page key, last knowledge snapshot, outbox, token | core API |
| Editor extension | TypeScript, VS Code API | diagnostics for quiet marks, local stop patterns, panel with the character, git hook installer, MCP configuration helper | cache of file-hunk results, outbox, token in the editor's secret storage | core API |
| Device tool `kata` | decided by the terminal spike (R3); proposed: Python standard library only, because it has a pseudo-terminal module and the runtime named before (Node) needs a native add-on for one (Verify) | `enrol`, `term`, `flush`, `precommit`, `postcommit`, `hooks install`, `progress import` | spool directory, token file | core API |
| Terminal session `kata term` | part of the device tool; one process per session, started by the user | section 5.4 | none beyond the spool | core API |
| Git hooks | shell scripts | pre-commit: local gitleaks, then optional concept hints; post-commit: bypass detection | marker file in the repository's git directory | gitleaks binary, device tool |
| Phone page | TypeScript, installable web page served by the core | questions, review of cards, "add a link", journal view | service-worker cache, outbox in browser storage, session cookie | core API (same origin) |
| Trainer adapter | TypeScript compiled to one script, injected as a course plugin at build time | storage adapter registered through `registerStorage` | the trainer's browser storage, key namespaced by user id | progress endpoints on the trainer origin |
| Model worker `kata-worker` | Python | registration, long poll for work and control messages, result posts, heartbeat, model endpoint supervisor (it owns the GPU), availability switch | worker id, token file, configuration | core (outbound HTTP only), local model endpoints |

Browser differences the extension must handle (every cell: Verify against the browser's documentation before S3):

| Topic | Firefox | Chrome |
|---|---|---|
| Background context | event page, suspended when idle | service worker, suspended when idle |
| Consequence | no long-lived stream in the background; streams are opened by the side panel, which lives while it is open | same |
| Panel API | `sidebar_action` (`landscape` 2) | `side_panel`; the polyfill does not unify the two, so the panel host is a thin per-browser shim |
| Site permission | optional host permission, granted per site by the user and revocable | optional host permission per site |
| Meaning for kata | "add this site" in the panel saves a URL mask (below) and requests the optional host permission for its match pattern; the mask list of principle 5 decides where automatic scans run | same |
| Lesson change without page load | navigation detection in the content script (address change plus main content change) | same |
| Install without a store | stable builds load unsigned extensions only temporarily; needs signing for self-distribution | unpacked load in developer mode, or a packaged build |
| Token storage | extension storage restricted to trusted extension contexts where the browser allows it; the content script never needs the token (all API calls go through the background or panel) | same |

#### Added sites: URL masks

An added site is a URL mask, a pattern with wildcards, so one entry can cover a whole site such as an entire course platform. Automatic scanning on page open runs only for pages that match a mask the user added.

| Topic | Design |
|---|---|
| Syntax | `[scheme://]host[:port][/path]`. Scheme optional: without it, `http` and `https` both match; `*` also means both. Host: exact name, or a leading `*.` which matches the domain itself and every subdomain (`*.courses.example.org`). A wildcard elsewhere in the host is not allowed. Path optional: `*` matches any characters including `/`, other characters match literally; no path means the whole site (`/*`). Query and fragment are ignored in matching. Examples: `courses.example.org`, `*.example.org/learn/*`, `https://example.org/course/*/lesson/*` |
| Rejected masks | the bare `*`, a host that is only a top-level domain (`*.org`), and an empty host; the panel explains why. The mask is stored in a normalized form (lowercase scheme and host, no trailing dot) |
| Matching | one pure function `matchMask(mask, address)` in a shared extension module, used by the background part and the content script. The address is normalized the same way as for the page key. First the panel converts each mask to a WebExtension match pattern (`*://*.example.org/learn/*`) and requests it as an optional host permission, so the browser runs the content script only where a granted pattern covers the page. Then the content script asks the background part on load (and on a lesson change without a page load) whether the address matches an enabled mask; the background part answers from its cached list with `matchMask`. A page that passes the browser check but fails `matchMask` (the permission works per pattern, `matchMask` is the rule of record) is treated as not added. Verify the browser's pattern rules against `matchMask` in a unit test table (R19) |
| Storage | table `site_mask`, private per user: id, mask, enabled, created time. Synced through the core with `GET, POST /v1/me/site-masks` and `PATCH, DELETE /v1/me/site-masks/{id}`; cached in the extension's storage so matching works offline. The browser permission grant is per browser: a second browser gets the list from the core and asks the user to grant the patterns again |
| User view | the panel has a "Sites" screen: the list of masks with enabled switch, edit and delete, and "add this site" on the current page, which proposes a mask for the page's host (whole site) that the user can narrow or widen before saving |
| Privacy | the mask list shows where the user studies, so it is private data like the journal: never in logs, never in shared tables, not in `GET /v1/admin/counts`, never sent to a cloud provider or through MCP. The admin can see that a user has some number of masks only as a count if at all; the product shows no read path to the list for the admin |
| Editor and other clients | masks apply to the browser extension only; the phone page and the editor do not scan pages automatically |

Both browser targets are built in CI from slice S3 so differences show early; only Firefox is tested end to end until S15.

#### 5.4 Terminal tracking: an explicit session

Terminal tracking has one entry point that the user starts. It is opt-in per session; there is no always-on hook in the shell profile, and a terminal not started this way is never observed. (The older note placed a hook in the local shell profile, the setup notes; that is replaced.)

| Topic | Design |
|---|---|
| Entry point | `kata term` starts the user's local shell in a tracked session; `kata term -- ssh <arguments>` starts an SSH session in one. A start line says that tracking is on; leaving the shell ends it |
| Mechanism | the device tool runs the shell or SSH inside a local pseudo-terminal proxy and adds, for that session only, a prompt hook. Candidates, to be chosen by the spike in this order: the standard-library pseudo-terminal of the device tool's language; wrapping the system's terminal-recording helper |
| Mark format | the common shell-integration marks carry only prompt and command boundaries and the exit code (Verify); command text is not standard. kata defines one private escape sequence: session nonce, kind (command start, command end), encoded command text, exit code. The proxy drops any mark without the session's nonce, so remote output cannot forge events |
| Injection | local shell: a temporary start file that loads the user's own first. SSH: the hook definition is sent only after the first shell prompt has been seen, never during login banners, password or second-factor prompts; the SSH command the user asked for is not changed |
| What the proxy does | reads the marks, masks the command by its pattern list, writes the event to the spool, sends in the background, prints queued messages as one dim line before the next prompt, prints the destructive-pattern warning at command start |
| Printed text | any text from the core is reduced to printable characters and a length limit before it is written to the terminal (section 11.7) |
| Remote machine | nothing is installed or left behind, no token leaves the user's computer, the remote machine needs no route to the core |
| Shell profile | nothing is added |
| Prompt delay | none: capture is passive reading of the terminal stream; sending is asynchronous |
| Spike (slice S-1, section 18 R3) | confirm capture of command text and exit code inside an SSH session for bash and zsh remote shells, an old remote shell without a pre-execution hook, a terminal multiplexer with and without passthrough, a login with a password prompt, and a forged-mark test |
| Fallback if the spike fails | (1) `kata term` for local shells only; (2) for remote sessions the user runs one command by hand inside the remote shell that defines the same marks for that shell process (nothing persistent, no token); (3) for terminals inside the editor, the editor's terminal shell-integration events. If none works for a remote shell, scenario S3 covers local commands only |

### 6. Interfaces

#### 6.1 Client-core API

General rules:

| Topic | Rule |
|---|---|
| Shape | HTTP, JSON, base path `/v1`; schema generated from the core's models as OpenAPI; TypeScript types generated from it  |
| Versioning | within `/v1` only additive changes: new endpoints, new optional fields, new event types. Clients ignore unknown fields and unknown enum values. One admin updates core and clients together, so there is no promise to run two API versions side by side |
| Version handshake | every request carries `X-Kata-Client: <kind>/<version>`; `GET /v1/meta` returns the API version and one minimum client version. A client below it gets `426` with code `client_too_old`, shows "update needed" and continues from cache |
| Errors | `application/problem+json` with a stable `code`, a `request_id`, no echo of request content. A foreign or unknown id is `404`, never `403` (no existence leak) |
| Identity | `Authorization: Bearer <device token>`; web pages use a session cookie (section 11.2). Every endpoint declares its allowed scopes in the API schema (table below) |
| Idempotency | ids are made by the client (UUID version 7) for events, scans, asks, sources, notes, jobs. Primary keys are (`user_id`, `id`), so one user's id can never collide with another's. Repeating a create with the same id and the same body returns the existing resource; the same id with a different body is `409` |
| Concurrency | documents that are edited (`note`, `trainer_progress`, settings) carry a revision; writes send `If-Match`; mismatch is `412` |
| Caching | `ETag` on taxonomy, knowledge snapshot, cards |
| Streaming | server-sent events only for scans and asks, on `GET .../stream`, read with `fetch` from a panel context (never from the extension background). A broken stream is not resumed: the client reads the resource with `GET` and, if it is still running, opens the stream again and receives the events from the start |
| Polling | job progress and device messages are polled while a panel is open |
| Paging | opaque cursor |
| Limits | body size, batch size and rate per token from configuration; `429` with `Retry-After` |

Resources:

| Group | Endpoints | Notes |
|---|---|---|
| Meta | `GET /v1/meta`, `GET /v1/health` | health is content-free |
| Auth | `POST /v1/auth/enrol`, `POST /v1/auth/session`, `GET /v1/auth/devices`, `DELETE /v1/auth/devices/{id}`, `POST /v1/auth/enrolment-codes`, `POST /v1/confirmations/{id}` | section 11.2 |
| Self | `GET, PATCH /v1/me/settings`, `GET /v1/me/spend`, `POST /v1/me/export` (job), `DELETE /v1/me` (job) | settings hold switches, thresholds, language, provider chains, the background-prefetch switch (off by default for a user without a worker); the site masks have their own calls `GET, POST /v1/me/site-masks` and `PATCH, DELETE /v1/me/site-masks/{id}` (5.3) |
| Events | `POST /v1/events`, `GET /v1/events`, `DELETE /v1/events/{id}` | post is a batch; its response carries per-id results and pending messages for this device (section 6.2). Read and delete let a user see and remove single stored commands |
| Messages | `GET /v1/messages?since=` | polled by open panels |
| Taxonomy | `GET /v1/taxonomy`, `POST, PATCH, DELETE /v1/taxonomy/overlay/nodes[/{id}]`, `.../overlay/aliases` | merged view of shared tree and own overlay |
| Knowledge | `GET /v1/knowledge/snapshot`, `GET /v1/knowledge/states`, `GET /v1/knowledge/gaps`, `GET /v1/knowledge/nodes/{id}/evidence`, `DELETE .../evidence/{id}` | writes arrive as events |
| Scans | `POST /v1/scans`, `GET /v1/scans/{id}`, `GET /v1/scans/{id}/stream`, `GET /v1/pages/{page_key}/card` | section 8.1 |
| Sources | `POST /v1/sources`, `PUT /v1/sources/{id}/file`, `GET /v1/sources`, `DELETE /v1/sources/{id}`, `DELETE /v1/documents/{id}` | section 8.10 |
| Search | `POST /v1/search` | over the user's own links only |
| Asks | `POST /v1/asks`, `GET /v1/asks/{id}`, `GET /v1/asks/{id}/stream`, `POST /v1/asks/{id}/cancel` | section 8.4 |
| Code | `POST /v1/code/check` (file hunk to concept marks), `POST /v1/diffs/check` (staged diff to hints), `GET, PUT /v1/repos/{repo_id}` (cloud opt-in, local-only flag) | never blocking; cached by hunk hash; section 11.4 |
| Notes | `GET, PUT, DELETE /v1/notes/{id}` | revision checked |
| Journal | `GET /v1/journal`, `DELETE /v1/journal/{id}` | feedback arrives as events |
| Jobs | `POST /v1/jobs`, `GET /v1/jobs/{id}`, `POST /v1/jobs/{id}/cancel`, `POST /v1/jobs/{id}/resume` | section 8.11 |
| Courses | `POST /v1/courses` (job), `GET /v1/courses`, `DELETE /v1/courses/{id}`, `POST /v1/courses/{id}/open` (handoff code for the trainer origin), `POST /v1/courses/{id}/progress/import` | section 6.5 |
| Trainer origin | `GET /c/{id}/enter`, static pages under `/c/{id}/`, `GET, PUT /c/{id}/progress` | served only on the trainer name; section 6.5 |
| Worker | `POST /v1/worker/register`, `POST /v1/worker/poll`, `POST /v1/worker/requests/{id}/delta`, `POST /v1/worker/requests/{id}/done`, `POST /v1/worker/requests/{id}/error`, `POST /v1/worker/heartbeat`, `POST /v1/worker/goodbye` | section 6.3; pull link, all calls come from the worker |
| Admin | `/v1/admin/users`, `/v1/admin/users/{id}/enrolment-codes`, `/v1/admin/users/{id}/limits`, `/v1/admin/taxonomy/...`, `/v1/admin/counts`, `/v1/admin/workers` | content-free; no impersonation |
| MCP | `/mcp` | section 6.4 |

Scopes per endpoint group (part of the API schema; a test checks every route against this table):

| Endpoint group | Scopes allowed |
|---|---|
| Meta, health, enrol | none |
| Events post, messages, sources create and file upload | `app`, `tool`, `ingest` |
| Diffs check, progress import | `app`, `tool` |
| Events read and delete, self settings and spend, taxonomy, knowledge, scans, search, asks, code check, repos, notes, journal, jobs, courses, device list | `app` |
| New-device code, device removal, export, delete everything | `app` plus a confirmation in an open panel of a full-scope device (section 11.2) |
| Trainer origin | `trainer:<course id>` |
| Worker | `worker` |
| MCP | `mcp` |
| Admin | `admin` |

#### 6.2 Event model and offline queue

| Topic | Rule |
|---|---|
| Model | append-only log per user; state (knowledge, counters, journal) is derived on the core  |
| Envelope | `id` (client-made, UUID version 7), `seq` (per-device counter), `type` with the version in the name (`terminal.command.v1`), `occurred_at` (client clock), `payload`. Each batch also carries the client's current time. The device and user come from the token, never from the body |
| Intake | insert with "do nothing on conflict" on (`user_id`, `id`); the response lists each id as `accepted`, `duplicate` or `rejected` with a code. A rejected event is dropped by the client and written to its local log |
| Clock | the core computes the device's skew from the batch's "client now" and shifts `occurred_at` by it; the result is clamped to the range from "receive time minus the queue age limit" to "receive time". A real offline event keeps its age; a wrong clock is corrected |
| Order | per device by `seq`; across devices by the corrected time, tie by receive time. A reinstalled client enrols as a new device, so its `seq` starts again without conflict |
| Late events | intervention rules ignore events whose corrected time is outside their window; they still count as evidence |
| Client queue | extension: browser database; editor: file in the extension's storage; device tool: spool directory of line-delimited JSON, written by `kata term` sessions and git hooks; phone page: browser storage |
| Retry | flush on start, on reconnect and on a timer; batches of up to 100; exponential backoff with jitter from 1 s to 5 min |
| Bounds | at most 5000 events or 5 MB per device queue, 30 days; when full, the oldest events are dropped |
| Masking | terminal events are masked by the `kata term` proxy before they are written to the spool |
| Piggyback | the response to `POST /v1/events` returns queued messages for this device, so a terminal session needs no open connection |

Event types (first set): `page.viewed`, `block.read`, `knowledge.asserted` (known or not known, from the button), `terminal.command`, `editor.diagnostic`, `editor.signal`, `intervention.shown` (client-side, model-free), `intervention.feedback`, `precommit.result`, `precommit.bypassed`, `note.saved`, `client.timing`. Trainer results are not client events: the core derives them from saved progress documents (section 6.5).

#### 6.3 Worker link

Decided: the link is pull-based over plain outbound HTTP. The worker asks the core for work with a long request, runs it on its local model and posts the answer back. Nothing connects to the worker's machine; the core never needs the worker's address; the link works with or without a VPN and with no local model running (a worker that is not asking is absent). Rejected: the core calling the worker's model endpoint; one WebSocket carrying everything.

In M0 the same pull code runs over loopback: a minimal `kata-worker` on the workstation polls the core on `127.0.0.1`. There is no separate direct local-model mechanism.

Worker to core only (bearer token, scope `worker`, section 11.2). The session id from `register` travels in every later call; there is no session key and no worker address.

| Call | Content | Answer |
|---|---|---|
| `POST /v1/worker/register` | worker id, protocol version, worker version, models (class, key, context, slots, state `loaded`, `loading`, `unloaded`, `unavailable`), GPU memory total and free, mode, `available` flag | session id, heartbeat interval (default 3 s), poll timeout (proposed 25 s), settings (idle-unload time, slot limit), or `426 protocol_unsupported` with the supported version |
| `POST /v1/worker/poll` (long request) | session id, free slots per class | held until there is a message or the poll timeout; answer is a list of messages (below), empty on timeout |
| `POST /v1/worker/requests/{id}/delta` | sequence number, text delta (batched, about every 100 ms, proposed) | `ok`, or `cancelled` |
| `POST /v1/worker/requests/{id}/done` | final sequence number, finish reason, token usage | `ok` |
| `POST /v1/worker/requests/{id}/error` | reason (`memory`, `unavailable`, `busy`, `model_error`), detail without content | `ok` |
| `POST /v1/worker/heartbeat` | session id, state: loaded models with their state, free memory, mode, `available`, busy slots | `ok`, or `unknown_session` (the worker registers again) |
| `POST /v1/worker/goodbye` | session id | the core stops granting work and marks the session absent; used before shutdown and before sleep when the system announces it |

Messages in a poll answer (names kept from the former frames):

| Message | Content | Worker action |
|---|---|---|
| `request` | request id, model class, priority, deadline, OpenAI-style chat body | run it on the local model for that class; post `delta`, then `done` or `error` |
| `cancel` | request id | stop generating at once; free the slot; post nothing more for it |
| `ensure` | class | load the class if it can (memory check first) |
| `release` | class | the class may be unloaded now |
| `mode` | `interactive`, `batch_coexist`, `batch_exclusive` (from S13) | switch, if the local switch allows |

Rules:

- Slots and credit: every poll declares the free slots per class. The core hands out at most that many `request` messages for a class and counts a slot as used until the request ends with `done`, `error` or `cancel`. A worker never gets more work than it asked for. With no free slot the worker keeps one poll open with zero slots; it then receives only `cancel`, `ensure`, `release` and `mode`. A worker with `available` off declares no slots (it counts as absent for work).
- One poll open per session. A new poll replaces the old one. The core answers a poll at once when a message is ready, so a granted request costs no added wait.
- Long-poll timeout: proposed 25 s, shorter than the proxy idle timeout of 4.2. After a timeout answer or an answer with messages the worker polls again at once. After a network error or a `5xx` the worker retries with backoff: 0.5 s, doubling to 30 s, with jitter, reset by the first good answer (proposed). `unknown_session` or `401`: register again.
- Cancel: the core marks the request cancelled (client gone, deadline passed, user pressed stop). It sends `cancel` in the open poll, or in the next one, and answers the worker's next `delta` post with `cancelled`. The worker stops either way. Late posts for a cancelled request are discarded.
- Presence: a session is present while a poll is open or a heartbeat arrived within two heartbeat intervals (about 6 s with the default; proposed). Neither: the session is absent. Sleep, network change and crash look the same.
- Lost worker: when a session goes absent, every request in flight on it fails with `worker_lost`. An interactive request moves to the next chain entry if its deadline allows; a background request is queued again. A request that gets no first `delta` within the first-byte timeout from configuration is treated the same, and the worker is marked absent until its next poll or heartbeat.
- Admission: a worker with a free slot has an open poll, so a request is picked up at once. A request not picked up within the priority's wait budget (9.4) moves to the next chain entry. An over-full worker answers `error busy`; the core counts slots itself and normally does not exceed them.
- Control wishes: `ensure`, `release` and `mode` are wishes the core sends in the poll answer. The worker decides, and may refuse. It confirms through the heartbeat (the next one carries the changed state at once; `loading`, `loaded`, `unloaded`, `failed` with reason `memory` or `unavailable`) and through result posts. The core keeps the wish until the state matches, a failure is reported or the scheduler withdraws it. The core never starts or stops a process on the worker's machine.
- The worker owns the GPU: it keeps class L resident, loads class M on demand, unloads it after the idle time even when the core is silent, swaps models and switches modes by itself, and the user's local availability switch always wins.
- Resume: after sleep the first poll or heartbeat gets `unknown_session` or fails; the worker registers again. A restart of the core empties the registry; workers notice the same way.
- Versioning: one protocol version, an integer sent in `register`. The core serves one version; a worker that announces another gets `426 protocol_unsupported` and stays absent. Within a version only additive changes (new messages, new optional fields); a worker ignores unknown messages and fields. Core and workers are updated together.
- A worker serves only its own user. The `worker` scope allows only the calls above.

#### 6.4 MCP surface

Streamable HTTP at `/mcp`, token scope `mcp`, the same user scope as the API, so row rules apply.

| Kind | Name | Returns |
|---|---|---|
| Tool | `kata_concept_state` | states for given concept names (alias match) |
| Tool | `kata_gaps` | new and learning concepts, optional topic filter |
| Tool | `kata_profile_summary` | states aggregated by topic |
| Tool | `kata_search` | own notes and concept entries; never material text in version 1 |
| Resource | `kata://taxonomy`, `kata://profile` | merged taxonomy, compact profile |

Read-only in version 1. A write tool needs a separate scope and is not built.

Everything a tool returns goes to the assistant's own cloud provider, which the core does not know, and to an assistant that has tools of its own. The MCP gate is therefore its own short list, not the cloud gate of 11.4:

1. Content class against a fixed "unknown provider" policy, the most restrictive one: states, node names and the user's own notes may pass; material text, code and terminal commands may not.
2. Secret scan of the result.
3. Size limit per result.
4. Shape: every result is returned as quoted data under a fixed prefix that says it is reference data and not an instruction; node names are restricted to a character class and a length (section 11.7).

No cost check applies: the assistant's provider bills its own user.

#### 6.5 Trainer adapter contract

| Operation | Contract |
|---|---|
| Origin | trainer pages are served on their own name, separate from the API and app pages. The trainer name has its own narrower cookie, not sent to the app name. On loopback before the proxy exists, a second port gives the same separation |
| Identity | opening a course from an app page calls `POST /v1/courses/{id}/open`, which returns a one-time handoff code; `GET /c/{id}/enter?code=` on the trainer origin sets a cookie that is `HttpOnly`, `Secure`, `SameSite=Strict`, limited to the path `/c/{id}/` and to scope `trainer:<course id>`. That scope reaches only this course's pages and progress. No token in page script |
| Registration | a plugin script added to the generated course at build time calls `registerStorage` |
| `load(course)` | `GET /c/{id}/progress` returns the progress document and its revision, or "none" |
| `save(course, doc, base revision)` | `PUT` with `If-Match`; `412` returns the current document; the adapter merges with the trainer's own merge function and retries |
| Offline | the trainer's browser storage stays the working copy; the adapter marks it dirty and retries later; the page never waits on the core |
| Local copy | the adapter namespaces the browser-storage key by user id and clears the working copy when the session's user changes, so two users of one browser profile do not upload each other's results |
| Evidence | on every accepted save the core compares item entries with the previous revision. For each item whose `ok` or `bad` counter rose it writes one evidence row with the id (course, item, `ok`, `bad`), so a repeated or merged save adds nothing. Counters that fell (a progress reset, `resetAt`) write nothing and remove nothing |
| Item mapping | the core owns it : `course_item_map` written at generation time, plus a tag `k:<node id>` on each item; item ids are opaque and append-only, so the map survives re-generation |
| Page safety | generated item text is untrusted: the build accepts only the item schema's text fields, and both origins send a strict content security policy (own scripts only, no inline script, no foreign connections). Verify that the trainer's renderer escapes item text |
| CLI import | `kata progress import <file>` posts an exported progress file to `POST /v1/courses/{id}/progress/import`; the core merges by running the pinned `trainer` binary, not by its own merge code |

Changes needed in the trainer tool: machine-readable output for `build` and `next-id`; a current-format `import-progress` with machine-readable output and no hand-made id map; a merge command for two progress documents (proposed; until it exists, import replaces only when the stored document is empty); a round-trip test with an external storage adapter.

#### 6.6 Provider adapter contract

| Element | Contract |
|---|---|
| Descriptor | id, kind (`worker`, `openai_compatible`, `claude`, `cli`), policy flags (may train on requests, jurisdiction, retention, `trusted`), price entry, concurrency limit. A user's worker (also the M0 loopback worker) is a descriptor of kind `worker` with `trusted` set, created from registration: the adapter queues the request for the worker's next poll and streams the posted deltas back (6.3); the request body is OpenAI-style. `openai_compatible` is for cloud and other endpoints the core itself calls |
| `capabilities` | streaming, structured output mode (`schema`, `object`, `none`), context size |
| `estimate(request)` | input tokens, maximum output tokens, price from one flat table (input and output price per provider model). Peak-hour prices (`provider` 1) are added only when a provider with them is adopted; until then the higher price is entered |
| `complete(request, cancel)` | stream of text deltas, then usage and finish reason |
| `health` | reachable or not, with a reason code |
| Request | provider-neutral: task id, messages, output schema, maximum output tokens, temperature, seed, deadline, request id |
| Errors | normalized: `unavailable`, `rate_limited`, `timeout`, `invalid_output`, `refused_content`, `auth`, `cancelled` |
| Output validity | the task layer validates against the schema and retries once; an empty answer in JSON mode counts as `invalid_output` (`provider` 5) |

The vendor-CLI adapter stays optional and off by default.

### 7. Data model

#### 7.1 Three kinds of tables

| Kind | Rule | Tables |
|---|---|---|
| Private | `user_id` not null; uniform row rule; reachable only through a user scope | `user_setting`, `provider_chain`, `repo_setting`, `site_mask`, `user_node`, `user_alias`, `knowledge_state`, `evidence`, `event`, `event_summary`, `source`, `source_file`, `document`, `document_chunk`, `scan`, `ask`, `note`, `journal_entry`, `message`, `policy_state`, `job`, `course`, `course_file`, `course_artifact`, `course_item_map`, `trainer_progress`, `spend_period`, `spend_entry` |
| Shared content | no user id; no personal data; no row rule | `tax_node`, `tax_alias`, `chunk`, `chunk_annotation`, `chunk_scan`, `embedding_model`, `emb_<model>` |
| System, per user | carry a `user_id` and the same row rule, so a user scope can read its own rows (`GET /v1/auth/devices`); before a user is known they are reached only through definer functions | `device`, `device_token`, `enrolment_code`, `pending_action`, `worker`, `user_limit` |
| System, global | no user content; system scope only | `app_user`, `schema_meta` |

Keys: UUID version 7 for all ids. Every private table whose id is made by a client has the primary key (`user_id`, `id`). `chunk` is keyed by the SHA-256 of its normalized text.

#### 7.2 Per-user isolation mechanism 

| Layer | Mechanism |
|---|---|
| Database roles | `kata_owner`: owns the tables, runs migrations, no login at runtime. `kata_app`: the runtime login role, no ownership, no bypass of row rules. `kata_definer`: a non-login role with the bypass attribute that owns the definer functions. `kata_backup`: a login role with the bypass attribute, used only by the dump script |
| Row rules | every table with a `user_id` column has row-level security enabled and forced; one policy for read and write: `user_id` equals the transaction setting `kata.user_id`, read null-safe (a missing setting and an empty string both count as "no user" and match no row, without a cast error) |
| Transaction | every database access runs in a short transaction that sets `kata.user_id` locally from the authenticated token; the setting ends with the transaction, so pooled connections are safe |
| Streams | a stream endpoint holds no transaction and no connection while it waits; it opens one short transaction per batch of events it emits |
| Storage interface | `Storage.for_user(user_id)` returns a `UserScope` with the repositories for private tables; there is no repository method for a private table outside a `UserScope`. `SharedScope` covers shared content. `SystemScope` covers global system tables |
| Cross-user operations | only through named functions owned by `kata_definer` that return no private content: token lookup, job pick (returns job id and user id), spend totals for the admin, chunk collection, retention sweep, account deletion. All of them are listed in one file with the reason for each |
| Data migrations | run in `kata-migrate` as functions owned by `kata_definer`, without returning private rows |
| Jobs | the runner picks an id, then enters that user's scope; it never holds a cross-user read |
| Shared chunks | no row rule (the text is not personal). The repository reads `chunk`, `chunk_annotation` and `emb_<model>` only through a join on `document_chunk`, which has the row rule, so a user reaches only chunks they link (7.3) |
| Tests | a catalogue test lists every table with a `user_id` column and fails if row security is not enabled and forced (there is no exemption list: system per-user tables carry the rule too); a two-user test walks every endpoint in the API schema, every MCP tool and every job kind and expects `404` or an empty result for the other user's ids; connection-reuse tests on one physical connection: user A then user B, and "a user, then no user", both expecting only the right rows and no error; each definer function is called as `kata_app` and must return rows |

The three behaviours this rests on (the value of a custom setting after a local set on a reused connection; forced row security against the administrator and inside definer functions; dump under row security) are checked by a short SQL spike in slice S-1 before S1 is written. Status: Verify.

Scope of this mechanism: it keeps data private from the app, its bugs and other users. It does not protect against whoever runs the core host (database superuser, backups, provider accounts); that is accepted and no per-user encryption is built.

#### 7.3 Shared and private course material

| Data | Where | Why |
|---|---|---|
| Chunk text, language, kind | `chunk` (shared), one row per content hash | stored and embedded once |
| Annotation of a chunk | `chunk_annotation` (shared), keyed by hash, task version and topic-list version; holds the topic id from the shared list and, from slice S6, the raw concept names the model gave | derived from content and shared data only; contains no private node id and no result of a private alias |
| Secret-scan verdict | `chunk_scan` (shared), keyed by hash and scanner rule version: `clean` or `hit` with rule ids | scanned once at intake, reused at every cloud call (11.4) |
| Embedding | `emb_<model>` (shared) | same |
| Who has which chunk, from which page, in which order | `document_chunk` (private) | the link is the personal part |
| Resolution of concept names to nodes (shared tree, then the user's overlay), labels, card | `scan` (private), recomputed when the user's aliases or states change | depends on the user |
| Source, document, title, address, flags (`local_only`, graded) | `source`, `document` (private) | personal |
| Uploaded files | `source_file` (private) | personal |

Consequences:

- Sharing is deduplication, not access: a user reaches a chunk only after posting the same content, so no user receives material through kata that they did not already have.
- Retrieval joins through `document_chunk`, so results never include unlinked chunks.
- An admin edit of the shared tree does not invalidate annotations unless the topic list itself changes; alias changes only trigger a new resolution, not a new model call.
- Deleting a document removes links; a shared chunk row is removed by the periodic collection when no user links it. Until then the text stays for the other users.
- Content class (`material`, `code`, `terminal`, `personal`, `public`) is stored on the link, not on the chunk, because the same text can be public for one user and part of a local-only project for another.
- A chunk with a secret-scan hit is kept and usable locally (worker, retrieval) but never sent to a cloud provider or through MCP; this holds for page blocks and uploaded files alike. The chunk is not rejected; clients show it as "not sent to cloud".

#### 7.4 Taxonomy and overlay

| Element | Design |
|---|---|
| Shared tree | `tax_node` (id, parent, kind `category`, `topic`, `concept`, slug, name, status `active` or `retired`) and `tax_alias` (node, alias, language, normalized form). Read-only for users; written only through the admin API |
| Versions | two counters in `schema_meta`: the topic-list version (changes when a topic is added, retired or moved) and the alias version. Clients cache `GET /v1/taxonomy` by `ETag` |
| Overlay | `user_node` (own topic or concept, parent in the shared tree or in the overlay, status `suggested` or `active`, origin `user` or `model`) and `user_alias` (own alias for a shared or own node). Never changes the shared tree |
| References | private tables point at a node with two columns, shared id or own id, exactly one set (check constraint) |
| Rename, move | ids are stable, so a rename or move changes no state |
| Retire | the node stays for existing references and is hidden from new tagging |
| Merge | version 1: retire one node and add its name as an alias of the other; existing states stay on the retired node and count for the target through the alias at read time. A function that rewrites references, and split, are left for later |
| Model suggestions | from slice S6: concept names a model gives that resolve to no node go to that user's overlay as `suggested`, after validation of length and characters (11.7); they never reach the shared tree by themselves |
| Promotion | a user may send an overlay node to the admin as a proposal; this is an explicit act |
| Normalized form | every node keeps a terse normalized name beside free text, because terse entries match best (the benchmark profile as text) |

#### 7.5 Knowledge state and evidence 

| Element | Design |
|---|---|
| States | three: `known`, `learning`, `new` (`SUITE` 8). The older "proficiency level" is replaced by an internal score from 0 to 1 that maps to the three states by thresholds |
| Grain | `knowledge_state` exists for topics and, from slice S6, for concepts. A concept without own evidence inherits its topic's state. Cold start writes topic-level states from the skill list, which comes from the administrator's initial review (slice S3a) |
| Evidence | `evidence` is append-only: node, type, polarity, corrected time (6.2), and an optional source reference (event id or progress revision). The reference may be empty: events are compacted after 90 days and may be deleted one by one |
| Types and default order of weight | `assertion` (button) > `trainer` and `test` > `code` > `terminal` > `reading`. Weights and half-lives are configuration |
| Rule | the evidence of a node is ordered by corrected time, tie by id. score = sum of weight x polarity x decay(age), clamped; thresholds map to a state. Fixed rules, applied in that order: an assertion sets the state at once and holds until a configured number of later contrary trainer or test results; `reading` alone can raise `new` to `learning` and never to `known`; negative evidence (wrong answers, repeated errors) lowers the score |
| Determinism | the state is a function of the ordered evidence list and the configuration version; it can be recomputed after a late event, a deletion or a threshold change, and two cores with the same rows give the same state |
| Scheduling | spaced repetition stays inside the trainer; the core reads the trainer's item stage. No scheduling library in the core in version 1 |
| Thresholds | defaults in configuration; per-user overrides in `user_setting`, tuned only from that user's journal |

#### 7.6 The label rules

Two rules, both in the core only. Clients cache results and apply one local rule: after "I know this" the pressed block shows as known until the core answers.

| Rule | Used | Input | Result |
|---|---|---|---|
| Topic rule | Milestone 0 and the default afterwards (marks are at topic level first, concept level in a later slice) | the block's topic id and the user's state for that topic | the label is the topic's state; a topic with no state is `new`. This is the benchmarked rule (benchmark results: tagging consistency) |
| Concept rule | only after the experiment of 8.3 passes, and only for a block with at least 3 resolved concepts (configuration) | the block's resolved concepts and their states | `new` if at least 30 percent of the resolved concepts are new; else `learning` if at least 30 percent are new or learning; else `known` (benchmark results: lesson check) |

Names that resolve to no node are not counted in the ratio and are shown on the block as "unknown term". With fewer resolved concepts than the minimum, the topic rule decides. The 30 percent values come from a reference set where most blocks were new (benchmark results: lesson check), so they are starting values to be checked on real labels (section 18 R2). The output always names the topic or the concepts that caused the label.

#### 7.7 Journal

`journal_entry`: time, type (`mark`, `nudge`, `stop`, `precommit`, `egress_block`, `cap_warning`), trigger, context reference, shown text, device, provider class used, degraded flag, feedback (useful, not useful), outcome (dismissed, disabled). Private; shown text and context are kept 90 days. The admin sees only counts by type and outcome through `GET /v1/admin/counts`.

#### 7.8 Retention and deletion

Retention:

| Data | Kept in detail | After that |
|---|---|---|
| `event` (commands, page views, dwell) | 90 days | compacted into `event_summary` (per day: concept, command family, error kind, counts), detail deleted |
| `journal_entry` shown text and context | 90 days | text removed, counts kept |
| `ask` question and answer | 90 days | deleted |
| `evidence`, `knowledge_state` | no limit | they hold node references and dates only |
| Sources, documents, links, files, notes, courses, progress | until the user deletes them | n/a |
| `spend_entry` | a configured number of periods | totals kept in `spend_period` |
| Finished `job` | 30 days | deleted |
| Backups, pre-migration dumps | rotation window (section 12.2) | deleted data lives in backups until rotation; a restore replays deletions from the tombstone file |

Deletion at every level:

| Level | Endpoint | Effect |
|---|---|---|
| One event (for example one stored command) | `DELETE /v1/events/{id}` | row removed; evidence from it stays without its source reference unless deleted too |
| One journal entry, one evidence row | `DELETE /v1/journal/{id}`, evidence delete | row removed; state recomputed |
| One page | `DELETE /v1/documents/{id}` | links, scans, cached cards removed; orphan chunks collected |
| One source | `DELETE /v1/sources/{id}` | all its documents and files; evidence that came from it |
| One concept's history | evidence delete per node | state falls back to the topic's |
| One course | `DELETE /v1/courses/{id}` | sources, built pages, item map, progress; trainer evidence from it |
| One device | `DELETE /v1/auth/devices/{id}` | token revoked; its queued messages dropped; optionally the devices enrolled from it; past events stay unless deleted |
| Everything | `DELETE /v1/me` | a job deletes every private row of the user, then the identity rows; orphan chunks collected; a content-free receipt remains |

All private parent tables cascade to their children, so each level is one delete plus a recompute. Every deletion of a source, document, device or account also appends its id to the tombstone file (12.2).

#### 7.9 Embedding storage

One table per adopted embedding model, `emb_<model key>` (chunk hash, vector of that model's dimension), registered in `embedding_model` (name, dimension, file hash, status `building`, `active`, `retired`). Changing the model: create the new table, run a re-embedding job, switch the active model in settings, drop the old table. The vector cache key is the model hash plus the chunk hash. Index: start with an exact search over the user's linked chunks; add an approximate index only when the measured query time passes the budget.

Keyword search: a text-search column on `chunk`, filled once at insert (chunks never change), not a generated column. The baseline for the retrieval comparison is the `simple` configuration over text with identifier splitting (camelCase, snake_case) applied in the core before insert; per-language configurations and a BM25 extension are candidates in the same comparison, because lesson text mixes languages (prose in one, terms in English). Fusion: reciprocal rank fusion.

#### 7.10 Migration approach 

- Tool: Alembic. Migrations run only in `kata-migrate` under `kata_owner`; `kata-core` checks the schema version at start and refuses to run on a mismatch.
- Every table with a `user_id` is created together with its row rule in the same migration; the catalogue test (7.2) guards this.
- Migrations are backward compatible with the previous image (expand, backfill, contract over two releases). Rollback is therefore "previous image, same database"; no events are lost.
- `kata-migrate` takes a dump before it applies anything, encrypted and rotated like every backup; it is the last resort, not the rollback path.

### 8. Key flows

Abbreviations: "chain" = provider chain resolution (9.6); "gate" = egress gate (11.4). Messages reach panels by polling and a terminal session by piggyback (6.1, 6.2).

#### 8.1 Page scan to side-panel card

1. Start. On a page whose address matches a mask the user added (principle 5; matching in 5.3) the scan starts when a lesson opens, including a lesson change without a page load. On any other page it starts only when the user presses "scan" in the panel. For a user without a worker the scan on open runs only on masked pages, and background prefetch of further pages is a setting, off by default. The content script checks the "silent here" switch and the graded-page check. Graded or silenced: stop, show nothing.
2. The content script extracts the article with Readability on a copy of the page and segments it by headings, merge under 120 words, split over 900 (benchmark results: automatic blocks). Block id = first 16 hex digits of the hash of the normalized text, plus an ordinal when the same text repeats.
3. The background part looks up the page key (hash of the normalized address) and block ids in the cache. Hit: card and marks appear at once, marked with their age.
4. `POST /v1/scans` with address, title, language, blocks (id, text, heading path, kind) and the ids of visible blocks. Budget 1.5 s to the first byte.
5. The core stores source, document, chunks by hash and private links; new chunks get a secret-scan verdict (`chunk_scan`); it reads `chunk_annotation` for each hash. Annotated blocks get labels at once (7.6).
6. For the rest the scheduler queues tag requests (class `tag`, interactive priority, two class L slots), visible blocks first. Nothing else is sent to the user's worker while tagging runs.
7. The side panel opens `GET /v1/scans/{id}/stream` and receives `block` events as each block finishes (topic, label, source `model` or `rule`), then `tags_done` with the card (counts, top gaps). The 30 s target ends here.
8. After `tags_done` the core queues the wish `ensure M` (delivered in the worker's next poll answer) and the summary request (class `summary`); the stream continues with `summary.delta` and ends with `done`. The summary has no latency target.
9. The content script marks each block when its event arrives (first marks within 2 s is the target) by setting an attribute on the block's elements and one injected stylesheet. A page re-render triggers re-segmentation; marks are re-applied by block id; unmatched marks are dropped silently.
10. The card and marks are cached; `page.viewed` goes to the outbox.

Summary input: the whole text if it fits a token budget from configuration; otherwise headings plus the first sentences of each block up to the budget. A two-stage summary is not built in version 1.

Why the summary waits: with both models generating, the small model falls to about 27 tokens per second from about 90, which would add roughly 10 s to tagging and break the 30 s target.

Failure branches:

| Case | Behavior |
|---|---|
| Core unreachable or slow at step 4 | cached card with "offline" mark, or "no data yet"; the scan request is not queued (it is stale later); `page.viewed` is queued |
| No chain entry passes for `tag` (worker absent, and cloud not in the chain, not allowed, over the cap, or blocked by the scanner) | rule tagging: topic names and aliases matched against the block text; labels computed as usual; card marked "model-free" with the reason |
| Worker lost mid-scan | remaining blocks go to the next chain entry or to rule tagging; stream sends `degraded` with a reason |
| Invalid model output | one retry, then rule tagging for that block |
| Summary provider absent or class M cannot load | card without summary, headings listed instead |
| Stream breaks | the panel reads `GET /v1/scans/{id}` and opens the stream again; the scan continues on the core regardless |
| Site permission withdrawn, or the mask removed or disabled | automatic scans stop for the pages it covered; the panel offers "scan" by click |
| A block or file chunk has a secret-scan hit | the block is tagged and marked locally as usual (worker or rules) but never goes to a cloud provider; the card shows "not sent to cloud" for it |

#### 8.2 Tagging and the label

Milestone 0 (the benchmarked task):

1. Input: one block, the shared topic list as a stable prompt prefix, the output schema.
2. The model returns one topic id from the list. No profile is in the prompt, so nothing personal leaves with a tagging call.
3. Code validates the id against the topic list and stores it in `chunk_annotation` (hash, task version, topic-list version).
4. Code computes the label with the topic rule (7.6).

From slice S6, behind its own measurement (8.3): the output also carries concept names. They are stored raw in the shared annotation. Resolution to nodes (shared tree, then the user's overlay) is done per user at read time and cached in `scan`; names that resolve to nothing become `suggested` overlay nodes after validation.

Failure branches: unknown topic id: retry once, then rule tagging. Batching several blocks per request is not assumed; it is one of the levers the first spike may test.

#### 8.3 Lesson check against the knowledge base (an experiment with an exit criterion)

Concept-level labels are not shipped until this passes; until then the topic rule is the product behaviour.

1. For each block whose topic state is `learning` (the blocks where finer grain matters), retrieve candidate concept entries by keyword search over names and aliases (later also vectors): about 50 for class L, 10 to 25 for class M.
2. The model selects which candidates the block teaches and may add names not in the list. It does not output a state.
3. Code resolves, looks up states and applies the concept rule (7.6).

Exit criterion (slice S6): on a labelled set from a real user, mean class recall of at least 0.8 and above the topic rule's result on the same set by more than the measured noise; a 55-block lesson still inside 30 s on the reference GPU. Reasons for the caution: the benchmark measured model-decided labels, its best mean class recall was 0.81 under an optimistic reference, and 50 candidates roughly double the prompt of the measured 25 (benchmark results: lesson check).

Failure branches: no candidates found or fewer resolved concepts than the minimum: topic rule. Provider absent: topic rule from the cached annotation.

#### 8.4 On-demand explanation

1. The user selects a block or asks a question; the client sends `POST /v1/asks` with the block reference or selected text, the question and the language setting.
2. The context builder collects: the block, the top retrieved chunks from the user's own links, the user's notes on the concepts, and known neighbouring concepts for analogies. Retrieved text is placed in the prompt as quoted reference material. Terms stay in English.
3. Chain for class `explain`. Cloud entry: gate first; chunks with a secret-scan hit are left out.
4. The answer streams over `GET /v1/asks/{id}/stream` and is rendered as plain text: no automatic links, no images (11.7). If the base has nothing relevant, the answer says so and is marked as general knowledge (`SUITE` 8).
5. The ask is stored for 90 days; `block.read` evidence is recorded.

Failure branches: class M not loaded: `ensure`, wait within the budget, else next chain entry. No provider: show the retrieved passages and notes with a "no model" mark. Cancel: `POST .../cancel` closes the stream to the worker or the cloud provider; the cost entry is corrected to what was used. Graded page: the client does not offer questions about the page's own questions.

#### 8.5 Terminal nudge

1. The user starts a tracked session: `kata term` (local shell) or `kata term -- ssh ...` (5.4). Without this step nothing below happens.
2. For each command the proxy reads command text, exit code and time from the session's marks; the prompt is never delayed.
3. The device tool masks by its own pattern list, writes the event to the spool and sends in the background with a 1 s timeout.
4. `events` stores it; `policy` counts by key (command family, exit code). Threshold: 3 similar errors in 10 minutes; limits: 1 per topic per hour, two dismissals silence the topic for the day.
5. On a hit, `policy` maps the error to a topic by a rule table or a class `hint` request, builds the text (model, or a fixed template with a link to the concept), writes the journal entry through `journal` and a message through `delivery`.
6. Delivery: in the response to the next event batch; the proxy strips the text to printable characters and a length limit and prints one dim line before the next prompt of that session. Open panels get the same message by polling `GET /v1/messages`, where the character shows it.
7. Feedback and dismissals return as events. Leaving the shell ends the session; the proxy flushes the spool once and exits.

Failure branches: core unreachable: events stay in the spool (sent by the next session or by `kata flush`), no nudge; when they arrive late they count as evidence but trigger nothing. No provider for `hint`: template text. User without a worker: the masked command may go to cloud after the gate; a scanner hit blocks the call and the template is used. Marks not received in an SSH session (5.4 spike case): the session works as a plain terminal, the proxy says once that tracking is off, and nothing is recorded.

#### 8.6 Stop signal

1. Local detection, no network. Editor: on change, debounced, the extension matches secret patterns and destructive patterns and shows a warning diagnostic and a character message. Terminal, inside a `kata term` session only: the proxy matches a short destructive-pattern list when the command-start mark arrives and prints one warning line; the command proceeds.
2. The client queues `editor.signal` or `intervention.shown`; the core writes the journal.
3. Core-side trigger: two ignored nudges on the same topic raise the next message to level `stop`; delivered as in 8.5.

Failure branches: core unreachable: local signals still work; the journal entry arrives later. Pattern false positive: the user's "not useful" feedback feeds that user's thresholds and switches.

#### 8.7 Pre-commit

1. The pre-commit hook runs gitleaks locally on the staged changes with a 5 s limit.
2. Finding: the commit is blocked with the rule name and location. No content leaves the machine; only a `precommit.result` event with rule ids and counts is queued. No finding: the hook writes a marker with the staged tree hash.
3. With time left in the 5 s, `kata precommit` posts the staged diff to `POST /v1/diffs/check`; hints (new concepts touched) come back as a character message. Timeout: skipped silently. This is the only contact with the core in the commit path, and it follows the code rules of 11.4.
4. The post-commit hook compares the commit's tree with the marker and then deletes the marker. No marker, or a marker for another tree, means the pre-commit hook was bypassed: it queues `precommit.bypassed`. This is how an override with `--no-verify` reaches the journal, because that option skips the pre-commit hook but not the post-commit hook.
5. The post-commit hook does nothing while a rebase, merge or cherry-pick is in progress, where commits are made without the pre-commit hook (Verify per git operation).

Install: `kata hooks install` in one repository. If a hook manager or a configured hooks path is present, it does not overwrite anything and prints the two lines to add.

Failure branches: gitleaks missing or over the time limit: warn in one line and allow (only a finding blocks); CI scans again. Core unreachable: steps 1, 2, 4 and 5 still work. Hooks removed by the user: nothing is recorded; accepted.

#### 8.8 Trainer progress return

1. The user opens a course from an app page; the handoff of 6.5 sets the course cookie on the trainer origin; the page loads built files from `course_artifact`.
2. The adapter loads the progress document; the trainer works on its browser copy (key namespaced by user id).
3. On save the adapter sends `PUT /c/{id}/progress` with `If-Match`.
4. The core stores the new revision, compares items with the previous one (6.5 "Evidence"), maps item ids to nodes through `course_item_map`, writes `trainer` evidence and recomputes states.
5. Clients see changed states at their next snapshot read.

Failure branches: `412`: merge in the page, retry. Core unreachable: local copy stays dirty, retried on the next save or load. Item without a mapping: evidence skipped and counted in the `doctor` report. Progress reset: no evidence written. Another user signs in on the same browser profile: the working copy is cleared before load. Exported file: `kata progress import` (6.5).

#### 8.9 Mini-course build through trainer

1. The user picks categories and topics from `GET /v1/knowledge/gaps` and sends `POST /v1/courses` (a job).
2. Step `select`: gap concepts and supporting chunks from the user's own links.
3. Step `generate`: class `generate_course` requests in batches per concept; the item format comes from the pinned `trainer schema --brief`. Lesson text is passed as quoted reference material. Each batch is saved in the job's checkpoint.
4. Step `add`: only the text fields of the item schema are accepted from the model. Course files are written from `course_file` into a temporary directory; `trainer next-id`, `trainer add`, `trainer validate --json --strict`. Diagnostics go back to the model; at most a configured number of rounds.
5. Step `build`: add the storage adapter plugin and item tags, `trainer lock`, `trainer build`; store the output in `course_artifact` and the map in `course_item_map`; remove the temporary directory.
6. A message announces the course; the page is served on the trainer origin.

Failure branches: no provider: job state `waiting_provider` until a deadline. Cap reached: job paused, user told. Validation not clean after the last round: failing items dropped; build if a minimum number remain, else fail with the diagnostics summary. Core restart: resume from the checkpoint. Generated items are private course data and are never shared.

#### 8.10 Ingestion of pages, PDF and slides

| Source | Path |
|---|---|
| Course page or any open tab | the extension posts blocks (8.1 steps 2 to 5); the core never fetches platform pages |
| Article or documentation by address (phone, panel) | `POST /v1/sources` with the address; a job fetches it under the fetch rules below, extracts and segments |
| PDF or slide file | `POST /v1/sources`, then `PUT .../file`; a job parses with Docling on the core host CPU, one slide or section per block, then the same chunk path |

Common steps: store chunks by hash and links; scan each new chunk once and store the verdict in `chunk_scan` (a hit keeps the chunk for local use and bars it from cloud and MCP); embed missing chunks; queue background tagging for chunks without annotation.

Fetch rules for addresses (the core host also runs unrelated services, so its own network is a real target):

- `http` and `https` only; a fixed redirect limit; every redirect is checked again.
- The name is resolved once and the connection goes to the checked address (no second resolution).
- Refused targets: loopback, private, link-local, carrier-grade and the VPN's ranges, and their IPv6 equivalents; the core host's own names.
- Response type limited to text, HTML and PDF; size and time limits; robots rules respected.

Failure branches: parse failure: source marked failed with a code, file kept for retry. Parsing too slow on the core host: fallback to plain text extraction (section 18 R7). Duplicate upload: same file hash returns the existing source.

#### 8.11 Long jobs: start, progress, cancel, resume 

1. Start: `POST /v1/jobs` (or a resource endpoint that creates one) inserts a `job` row with kind, parameters (ids only, no content), state `queued`.
2. Run: one runner loop inside `kata-core` picks the oldest queued job through a definer function, enters the job's user scope and calls the handler registered for the kind. CPU-heavy steps run in the process pool. Model calls go through the scheduler with background or batch priority.
3. Checkpoint: after each step the handler writes a JSON checkpoint (finished step keys and their small outputs) and a progress value on the job row.
4. Progress: the client polls `GET /v1/jobs/{id}` while a panel shows the job.
5. Cancel: sets a flag; the handler checks it between steps and cancels a running model request through the scheduler.
6. Resume: at core start every job in state `running` goes back to `queued` with an attempt count; the handler skips steps found in the checkpoint. A job that fails a configured number of times is `failed`. `POST .../resume` restarts a paused or failed job from its checkpoint.

Job kinds: `ingest.document`, `embed.chunks`, `tag.chunks`, `scan.prefetch`, `course.build`, `deck.analysis`, `project.analysis`, `index.rebuild`, `user.export`, `user.delete`. Periodic tasks (retention sweep, chunk collection) are timers in `kata-core`, not jobs. No leases, no per-step tables, no progress stream and no fairness between users in version 1; they return if a second runner or more users appear.

### 9. Model orchestration

#### 9.1 Split of duties 

| Duty | Administrator | Reason |
|---|---|---|
| Queue, priorities, deadlines, chain resolution, cost | core scheduler | it sees all of a user's devices and jobs |
| Load and unload, memory check, idle unload, availability, starting and stopping engines | worker | only it sees the GPU, the desktop session and local use |
| Asking for a class (`ensure`), allowing unload (`release`), asking for a mode | core, as wishes in the poll answer that the worker may refuse; the worker confirms by heartbeat | keeps the worker safe when the core is wrong or silent |
| Starting and stopping model processes, swapping models, switching GPU modes | worker only; the core never starts a process on the worker's machine | it owns the GPU |

#### 9.2 Worker registry

In memory in `kata-core`: per registered session the user, worker id, protocol version, models and their states, free and used slots per class and requests in flight, pending control wishes (`ensure`, `release`, `mode`), free memory, mode, `available` flag, last poll and last heartbeat time. No worker address is kept. The `worker` table keeps only identity and last-seen time. A restart of the core empties the registry; workers register again at their next poll or heartbeat (6.3). In M0 the registry holds the one session of the loopback worker, created by its registration like any other.

#### 9.3 Task classes and model classes

| Task class | Model class | Default chain, user with a worker | Default chain, user without a worker | Degraded behaviour |
|---|---|---|---|---|
| `tag` | L | worker L | cloud small | rule tagging (topic names and aliases) |
| `hint` | L | worker L | cloud small | template text |
| `code_check` | L | worker L | none; cloud only for repositories the user opted in, for a user without a worker (11.4); otherwise model-free code checks | no marks |
| `summary` | M (on demand) | worker M, then cloud if the user allows it | cloud | headings list |
| `explain`, `ask` | M | worker M, then cloud if the user allows it | cloud | retrieved passages and notes |
| `code_overview` | M | worker M | none unless opted in | skipped, user told |
| `generate_course` | H or M | cloud, worker M | cloud | job waits |
| `batch_analysis` | B (batch engine) | worker B, cloud | cloud | job waits |

One chain per task class per user, defaults from configuration. For a user with a worker, `tag` has no cloud entry by default: with the worker absent, scans fall to rule tagging, and explanations go to cloud only when the user has allowed it. The user can add cloud to any chain in settings.

#### 9.4 Request queue and priorities

| Priority | Used for | Deadline behavior |
|---|---|---|
| P0 realtime | hints for the terminal and editor | short deadline; on miss, template text |
| P1 interactive | the scan the user is looking at, summary, explanation | wait budget, then next chain entry |
| P2 background | prefetch scans, tagging of ingested files, code checks on save | waits; goes to cloud only if the chain has a cloud entry and, for a user without a worker, prefetch is switched on (off by default) |
| P3 batch | whole deck, project analysis, index building | waits for batch mode (slice S13) |

Rules:

- One queue per worker session, ordered by priority, then arrival. The core hands the next request out only when the worker's poll declares a free slot for its class (6.3).
- While any P0 or P1 request runs or waits on a worker, no P2 request is dispatched to it. Background work is cut into block-sized requests (about 0.4 s each), so yielding means "do not hand out the next one"; running background requests are not cancelled.
- While a scan's tagging runs, no class M request is handed to that worker (8.1). An explanation the user asks for during a scan waits for `tags_done` or goes to the next chain entry, by its wait budget.
- At most 2 slots per model. An interactive scan may use both L slots; background work uses one. Whether two L slots still fit beside class M under a desktop session is unmeasured (9.5).
- Interactive requests are in memory only; if the core restarts the client retries. Background and batch requests are issued again by their job on resume.
- Cloud requests have a concurrency limit per provider; `rate_limited` triggers backoff.

#### 9.5 GPU use and class selection

Until slice S13 the worker has one switch, `available` on or off, set locally (the mode-switch script of the setup notes calls it). Off means the GPU is used for something else and the worker counts as absent.

- Class L: resident while the worker is available.
- Class M: loaded on `ensure` or on the first M request; the scan flow queues `ensure` after `tags_done`. Unloaded by the worker after the idle time (default 10 minutes) or on `release`.
- Memory check: before a load the worker compares free memory with the model's need plus a margin (default 500 MiB). Not enough: `failed memory`; the scheduler moves on in the chain.
- What is measured: both models at 8k context fit with 1182 MiB free on a GPU with no desktop session and one slot per model. What is not: two class L slots, and a desktop session with a browser and an editor, which typically hold 300 to 800 MiB. On the M0 workstation that is the normal case. A spike in slice S-1 measures it; if class M does not fit, one of these is chosen from the numbers: one L slot while M is loaded; class M at 4k context; the summary on class L.

Modes arrive with slice S13 (batch work), not before:

| Mode | Loaded | Serves |
|---|---|---|
| `interactive` | L resident; M on demand | L, M |
| `batch_coexist` | L plus the batch engine with a memory reserve | L, B |
| `batch_exclusive` | batch engine only | B |

- The user switches modes locally; the core does not start batch mode by itself in the first version of S13. A `mode` message in the poll answer is a request the worker may refuse; the worker reports its mode and any refusal in the heartbeat. Load, unload and mode switch are always done by the worker daemon.
- While class M is loaded the batch engine waits.
- In `batch_coexist` the small model is several times slower while both generate. An interactive scan therefore pauses the batch job at its next step boundary; until the pause takes effect the scan is outside its target, and the card says so.
- Batch mode is not used while the workstation is also the core host: the batch engine's memory does not leave room for the core (section 15, S13 depends on S8).

#### 9.6 Provider chain resolution

For a request of task class T for user U:

1. Read U's chain for T (own setting, else the default for U's kind, 9.3).
2. For each entry in order:
   - Worker entry: is a session of U registered and available, with the class loaded or loadable, and is the estimated wait within the priority's budget? If not, next entry. A worker entry has no gate.
   - Cloud entry: does every part of the request pass the content rules for this provider (11.4)? Is the source or repository flagged `local_only`? Does the secret check pass? Does the cost check succeed (9.7)? If any answer is no, next entry, and the reason is kept.
3. Dispatch to the first entry that passes. On `unavailable`, `timeout` or `worker_lost`, continue with the next entry if the deadline allows.
4. No entry left: the task's degraded behaviour, with the kept reason (`no_worker`, `provider_unreachable`, `cap_reached`, `secret_blocked`, `policy`) shown to the user.

Escalation by low confidence inside a chain is not built in version 1: the first available provider wins.

#### 9.7 Cost check

1. Estimate: input tokens (counted pessimistically) and the request's maximum output tokens, priced from the flat table (6.6).
2. Reserve: one atomic update adds the estimate to `spend_period.spent` and succeeds only if the result stays under the cap. A `spend_entry` row records the call with the estimate.
3. Call the provider.
4. Correct: replace the estimate with the provider's reported usage (one update of the period total and the entry). If the call failed before reaching the provider, subtract the estimate. If it is unknown whether the provider billed, keep the input estimate.

There is no separate "reserved" state and no sweeper: a crash between steps 2 and 4 leaves the estimate counted, which errs on the safe side; the `doctor` report lists such entries and the admin can correct the total.

Warning threshold: one message per period when crossed. At the cap: degraded behaviour and a message; the admin can raise the cap in `user_limit`. The admin sees totals per user, never requests. Provider keys are core-host configuration in version 1.

### 10. Failure and offline behavior

| What breaks | What the user sees | What still works |
|---|---|---|
| Core unreachable (down, VPN off, maintenance) | "offline" mark; cached cards and marks; no new scan | local stop patterns, pre-commit secret check, trainer on its browser copy, event queues, cached profile and taxonomy |
| Core reachable, user's worker absent, the chain has a cloud entry that passes | nothing special; slower or costlier answers | everything, through cloud after the gate |
| Worker absent and no cloud entry passes (not in the chain, not allowed, capped, blocked) | "model-free" mark with the reason | rule-based labels, retrieval and search on the core host CPU, notes, journal, trainer |
| A class is missing on the worker (class M cannot load, memory) | that request comes from the next chain entry or shows passages only | the other class |
| Cloud provider down or rate-limited | as above when it is the only provider | worker path if present; degraded behaviours |
| Cost cap reached | message "cap reached"; model-free hints | everything local and on the worker |
| Secret-scan hit on an outgoing part | message that the cloud call was blocked (no secret shown) | worker path; degraded behaviour for that request |
| Secret scanner binary missing on the core host | cloud calls refused (fail closed); health check red | worker path |
| Worker lost during a request | short delay, then the answer continues from another provider or a degraded mark | all other requests |
| Worker switched to not available, or in batch mode | same as worker absent for L and M | batch work in batch mode |
| Job runner stalled or a job failing | long jobs do not progress; uploads stay "queued" | all interactive paths |
| Postgres down | same as core unreachable | client-side functions |
| Core restart | streams drop; panels read the resource and open the stream again; running interactive requests are retried by clients | jobs resume from their checkpoint; workers register again |
| Client queue full | nothing | oldest events are dropped |
| Client older than the minimum version | "update needed"; cache mode | local functions |
| Trainer page cannot reach the core | nothing; progress saved in the browser | the whole trainer; sync later |
| trainer binary missing or wrong version | course build fails with a clear code | existing courses |
| Embedding model missing | keyword-only retrieval, marked in results | everything else |
| Backup failed or disk absent | line in the `doctor` report and in the nightly log | service unaffected |

### 11. Security and privacy

#### 11.1 Threats considered

| # | Threat | Main answer |
|---|---|---|
| T1 | A code path returns another user's data | row rules in the database, storage interface, two-user and connection-reuse tests (7.2) |
| T2 | A device or its token is lost | per-device revocable tokens, hashed at rest, scopes per client kind, confirmation for new devices and destructive calls (11.2) |
| T3 | A secret or sensitive text leaves to a cloud provider | one egress gate; scanner fails closed; code is worker-only by default (11.4) |
| T4 | Text from a page or a model manipulates a model, an assistant, a terminal or a page | one rule per sink (11.7) |
| T5 | The page fetcher is used to reach internal addresses | fetch rules of 8.10 |
| T6 | A worker is compromised or impersonated | token scope `worker`; a worker receives only its own user's requests; it has no listening port, and the `worker` scope allows only the calls of 6.3 |
| T7 | Private data lands in the public repository | synthetic test data only; CI secret scan; benchmark outputs are metrics only (`SUITE` 5) |
| T8 | The operator of the core host reads private data | accepted, out of scope: small group server, no per-user encryption |
| T9 | An enrolment code is guessed | short life, single use, attempt limit, rate limit |
| T10 | Data leaves through the MCP client to its provider | the MCP gate of 6.4; no material text |
| T11 | Script in a generated course page acts with the user's session | trainer pages on their own origin with a course-only cookie; content security policy; item text treated as untrusted (6.5) |
| T12 | A restore brings back revoked tokens or deleted data | tombstone file replayed after every restore (12.2) |

#### 11.2 Authentication flow

1. First start: a command on the core host creates the first admin and prints an enrolment code.
2. The admin creates a user and an enrolment code through the admin API or command. The code is single-use, lives 15 minutes, and is stored hashed.
3. The device sends `POST /v1/auth/enrol` with the code, a device name and its kind. The core creates the device and returns a token once: a random 256-bit value with a short public id prefix. The core stores only its SHA-256. The scope is fixed by the kind the code was issued for.
4. Every request: the token is looked up by a definer function that returns user, device and scopes; the scope is checked against the endpoint; the user scope is opened.
5. A further device of the same user: a device with scope `app` requests a code; the request creates a `pending_action` that the user confirms in an open panel of a full-scope device (it shows what is being added). Only then is the code issued. Tokens with scope `tool`, `ingest`, `mcp`, `worker` or `trainer` cannot request codes. A device with a narrow scope cannot enrol others. The new device records which device enrolled it.
6. Destructive calls (`DELETE /v1/me`, device removal, export) use the same confirmation step.
7. Revocation: `DELETE /v1/auth/devices/{id}` by the user, with the option to revoke the devices enrolled from it as well; the admin can disable a whole user. Each revocation is appended to the tombstone file.
8. Web pages: the enrolment page of the app origin exchanges the code for a device token held in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie. State-changing requests also need the `X-Kata-Client` header and a matching origin. Trainer pages get a different, course-only cookie on their own origin (6.5).

Scopes: `app` (full user API; extension, editor extension, phone page), `tool` (device tool: event post, messages, source create, diff check, progress import), `ingest` (event post, messages and source create only; for a phone shortcut), `trainer:<course id>`, `worker`, `mcp`, `admin` (only on tokens of admin users, requested explicitly). The table in 6.1 maps every endpoint group to scopes.

#### 11.3 Token storage per client

| Client | Storage |
|---|---|
| Browser extension | the extension's local storage area (not the synced one), restricted to trusted extension contexts where the browser allows it (Verify per browser); the content script never reads it |
| Editor extension | the editor's secret storage |
| Device tool, git hooks | one file under the user's configuration directory, mode 0600, scope `tool` |
| Model worker | file, mode 0600, path from the worker configuration, scope `worker` |
| Phone page | cookie as in 11.2 |
| Trainer pages | course-only cookie on the trainer origin |
| MCP client | its own configuration, a separate token with scope `mcp` |

#### 11.4 Cloud hop rules (the egress gate)

Every request that leaves the core for a cloud provider passes these checks in order. (MCP results have their own shorter gate, 6.4.)

1. Content class of each part against the provider's policy flags:

| Content class | Default |
|---|---|
| Knowledge states, notes, the text of a page the user scanned, open documentation | any provider that does not train on requests |
| Terminal commands | cloud only for a user without a registered worker, after client masking |
| Code and diffs (`code_check`, `code_overview`, `diffs/check`) | worker only. Cloud needs an opt-in per repository, stored per user on the core in `repo_setting` and keyed by a repository id the client derives (hash of the first commit's id). The core cannot tell public code from private code, so there is no "public code" default. Without the opt-in (or without a worker), code checks use model-free rules |
| Anything from a source or repository flagged `local_only` | never |
| A chunk with a secret-scan hit | never; shown to the user as "not sent to cloud" |

2. Secret check. Stored chunks are not scanned again: their verdict is read from `chunk_scan` by hash and scanner rule version (scanned once at intake). Only the parts that are not chunks (question, notes, command, diff) are scanned at call time, with gitleaks through the scanner interface. A hit blocks the call and writes a journal entry with the rule id and the content class, without the matched text. Scanner error or absence: the call is refused. For a tagging call the whole text is a stored chunk, so no scanner process starts on the scan path.
3. Cost check (9.7).
4. Send, with the provider's no-training setting where one exists.

Data minimization: tagging prompts carry no profile (8.2); explanation prompts carry only the states of the concepts involved. Requests handed to the user's own worker (also the M0 loopback worker) skip the gate: descriptor flag `trusted`.

#### 11.5 Secret handling

| Secret | Where | Rule |
|---|---|---|
| Provider API keys | files named in the core configuration | never in the database, the repository, logs or error messages |
| Database passwords per login role | files named in the configuration | `kata_app`, `kata_backup` and the migration login each have their own |
| Device tokens | hashed in the database; clear only on the device | shown once |
| Worker session ids | memory only, on both sides; not a secret (the worker token authenticates) | new at every registration |
| Backup encryption key | held by the admin, outside the core host's kata directories | see 12.2 |
| Secrets in terminal commands | masked on the client before the spool | never reach the core |
| Secrets in page blocks or uploaded files | the chunk is stored with a `hit` verdict and never leaves the core host or the user's worker; shown as "not sent to cloud" | journal keeps rule ids only |

#### 11.6 Logging without secrets

- Log calls accept only a fixed set of typed fields: request id, user id (opaque), device id, route, status, duration, task class, provider id, token counts, cost, reason codes. There is no free-text field for payloads.
- Validation errors do not echo input.
- Exceptions are logged by type and location; messages from providers are reduced to a code.
- A test feeds marked synthetic content through every endpoint and fails if the marker appears in logs.

#### 11.7 Untrusted text: one rule per sink

Text from web pages, uploaded files and models is data. Where it can turn into an instruction or an action, a fixed rule applies:

| Sink | Rule |
|---|---|
| Tagging and lesson-check prompts | no tools; output bound to a schema; every id validated in code against the list that was offered |
| Explanation and course-generation prompts | retrieved and lesson text enters as quoted reference material under a fixed instruction that it is not to be followed; no tools |
| Panels (side panel, editor panel, phone page) | model text is rendered as plain text; no automatic links, no images, no markup from the model |
| Terminal (`kata term`) | text from the core is reduced to printable characters and a length limit before printing; no escape sequences pass |
| MCP results | quoted data under a fixed prefix, size-limited; node names restricted to a character class; no material text (6.4) |
| Overlay names suggested by a model | validated for length and characters before storage, because they return into later prompts as candidates |
| Generated course items | only the item schema's text fields are taken; pages run on the trainer origin under a content security policy (6.5) |
| Remote terminal output | marks without the session nonce are dropped (5.4) |

A test page with injected instructions is part of the test set (section 13).

### 12. Operations

#### 12.1 Configuration

| Component | Source | Holds |
|---|---|---|
| Core, migrate | one configuration file plus environment overrides with the prefix `KATA_`; secrets by file path | database address, listen addresses, the two public names, cache directory, provider descriptors and the price table, default chains, thresholds, limits, timeouts, retention periods, scanner and trainer binary paths, embedding model |
| Worker | own file | `core_url`, token path, model definitions per class (start command or local endpoint address, context, slots, memory need), idle-unload time, memory margin; from S13 the batch engine start and stop commands |
| Clients | settings page or file | `core_url`, timeouts |

Per-user settings (switches, thresholds, language, chains, site mask list (table `site_mask`, 5.3), repository opt-ins) live in the database, not in files.

#### 12.2 Backup and restore 

- From the first slice: a nightly database dump in custom format, encrypted, with rotation 7 daily and 4 weekly. In M0 it goes to a local directory; in the target to the external disk plus a copy to a second location (open: which).
- Pre-migration dumps and relocation dumps use the same encryption and the same rotation.
- Tombstone file: a small append-only file kept beside the backups (and copied with them). It holds ids only: revoked devices and tokens, disabled and deleted users, deleted sources and documents, with the time. After any restore it is replayed before the core starts, so a restore cannot bring back a revoked token or deleted data.
- Recovery point: 24 hours. Continuous log archiving is not built in version 1 (it ties the setup to host paths and adds operating work that a small group core does not justify).
- Restore is the relocation procedure of 4.3; running it on a schedule against a scratch database is the restore drill.
- A backup contains every user's data in clear after decryption; the admin holds the key.

#### 12.3 Upgrades and migrations

1. Pull the new image tag (pinned in the compose file).
2. `kata-migrate` dumps, then migrates (backward compatible with the previous image, 7.10).
3. The core restarts; clients ride through on cache; workers register again.
4. `GET /v1/meta` announces a new minimum client version, if any; the admin updates clients and workers in the same sitting (12.6).
5. Rollback: start the previous image on the same database. The pre-migration dump is only for a migration that damaged data.

Pinned inside the image: gitleaks, the `trainer` binary, the embedding model reference. A change of any of them is an image change.

#### 12.4 Observability 

| Signal | Content | Use |
|---|---|---|
| Logs | structured JSON as in 11.6; the request id travels client, core, worker, provider | debugging without content |
| Client timings | `client.timing` events stored as rows: scan start to first block mark, to `tags_done`, to `done`; local action times | the three targets as the user perceives them |
| `kata-core doctor` | one content-free report from the database and the process: target percentiles from client timings, fallbacks by reason, worker presence history, queue length now, job failures, spend per user, cost entries left uncorrected, scanner blocks, unmapped trainer items, last backup, client versions seen | what a dashboard would show, without a metrics server |
| Journal | per user, private | tuning of interventions |
| Not built in version 1 | a metrics endpoint with a scrape server; tracing | add when the report is not enough |

#### 12.5 Resource budget on the server

The core host also runs unrelated services. Proposed container limits, to be confirmed by measurement on the real machine:

| Part | Memory | CPU |
|---|---|---|
| Postgres (kata's own container) | 4 GB | no limit |
| `kata-core` without the pool | 1 GB | 2 cores |
| Process pool including the embedding model | 3 GB | 4 cores |
| File parsing (in the pool, one file at a time) | up to 6 GB more at peak | same 4 cores |
| Total ceiling for kata | about 14 GB of 32 GB | half the cores |

While the workstation is the core host the same ceiling applies there; it does not fit beside the batch engine, which is one reason batch mode waits for the move (9.5). Disk: the database grows mainly with uploaded files and built course pages; a per-user storage quota (`user_limit`) bounds it.

#### 12.6 Distribution and updates

| Part | How it reaches a small group machine | Update |
|---|---|---|
| Browser extension | a signed build for self-distribution (not listed in a store) for the first browser; a packaged build for the second | new signed build installed by the admin; the minimum-version check tells users when |
| Editor extension | a packaged extension file installed from disk | same |
| Device tool, git hooks | one install script that puts the tool on the path and enrols the device | same script |
| Worker | the same image or package as on the admin's machine, with its own configuration file | updated together with the core (one protocol version) |

Signing for self-distribution, and whether the automation tool can drive an extension side panel, are checked in slice S0 (Verify).

#### 12.7 Operating work for one admin

What the admin must do by hand, so the cost is visible: update the core image, clients and workers together; keep the provider price table current; curate shared taxonomy proposals; hold the backup key and run the restore drill; read the `doctor` report; issue enrolment codes and raise caps. Kept out on purpose to limit this list: a metrics stack, peak-hour price logic, mixed-version operation, a second process, and sharing a database server with other services.

### 13. Testing strategy

Start small and add layers when a second client or implementer appears.

From the first slices:

| Layer | What | Rules |
|---|---|---|
| Unit | label rules, state computation, policy rules, chain resolution, cost check, segmenter, masking patterns, fetch deny list | synthetic data only; never bound to the repository's own content or to real lessons |
| Isolation | section 7.2 tests, including connection reuse and definer functions | run on every change |
| Scopes | every route checked against the scope table of 6.1 | generated from the API schema |
| Client-core contract | the OpenAPI schema and generated TypeScript types; one end-to-end smoke test per client | See architecture.md |
| Segmentation | golden vectors (synthetic pages to block ids) run by the extension's segmenter and the benchmark's segmenter | keeps benchmark numbers valid for the product |
| Model-dependent, in CI | a fake provider that returns recorded outputs; parser and prompt-builder tests on those; no GPU, no network  | recorded outputs come from synthetic inputs |
| End-to-end on the workstation | compose with core, Postgres and a fake worker that polls the core (or the minimal worker with a real model); the extension loaded in the browser against a synthetic lesson page; offline run with the core stopped mid-scan | depends on the automation check of S0; if the side panel cannot be driven, this layer covers content script and API only |

Added with the feature they guard:

| Layer | What |
|---|---|
| Untrusted text | a synthetic page with injected instructions and markup: tags stay schema-valid, the panel shows plain text, a generated course page runs no foreign script, MCP results stay quoted, a terminal line carries no escape sequence, a forged terminal mark is dropped (11.7) |
| Worker link | register, poll and long-poll timeout, slot and credit limits, cancel through poll and through `cancelled`, absent after no poll and no heartbeat, pickup timeout, `error busy`, lost mid-stream, `ensure`, `release` and `mode` confirmed by heartbeat, protocol mismatch, backoff; one run with a real suspend and resume of the worker machine |
| Provider adapters | one conformance suite against a fake OpenAI-compatible endpoint (empty JSON answers, rate limits); optional live run with a key, by hand |
| Trainer adapter | a built sample course in a headless browser: answer items, progress reaches the core, evidence appears; conflict path; reset path; two users on one browser profile; CLI import |
| Restore | restore a dump taken before a revocation and a deletion, replay the tombstone file, check both stay gone |
| Commit hooks | pass, block, bypass, stale marker, rebase in progress, hook manager present |
| MCP | tool list, the MCP gate, calls through an MCP client library |
| Events | golden fixtures per event type; clock skew and late-event cases |

Measurements (not CI):

| Measurement | Rule |
|---|---|
| Latency against the targets | three runs per cell, mean and spread; cells: worker cold, worker cached, with the summary following, class M first load from disk, desktop session present, through cloud, through the VPN |
| Label quality | a labelled set from a real user (blocks with new, learning, known), kept outside the repository; reported as mean class recall; threshold 0.8 for a rule to become the product default. The older threshold in `SUITE` T2 (0.9 accuracy) belongs to a model-decides task that the design no longer uses |
| Model regression | the benchmark suite (`SUITE`) run by hand or on a schedule on a worker machine, compared with a baseline and its noise; metrics only leave the machine |

Cleanup duties: every test removes its temporary directories, spool files, sockets, processes and environment changes; database tests use a scratch database that is dropped; containers started by tests carry a test name prefix and are removed on exit and on interrupt; benchmark runs check GPU memory back to the pre-run level (`SUITE` 3); the suite checks that the count of temporary entries did not grow.

### 14. Third-party parts and licence check list 

"Expected" is this document's belief, not a verified fact; every row needs the check unless a note already records it. The list lives in the repository and a CI step compares it with the installed dependency set.

| Part | Use | Shipped by kata | Expected licence | Status |
|---|---|---|---|---|
| FastAPI, Uvicorn, Pydantic, httpx | core | dependency | MIT, BSD | Verify |
| Postgres driver and SQL toolkit, Alembic | storage, migrations | dependency | choose a permissive driver | Verify; avoid copyleft drivers or record the reason |
| Postgres, pgvector | database | not shipped | PostgreSQL licence | Verify |
| fastembed, ONNX runtime | embeddings | dependency | Apache-2.0, MIT | Verify |
| Embedding model weights (candidates) | retrieval | downloaded by the operator | per model | Verify per candidate |
| MCP SDK | MCP server | dependency | MIT | Verify |
| gitleaks | scanner in the core image; local git hook | binary in the image | MIT | Verify release activity and stdin options |
| detect-secrets | alternative scanner | no | unknown | Verify |
| TruffleHog | rejected | no | AGPL-3.0 | rejected |
| Docling and its default models | file parsing | dependency | MIT code (`landscape` 6, secondary) | Verify code and weights |
| Plain PDF text library (fallback) | file parsing | dependency | permissive | Verify |
| Article extraction for fetched pages | ingestion | dependency | to choose | Verify |
| Readability | extension | bundled | Apache-2.0 | Verify |
| WebExtension polyfill | extension | bundled | MPL-2.0 | Verify; file-level copyleft is acceptable, record it |
| UI library for panels | extension, phone page | bundled | MIT | Verify |
| Build and test tools (bundler, extension runner, editor packaging, browser automation) | development | no | mixed permissive, MPL | Verify |
| the trainer tool | trainer binary in the image, hosted runtime | binary and pages | own project | Verify that its licence allows bundling; verify that its renderer escapes item text |
| llama.cpp, Ollama, LM Studio | model endpoints | not shipped | MIT for llama.cpp (`landscape` 4) | not distributed |
| Gemma model weights | classes L and M | not shipped | model terms | Verify terms for local personal use |
| Batch engine and its model | class B | not shipped | external | not distributed |
| A BM25 extension for Postgres | retrieval candidate | not shipped | varies; some are AGPL | Verify before the comparison |
| Mesh VPN client | access | not shipped | product choice open | n/a |
| FSRS libraries | not used in the core in version 1 | no | unknown | no check needed now |
| Device tool runtime | terminal sessions, hooks | standard library only (proposed) | n/a | decided by the terminal spike |
| A Postgres-backed queue library | not used: the job table is own code (8.11) | no | n/a | no check needed now |

### 15. Build order

No dates. Spikes come first because their results can change the design. Each later slice ends with something a user can run.

| Slice | Exists at the end | Depends on |
|---|---|---|
| S-1 Spikes (throwaway scripts; each ends with a number or a yes/no added to the benchmark results) | (1) Scan latency with the product prompt: topic-only output, a realistic topic list, two class L slots, summary after tagging, three runs; first-highlight time. (2) Memory: two class L slots plus class M at 8k under a desktop session with browser and editor. (3) Scanner time per call on the core host CPU. (4) Terminal capture inside SSH with the nonce mark and a forged-mark test; decides the device tool's mechanism and language. (5) Trainer storage hook round trip and a check that the renderer escapes item text. (6) Row-rule behaviour in SQL: setting after reuse, forced rules with definer functions, dump under row rules | none |
| S0 Skeleton | repository with CI (lint, tests, secret scan, licence list check), compose file (kata's own Postgres, core), configuration loader, `kata-migrate`, OpenAPI and TypeScript type generation, `/v1/meta`, nightly encrypted dump; checks: extension signing for self-distribution, browser automation of the side panel | S-1 item 6 |
| S1 Minimal core | users, admin bootstrap, enrolment, device tokens with the scope table, storage scopes and row rules with the isolation tests, event intake, shared topic list, skill-list cold start (the list loaded by an import command in Milestone 0), topic-level states, the topic label rule, delete of a document and of an event | S0 |
| S2 Model path through the pull link on loopback | the core side of 6.3 (register, poll, delta, done, error, heartbeat, goodbye; `worker` descriptor, `trusted`, no gate; registry with one session), a minimal `kata-worker` with one class L model, topic-only `tag` task with a fake worker in tests, scans API with a stream, rule tagging as degraded behaviour | S1, S-1 item 1 |
| S3 Browser extension | content script (extraction, segmenter, marks, navigation detection), side panel card, "I know this", one added site mask with scan on open and scan by click elsewhere, the mask list screen with matching (5.3), cache, outbox, offline mark, manual "silent here" switch; both browser targets built in CI. **Milestone 0 is complete here**: extension, minimal core with Postgres and token login, tagging through the administrator's local model | S2 |
| S3a Initial review (proposed) | the big first review in which the user marks which topics they know and which not; it writes topic-level states of type `assertion` and so becomes the cold-start skill list. Open detail: a guided screen in the side panel, or an imported list file (a command reading a file); proposed start: the import file, because Milestone 0 already loads a list that way, and the guided panel screen after it. Concept-level review comes with S6 | S3 |
| S4a Cloud path | egress gate (policy flags, chunk verdicts, call-time scan, cost check), journal, one cloud adapter, `summary` task after tagging, per-user chains with the two default sets | S3, S-1 item 3 |
| S4b Worker daemon | `kata-worker` completed (reconnect with backoff, goodbye, availability switch, class L supervisor, protocol version check), scheduler with two priorities, slot and credit accounting, presence and admission timeouts, cancel through the poll, `worker_lost` failover; test with a real suspend | S3 |
| S5 Jobs and ingestion | job table and runner loop with the process pool, shared chunks with private links, file upload and parsing, page fetch with the fetch rules, deletion at every level, tombstone file, retention sweep | S1 |
| S6 Retrieval and the concept experiment | the retrieval comparison on Postgres (measurement first), embedding table, keyword search, fusion, search API, concept nodes with overlay, raw concept names in annotations, the lesson check as an experiment with the exit criterion of 8.3 | S5 |
| S7 Class M and questions | `ensure` and `release` messages in the poll answer, load on demand and idle unload by the worker, confirmation by heartbeat, memory check with the choice from S-1 item 2, full priorities, explanation and ask flows, language switch | S4b, S6 |
| S8 Relocation and access | reverse proxy with both names, VPN, TLS, backup to two places, the relocation drill with tombstone replay; move to the server when it exists | S1 (independent of S2 to S7) |
| S9 Editor | panel with the character, quiet marks through `code_check`, repository opt-in, local stop patterns, git hooks, MCP server with its gate | S4a; S6 for concept marks |
| S10 Terminal | the device tool with `kata term` for a local shell and for SSH in the form the spike chose, masking, spool and sending, nudge policy, delivery inside the session. Nothing is added to the shell profile. If the spike failed for SSH, the slice ships local-shell sessions plus the fallback of 5.4 | S1, S-1 item 4; S4a or S4b for hint text |
| S11 Trainer loop | trainer origin and course cookie, hosted pages, storage adapter, progress with revisions, evidence from progress, CLI import | S5, S-1 item 5; the trainer tool changes (6.5) |
| S12 Mini-course | course generation job | S11, S6 |
| S13 Batch | GPU modes, class B through the batch engine, deck and project analysis, pause of batch work for an interactive scan | S7, S5, S8 (the core must have left the workstation) |
| S14 Phone page | installable page: questions, add a link, journal | S8, S7 |
| S15 Second user | a cloud-only user end to end, distribution to a second machine (12.6), per-user threshold tuning, storage quotas, admin counts, end-to-end tests on the second browser | S8, S4a |

Left out of Milestone 0 on purpose: the initial review screen (S3a), concept-level marks (S6), the cloud path and its gate, the cost check, the journal, the full worker daemon (S4b), stream resume, automatic graded-page detection, jobs.

