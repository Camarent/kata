# API, provisioning and enrolment guide

This guide covers the core HTTP API, the skill list file format, the database and admin CLIs, and how to run the tests.

## Conventions

- Base address: the core listens on `core.host` and `core.port` (defaults `127.0.0.1` and `8080`).
- Bodies are JSON unless noted. Responses are JSON unless the status is 204 (no body).
- Every route except `POST /auth/enrol`, `GET /v1/health/deep` and `GET /c/{token}/{path}` needs `Authorization: Bearer <token>`. A missing or malformed header returns 401 `missing bearer token`. An unknown or revoked token returns 401 `invalid or revoked token`.
- The user id always comes from the token, never from the body or the path.
- A route marked with a feature (`trainer`, `syllabus`, `planning`) answers 404 `{"detail": "feature disabled: <name>"}` when that feature is off in the config (`[<name>] enabled`).

## Routes

| Method | Path | Auth | Body | Success | Errors |
|---|---|---|---|---|---|
| POST | `/auth/enrol` | none | `{"code": str, "label": str}` | 200 `{"token": str, "expires_in": int}` | 401 invalid or used enrolment code |
| GET | `/auth/me` | bearer | none | 200 `{"user_id": int, "name": str}` | 401 user no longer exists |
| DELETE | `/auth/devices/{device_id}` | bearer | none | 204 | 404 device not found |
| GET | `/topics` | bearer | none | 200 list of `{"id", "category", "label", "private"}` | |
| POST | `/topics` | bearer | `{"category": str, "label": str, "private": bool = false}` | 200 `{"id", "category", "label", "private"}` | 422 on empty fields |
| POST | `/topics/{topic_id}/aliases` | bearer | `{"alias": str}` | 200 `{"id", "topic_id", "alias", "private": true}` | 404 topic not found |
| POST | `/import` | bearer | raw UTF-8 text, skill list format (see below) | 200 `{"created_topics": int, "marked": int}` | 422 bad line or body not UTF-8; nothing changes |
| POST | `/jobs` | bearer | `{"payload": str}` | 200 `{"id": int}` | 422 a `modelhost.*` kind whose payload its allow-list refuses (`core/kata_core/api/routes/jobs.py:96-100`); nothing queued |
| GET | `/jobs/next?kind=` | bearer | query: repeated `kind`, optional | 200 `{"id": int, "payload": str}` | 204 nothing queued; no `kind` means `tag` only |
| POST | `/jobs/{job_id}/result` | bearer | `{"category": str, "topic": str}` | 204 | 404 job not found or not leased by the caller |
| POST | `/jobs/{job_id}/fail` | bearer | none | 204 | 404 job not found or not leased by the caller |
| POST | `/jobs/{job_id}/output` | bearer | `{"output": {...}}` (JSON object) | 204; runs the kind's output hook in the same transaction | 404 job not found or not leased by the caller; 413 output above `[jobs] max_output_bytes`; 422 the job kind has no output hook (nothing stored) |
| GET | `/jobs/{job_id}` | bearer | none | 200 `{"status": str, "topic": {"id", "category", "label"} or null, "known": bool or null, "output": object or null}` | 404 job not found |
| POST | `/v1/courses` | bearer, `trainer` feature | `{"concept_ids": [int, ...] \| null, "title": str = "", "learning_rung": int 0..3 \| null}`; `learning_rung` null takes `trainer.learning_start_rung` | 202 course fields plus `"job_id"` | 409 `course_limit` at `[trainer] max_courses_per_user` (any status counts); 409 `course_name_taken` for a title the user already has (case, spaces and ends ignored); 422 `course_title_empty` for an empty or whitespace title; 422 the gap rule finds nothing to study, or a named concept is not visible to the caller |
| GET | `/v1/courses?limit=50&before_id=N` | bearer, `trainer` feature | query: `limit` 1..100 (default 50), `before_id` optional | 200 `{"items": [course, ...], "next_before_id": int \| null, "limit": int, "total": int}`, newest first; `limit` is the course limit (0 means unlimited), `total` counts all the caller's courses | 422 `limit` outside 1..100; `next_before_id` is null unless the page is full |
| GET | `/v1/courses/{course_id}` | bearer, `trainer` feature | none | 200 course: `{"id", "title", "status", "concept_ids", "error", "created_at", "updated_at"}` | 404 course not found or not the caller's |
| DELETE | `/v1/courses/{course_id}` | bearer, `trainer` feature | none | 204 | 404 course not found or not the caller's |
| GET | `/v1/courses/{course_id}/regenerate-preview` | bearer, `trainer` feature | none | 200 `{"carried": [item], "added": [item], "dropped": [item]}`, item `{"id", "label", "state"}` (`state` new, learning, known or `missing`); nothing is written | 404 course not found or not the caller's |
| POST | `/v1/courses/{course_id}/regenerate` | bearer, `trainer` feature | none | 202 course fields plus `"job_id"`; same course id, no new course row (D35) | 404 course not found or not the caller's; 409 `course_busy` while queued, generating or building; 409 `needs_cloud` as for create; 422 `nothing_to_study` when no concept is left |
| POST | `/v1/lists` | bearer | `{"name": str}` | 200 `{"id", "name", "item_count"}` | 409 list name already taken; 422 blank name |
| GET | `/v1/lists` | bearer | none | 200 list of `{"id", "name", "item_count"}`, in name order | |
| GET | `/v1/lists/concept/{concept_id}` | bearer | none | 200 list of `{"id", "name", "item_count"}`: the caller's lists that hold the concept | 404 concept not visible to the caller |
| PATCH | `/v1/lists/{list_id}` | bearer | `{"name": str}` | 200 `{"id", "name", "item_count"}` | 404 list not found or not the caller's; 409 name taken; 422 blank name |
| DELETE | `/v1/lists/{list_id}` | bearer | none | 204; deletes the list and its items, courses made from it are kept | 404 list not found or not the caller's |
| POST | `/v1/lists/{list_id}/concepts` | bearer | `{"concept_ids": [int, ...]}` (at least one id) | 200 `{"added": int}`; re-adding is not an error | 404 list not found or not the caller's; 422 a concept is unknown or not visible (nothing added) |
| POST | `/v1/lists/{list_id}/topics/{topic_id}` | bearer | none | 200 `{"added": int}`: every concept of the topic | 404 list or topic not found or not the caller's |
| DELETE | `/v1/lists/{list_id}/concepts/{concept_id}` | bearer | none | 204 | 404 concept not in the list, or list not the caller's |
| POST | `/v1/lists/{list_id}/course` | bearer, `trainer` feature | `{"title": str, "learning_rung": int 0..3 \| null}` | 202 course fields plus `"job_id"`; the list is kept | 404 list not found or not the caller's; 422 list has no concepts, a concept is not visible, or the title is empty; other course errors as `POST /v1/courses` |
| POST | `/v1/tracks/{track_id}/goals` | bearer, `planning` feature | `{"name": str, "deadline": date \| null}` | 201 goal: `{"id", "track_id", "name", "deadline", "created_at", "known", "total", "progress", "velocity_per_day", "pace", "projected_finish"}` | 404 track not found or not the caller's |
| GET | `/v1/tracks/{track_id}/goals` | bearer, `planning` feature | none | 200 list of goal (same shape as above) | 404 track not found or not the caller's |
| DELETE | `/v1/tracks/{track_id}/goals/{goal_id}` | bearer, `planning` feature | none | 204; deletes the goal with its sources and concept links | 404 goal not on the track or not the caller's |
| POST | `/v1/tracks/{track_id}/goals/{goal_id}/sources` | bearer, `planning` feature | `{"kind": "text" \| "file" \| "page", "label": str, "body": str, "concept_ids": [int, ...] = []}` | 201 `{"id", "goal_id", "kind", "label", "body", "added_at"}`; nothing stored when a concept is unknown or private | 404 goal not on the track; 422 unknown or private concept |
| DELETE | `/v1/tracks/{track_id}/goals/{goal_id}/concepts/{concept_id}` | bearer, `planning` feature | none | 204 | 404 goal not on the track |
| POST | `/v1/tracks/{track_id}/goals/{goal_id}/list` | bearer, `planning` feature | `{"name": str}` | 201 `{"id", "name", "item_count"}`: a new list of the goal's concepts that are not known | 404 goal not on the track; 409 name taken; 422 blank name |
| GET | `/v1/courses/{course_id}/progress` | bearer, `trainer` feature | none | 200 `{"revision": int, "doc": {...}}`, with `ETag: "<revision>"` | 404 course not found or not the caller's |
| PUT | `/v1/courses/{course_id}/progress[?import=1]` | bearer, `trainer` feature; `If-Match: "<revision>"` required | progress document JSON object; `?import=1` stores it and writes no evidence (`evidence_written` 0) | 200 `{"revision", "evidence_written", "skipped_items"}`, with `ETag` | 428 no `If-Match`; 400 `If-Match` not a revision number or body malformed; 413 above `[trainer] max_progress_bytes`; 412 revision mismatch, body `{"revision", "doc"}` holds the current document; 409 course not ready; 404 course not found or not the caller's |
| PATCH | `/v1/courses/{course_id}/progress` | bearer, `trainer` feature; `If-Match: "<revision>"` required | delta: `{"items": {"<item_id>": {"ok", "bad"}}}`, other keys replace stored keys | 200 `{"revision", "evidence_written", "skipped_items"}`, with `ETag` | same as PUT; 412 also when no document is stored yet, body `{"revision": 0, "doc": null}`: PUT first |
| POST | `/v1/courses/{course_id}/open` | bearer, `trainer` feature | none | 200 `{"url": str}`: a signed link to `/c/<token>/index.html` (base from `[core] public_url`, else the request URL) | 404 `course not found` (missing or foreign); 409 `course is <status>, not ready` |
| GET | `/c/{token}/{path}` | none: the signed token in the path is the credential; `trainer` feature | none | 200 the artifact bytes with its media type and the headers in the notes below (empty path serves `index.html`) | 404 `not found` for every failure: bad, expired or forged token, bad path, foreign or non-ready course, missing file |
| POST | `/v1/syllabi` | bearer, `syllabus` feature | `{"title": str, "text": str}` | 201 syllabus with its modules and triage; 202 `{...syllabus, "job_id": int}` when `[syllabus] model_extract` is on and the parser found no structure (queues `syllabus.extract`) | 413 text over `[syllabus] max_bytes`; 422 blank text or parse error |
| GET | `/v1/syllabi?limit=50&before_id=N` | bearer, `syllabus` feature | query: `limit` 1..100 (default 50), `before_id` optional | 200 `{"items": [{"id", "title", "status", "created_at", "module_count"}], "next_before_id": int \| null}`, newest first | 422 `limit` outside 1..100; `next_before_id` is null unless the page is full |
| GET | `/v1/syllabi/{syllabus_id}` | bearer, `syllabus` feature | none | 200 syllabus: `{"id", "title", "status", "created_at", "modules": [{"id", "position", "title", "triage", "action", "effort_minutes"}]}` | 404 syllabus not found or not the caller's |
| DELETE | `/v1/syllabi/{syllabus_id}` | bearer, `syllabus` feature | none | 204 | 404 syllabus not found or not the caller's |
| POST | `/v1/tracks` | bearer, `planning` feature | `{"name": str, "deadline": date, "priority": int = 0, "items": [item, ...] = []}`; item: `module_id` int or `label` + `minutes` int, `action` str = `learn` | 201 track; journal `plan.track_changed` (`change` `created`) | 422 invalid body, or an item `module_id` not in the caller's syllabus |
| GET | `/v1/tracks?limit=50&before_id=N` | bearer, `planning` feature | query: `limit` 1..100 (default 50), `before_id` optional | 200 `{"items": [track, ...], "next_before_id": int \| null}`, newest first | 422 `limit` outside 1..100; `next_before_id` is null unless the page is full |
| GET | `/v1/tracks/{track_id}` | bearer, `planning` feature | none | 200 track: `{"id", "name", "deadline", "priority", "status", "items": [{"position", "module_id", "label", "action", "minutes"}], "created_at", "updated_at"}` | 404 track not found or not the caller's |
| PATCH | `/v1/tracks/{track_id}` | bearer, `planning` feature | any of `name`, `deadline`, `priority`, `status` (`active`, `paused`, `dropped`), `items` (replaces all items; same item shape as POST) | 200 track; journal `plan.track_changed` (`change` `updated`) | 404 track not found or not the caller's; 422 invalid body or foreign module |
| DELETE | `/v1/tracks/{track_id}` | bearer, `planning` feature | none | 204; deletes the track with its items and points; journal `plan.track_changed` (`change` `deleted`) | 404 track not found or not the caller's |
| POST | `/v1/tracks/{track_id}/decision-points` | bearer, `planning` feature | `{"after_position": int >= 0, "due_on": date}` | 201 point: `{"id", "track_id", "after_position", "due_on", "status", "choice", "target_track_id", "decided_at", "created_at"}`; no journal entry | 404 track not found or not the caller's; 422 invalid body |
| POST | `/v1/decision-points/{point_id}/decide` | bearer, `planning` feature | `{"choice": "continue" \| "switch" \| "drop", "target_track_id": int \| null}` | 200 point (same shape as above); journal `plan.decision` with `point_id`, `choice`, `target_track_id`, in the same transaction as the track change | 404 point missing, not the caller's, already decided, or a switch target that is not the caller's track; 422 unknown `choice` |
| GET | `/v1/plan/budget` | bearer, `planning` feature | none | 200 `{"minutes_per_week": int \| null}`; null when no budget is set | |
| PUT | `/v1/plan/budget` | bearer, `planning` feature | `{"minutes_per_week": int >= 0}` | 200 `{"minutes_per_week": int}`; journal `plan.budget_changed` | 422 negative or non-integer minutes |
| GET | `/v1/plan` | bearer, `planning` feature | none | 200 `{"tracks": [{"track_id", "allocated": [{"position", "minutes"}], "deferred": [int]}]}`: per track, the placed items and the deferred item positions; no journal entry | |
| GET | `/marks` | bearer | none | 200 list of `{"topic_id", "category", "topic", "status"}` | |
| PUT | `/marks/{topic_id}` | bearer | `{"status": "known"}` | 200 `{"topic_id", "category", "topic", "status"}` | 404 topic not found |
| DELETE | `/marks/{topic_id}` | bearer | none | 204 | 404 mark not found |
| POST | `/concepts` | bearer | `{"topic_id": int, "label": str}` | 200 `{"id", "topic_id", "label"}` | 404 topic not found |
| GET | `/concepts/marks` | bearer | none | 200 list of `{"concept_id", "label", "state", "evidence", "created_at", "updated_at"}` | |
| PUT | `/concepts/{concept_id}/mark` | bearer | `{"state": "known" \| "learning" \| "new", "evidence": str = ""}` | 200 `{"concept_id", "label", "state", "evidence", "created_at", "updated_at"}` | 404 concept not found; 422 unknown state |
| DELETE | `/concepts/{concept_id}/mark` | bearer | none | 204 | 404 mark not found |
| GET | `/concepts/sorted?sort=name\|added\|viewed\|relevance&order=asc\|desc` | bearer | query: `sort` (default `name`), `order` (default `asc`) | 200 list of `{"concept_id", "label", "state", "added_at", "last_viewed_at", "relevance"}`, ignored concepts left out | 422 unknown `sort` or `order` |
| POST | `/concepts/block-state` | bearer | `{"concept_ids": [int, ...]}` (at least one id) | 200 `{"state": "new" \| "learning" \| "known" \| "mixed"}` | 404 a concept is not visible to the caller; 422 empty list |
| POST | `/concepts/{concept_id}/viewed` | bearer | none | 204 (stamps `last_viewed_at`) | 404 concept not found |
| POST | `/concepts/{concept_id}/aliases` | bearer | `{"alias": str}` (at least one character) | 200 `{"id", "concept_id", "alias", "private": true}` | 404 concept not found; 409 alias already exists |
| GET | `/concepts/{concept_id}/aliases` | bearer | none | 200 list of `{"id", "concept_id", "alias", "private"}`: shared aliases and the caller's own | 404 concept not found |
| PUT | `/concepts/{concept_id}/definition` | bearer | `{"definition": str}` | 204 | 404 concept not found |
| GET | `/concepts/ignored` | bearer | none | 200 list of `{"concept_id", "label"}`, ordered by concept id | |
| PUT | `/concepts/{concept_id}/ignore` | bearer | none | 204 (marks are kept) | 404 concept not found |
| DELETE | `/concepts/{concept_id}/ignore` | bearer | none | 204 | 404 concept not ignored |
| DELETE | `/concepts/{concept_id}` | bearer | none | 204 (removes the concept with its marks, aliases and ignore rows) | 404 concept not found; 403 shared concept |
| GET | `/scan/classification?page_key=` | bearer | query: `page_key` (the page URL without fragment) | 200 `{"topic_id", "area", "topic", "candidates": [{"topic_id", "area", "topic"}]}`; candidates with no visible topic are dropped | 404 no classification for the page, or its topic is not visible |
| POST | `/scan/choice` | bearer | `{"topic_id": int, "word": str (1..200 chars), "concept_id": int}` | 204 (remembers the concept for the word in the topic) | 404 topic or concept not visible; 422 concept not in the topic |
| POST | `/scan/reassign` | bearer | `{"topic_id": int, "word": str, "from_concept_id": int, "to_concept_id": int}` | 204 (moves the word to the other concept, teaches the alias, remembers the choice; marks unchanged) | 404 topic or concept not found; 422 concept not in the topic |
| GET | `/scan/overview?topic_id=` | bearer | query: `topic_id` | 200 `{"topicId", "area", "topic", "counts": {"new", "learning", "known"}, "concepts": [{"conceptId", "label", "state"}]}`; ignored concepts left out | 404 topic not found or not visible |
| POST | `/lesson-check` | bearer | `{"concept_ids": [int, ...]}` (at least one id) | 200 `{"results": [{"concept_id", "label", "state", "source", "evidence"}]}`, in input order | 404 a concept is not visible to the caller (nothing partial); 422 empty or non-integer list |
| POST | `/usage` | bearer | `{"micro_usd": int}` (>= 0) | 204 | 422 negative or non-integer `micro_usd` |
| GET | `/usage` | bearer | none | 200 `{"day": "YYYY-MM-DD", "micro_usd": int, "calls": int}` (UTC day) | zeros when nothing recorded |
| GET | `/v1/journal?limit=50&before_id=N` | bearer | query: `limit` 1..200 (default 50), `before_id` optional | 200 `{"items": [{"id", "kind", "detail", "created_at"}], "next_before_id": int \| null}`, newest first | 422 `limit` outside 1..200; `next_before_id` is null unless the page is full |
| POST | `/v1/events` | bearer | `{"events": [raw event, ...]}` (at most 100, see Events) | 200 `{"results": [{"event_id", "status", "reason"}], "messages": [message, ...]}`, results in input order | 422 more than 100 events or body not in that shape; a bad event is reported in `results` and never fails the batch |
| GET | `/v1/messages` | bearer | none | 200 `{"messages": [message, ...]}`, oldest first, at most 50 | |
| GET | `/v1/health/deep` | none | none | 200 `{"status": "ok", "checks": {"db", "migrations"}}` | 503 `{"status": "fail", "failed": [...], "checks"}` when the database is unreachable or migrations are pending |
| GET | `/capabilities` | none | none | 200 capabilities document, schema 2 (`models`, `fits_together`, `loaded_now`) | not a core route: served by the model host info service at `[modelhost] info_url` (default `http://127.0.0.1:11435`); the worker reads it, see [worker](modules/worker.md) |
| POST | `/mcp` | bearer, `mcp` scope | one JSON-RPC 2.0 message (see MCP below) | 200 JSON-RPC reply; 204 for a valid notification (no `id`) | 401 missing, invalid or revoked token, or an `api` token; 200 with JSON-RPC error `-32700` for bad JSON |

Notes:

- `GET /jobs/next` answers 204 when nothing is queued. The worker polls it; there is no push channel.
- `modelhost.up`, `modelhost.use`, `modelhost.measure` and `modelhost.status` are queued with `POST /jobs` and read back with `GET /jobs/{job_id}`. The worker posts `{ok, text[, capabilities]}` with `POST /jobs/{job_id}/output`; the hook checks it (`core/kata_core/modelhost/job_kinds.py:18`) and `output` stays null until then (`core/kata_core/api/routes/jobs.py:72`). Only the GPU-PC worker claims them.
- `known` in `GET /jobs/{job_id}` is computed from the caller's marks. The model only picks the topic.
- A topic created with `private: false` (the default) is shared. A private topic and a private alias belong to the caller.
- Concept marks are a second layer under topics. `state` is `known`, `learning` or `new`; a concept is visible when its topic is visible and it is shared or owned by the caller. `GET /concepts/marks` lists only the caller's marks. Topic marks (`/marks`) are unchanged.
- A concept made through `POST /concepts` belongs to its creator. A repeated label under the same topic and owner hits the unique index; the route does not map that error to a 4xx yet.
- `POST /lesson-check` gives the state of each concept for the caller. `state` is `known`, `learning` or `abstain` from retrieval; a caller's mark gives its own state, which may be `new`. Retrieval never gives `new`: it cannot prove absence. `source` is `mark` when the caller's concept mark decides; then `evidence` is the mark's text. Otherwise `source` is `retrieval` and `evidence` is a list of `{"source_ref", "score"}` hits. An abstain has `source` `none` and `evidence` `[]`. The user id comes from the token, never from the body.
- `POST /v1/courses` queues the worker job `course.generate`. Its output hook checks the drafts with the trainer and queues `course.build`, which builds the course or sets its `error`. The course `status` follows these two jobs.
- A course title is unique per user after normalisation (lower case, trimmed, runs of whitespace as one space). Existing duplicates were renamed with a ` (k)` suffix by migration `0014`. The count and the insert run under a row lock on the user, so two creates cannot both pass the limit. Errors use `detail: {"code", "message"}`; the 404 stays plain text.

### Open links (`/c/*`)

- `POST /v1/courses/{id}/open` returns a link signed with the open-link key (`[trainer] open_link_key_file`, at least 32 bytes). The link stays valid until `[trainer] open_link_ttl_seconds` from now. The user id comes from the bearer token, never from the path.
- `GET /c/{token}/{path}` serves one artifact of a READY course. The route takes no bearer token and is left out of the OpenAPI schema. With the `trainer` feature off it answers 404 `feature disabled: trainer`, like other trainer routes. Otherwise every failure answers the same 404 `not found` with the same headers, so a probe learns nothing.
- Success headers: `Cache-Control: private, max-age=0, must-revalidate`, `Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
- The files use relative URLs and need HTTP; `file://` does not work.

## Events and messages

`POST /v1/events` ingests a batch of device events. `GET /v1/messages` returns the caller's pending messages on their own. The user and device ids come from the token, never from the body.

Batch: `events` is a list of at most 100 raw events. A longer list returns 422. Each raw event is an object with these fields:

- `event_id`: string, 1 to 64 characters. The pair (user, `event_id`) is unique.
- `type`: string. Known types are `terminal.command`, `terminal.error` and `editor.<name>` (a non-empty name after `editor.`).
- `occurred_at`: ISO 8601 string with a time zone offset.
- `payload`: JSON object.

Each event gets one result, in input order: `{"event_id", "status", "reason"}`. `event_id` is null when the raw event has no string `event_id`. `reason` appears only for `rejected`.

- `accepted`: the event is stored and goes to the policy.
- `duplicate`: the (user, `event_id`) pair is already stored. The payload is ignored; nothing is inserted.
- `rejected`: the event is refused. The checks run in this order, and the first failure is the reason:
  - `bad_envelope`: the raw event is not an object, a field is missing or has the wrong type, `event_id` length is outside 1..64, or `occurred_at` is not ISO 8601 with an offset.
  - `unknown_type`: `type` is not a known type.
  - `clock_skew`: `occurred_at` is more than `MAX_FUTURE_SKEW_SECONDS` 300 seconds after the server time. An event older than the server time is accepted here; the policy decides whether late events count.

Only accepted events reach the policy. Its decisions are queued as messages for the caller. A message has this shape: `{"id": int, "kind", "body": {"at": ISO 8601, "detail": object}, "created_at": ISO 8601}`. Decision kinds are `quiet_mark`, `nudge` and `stop`.

Piggyback: the `messages` in the `POST /v1/events` response are the caller's pending messages, delivered in that same response after the batch is ingested.

Delivery is at-most-once. Each message is returned once: when it is returned, its `delivered_at` is set, and it is never sent again. `GET /v1/messages` and the piggyback both take up to 50 pending messages, oldest first. For each delivered message the server writes one journal entry of kind `message_delivered` with detail `{"message_id", "kind"}`; `GET /v1/journal` shows these entries.

## MCP

`POST /mcp` answers one JSON-RPC 2.0 message per request body. It takes only tokens of scope `mcp` (issued by `mint-mcp-token`). The user id comes from the token, never from the message. Batches are not supported: a JSON array gets `-32600`.

Methods:

- `initialize`: returns protocol version `2025-06-18`, capability `tools`, and server info `kata`.
- `notifications/initialized` and any valid notification (`jsonrpc: "2.0"`, string `method`, no `id`): no reply, HTTP 204. A malformed message without `id` still gets a `-32600` error reply (HTTP 200).
- `tools/list`: returns the two tools below with their input schemas.
- `tools/call`: runs one tool by `name` with `arguments`.

Tools:

- `kata_search` (`query` string, `limit` integer): visible entries for the query, one `[source_ref] body` line each, best first. `limit` is clamped to 1..10; default 5.
- `kata_concept_state` (`concept` string, 1 to 80 letters, digits, spaces, hyphens, underscores or dots): state and evidence of the caller's mark on that concept, or `no mark`.

Every tool result passes the MCP gate before it is returned (`core/kata_core/mcp/gate.py`). An allowed result is quoted: a fixed data sentence, then each line prefixed `> `. A result over 4096 UTF-8 bytes, or with a secret finding, is blocked: the tool returns `isError: true` with no data, and the core writes one `egress_block` journal entry naming the tool and the rule.

Error codes (JSON-RPC `error.code`):

| Code | Meaning |
|---|---|
| -32700 | parse error: body is not valid JSON or UTF-8 |
| -32600 | invalid request: batch, non-object message, missing `jsonrpc: "2.0"` or string `method`, non-object `params` |
| -32601 | method not found |
| -32602 | invalid params: bad tool name, missing or wrongly typed argument, bad concept name |

Tool errors from the gate are not JSON-RPC errors: they come back as a normal result with `isError: true`.

## Skill list file format

The file is UTF-8 text, one skill per line:

```
Category / Topic
Category / Topic = Alias
# a comment line
```

- Blank lines and lines starting with `#` are ignored.
- Whitespace around names is trimmed.
- An optional `= Alias` suffix after the topic adds an alias.
- A malformed line returns 422 with the 1-based line number. An import with a malformed line changes nothing.

## Provisioning

### Configuration

The CLIs and the core read a TOML file. Its path comes from the `KATA_CONFIG` environment variable, or from `--config` where the CLI accepts it. Each key can be overridden by an environment variable named in the README. The example file is `config/kata.example.toml`.

The database password is not in the file. The file names an environment variable in `[database] password_env`; set that variable to the password.

### Core server

Run from the repository root with the core package on the path. The server listens on the `[core]` `host` and `port`:

```
PYTHONPATH=core python3 -m kata_core
```

### Database CLI

Run from the repository root with the core package on the path:

```
PYTHONPATH=core python3 scripts/db/kata_db.py create NAME
PYTHONPATH=core python3 scripts/db/kata_db.py migrate [--name NAME]
PYTHONPATH=core python3 scripts/db/kata_db.py drop NAME
```

- `create NAME` creates a database.
- `migrate` applies pending migrations to the configured database, or to `--name`.
- `drop NAME` drops a database if it exists.

### Admin CLI

Users exist only because an admin created them. There is no self sign-up.

```
PYTHONPATH=core python3 -m kata_core.auth.admin create-user NAME
PYTHONPATH=core python3 -m kata_core.auth.admin enrol USER_NAME
PYTHONPATH=core python3 -m kata_core.auth.admin revoke DEVICE_ID
PYTHONPATH=core python3 -m kata_core.auth.admin mint-mcp-token USER_NAME LABEL
```

- `create-user NAME` creates a user and prints its id.
- `enrol USER_NAME` prints an enrolment code once. The code is not stored. The user redeems it with `POST /auth/enrol`.
- `revoke DEVICE_ID` revokes an active device, so its token stops working.
- `mint-mcp-token USER_NAME LABEL` issues a device token of scope `mcp` (stored in `devices.scope`) and prints it once (`core/kata_core/auth/admin.py:39`). Use it for an assistant that calls `POST /mcp`; the token does not work on the `api` routes.

## Enrolment flow

1. An admin runs `create-user` once for the person.
2. The admin runs `enrol` for that user and passes the printed code to the person.
3. The person's client calls `POST /auth/enrol` with the code and a device label. The code works once.
4. The response carries the raw token once. The client stores it and sends it as `Authorization: Bearer <token>`.
5. `DELETE /auth/devices/{device_id}` or `revoke` ends a device's access.

## Tests

The tests need a reachable Postgres server. The database user named in the configuration must have the `CREATEDB` privilege, because the tests create and drop their own databases. Point the tests at the server with a config file set in `KATA_CONFIG`, and set the password environment variable it names. The tests fail, and do not skip, when Postgres is unreachable.

```
KATA_CONFIG=path/to/kata.toml python3 -m pytest tests
```
