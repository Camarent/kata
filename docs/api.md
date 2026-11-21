# API, provisioning and enrolment guide

This guide covers the core HTTP API, the skill list file format, the database and admin CLIs, and how to run the tests.

## Conventions

- Base address: the core listens on `core.host` and `core.port` (defaults `127.0.0.1` and `8080`).
- Bodies are JSON unless noted. Responses are JSON unless the status is 204 (no body).
- Every route except `POST /auth/enrol` needs `Authorization: Bearer <token>`. A missing or malformed header returns 401 `missing bearer token`. An unknown or revoked token returns 401 `invalid or revoked token`.
- The user id always comes from the token, never from the body or the path.

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
| POST | `/jobs` | bearer | `{"payload": str}` | 200 `{"id": int}` | |
| GET | `/jobs/next` | bearer | none | 200 `{"id": int, "payload": str}` | 204 nothing queued |
| POST | `/jobs/{job_id}/result` | bearer | `{"category": str, "topic": str}` | 204 | 404 job not found or not leased by the caller |
| POST | `/jobs/{job_id}/fail` | bearer | none | 204 | 404 job not found or not leased by the caller |
| GET | `/jobs/{job_id}` | bearer | none | 200 `{"status": str, "topic": {"id", "category", "label"} or null, "known": bool or null}` | 404 job not found |
| GET | `/marks` | bearer | none | 200 list of `{"topic_id", "category", "topic", "status"}` | |
| PUT | `/marks/{topic_id}` | bearer | `{"status": "known"}` | 200 `{"topic_id", "category", "topic", "status"}` | 404 topic not found |
| DELETE | `/marks/{topic_id}` | bearer | none | 204 | 404 mark not found |
| POST | `/concepts` | bearer | `{"topic_id": int, "label": str}` | 200 `{"id", "topic_id", "label"}` | 404 topic not found |
| GET | `/concepts/marks` | bearer | none | 200 list of `{"concept_id", "label", "state", "evidence", "created_at", "updated_at"}` | |
| PUT | `/concepts/{concept_id}/mark` | bearer | `{"state": "known" \| "learning" \| "new", "evidence": str = ""}` | 200 `{"concept_id", "label", "state", "evidence", "created_at", "updated_at"}` | 404 concept not found; 422 unknown state |
| DELETE | `/concepts/{concept_id}/mark` | bearer | none | 204 | 404 mark not found |
| POST | `/lesson-check` | bearer | `{"concept_ids": [int, ...]}` (at least one id) | 200 `{"results": [{"concept_id", "label", "state", "source", "evidence"}]}`, in input order | 404 a concept is not visible to the caller (nothing partial); 422 empty or non-integer list |
| POST | `/usage` | bearer | `{"micro_usd": int}` (>= 0) | 204 | 422 negative or non-integer `micro_usd` |
| GET | `/usage` | bearer | none | 200 `{"day": "YYYY-MM-DD", "micro_usd": int, "calls": int}` (UTC day) | zeros when nothing recorded |
| GET | `/v1/journal?limit=50&before_id=N` | bearer | query: `limit` 1..200 (default 50), `before_id` optional | 200 `{"items": [{"id", "kind", "detail", "created_at"}], "next_before_id": int \| null}`, newest first | 422 `limit` outside 1..200; `next_before_id` is null unless the page is full |
| POST | `/v1/events` | bearer | `{"events": [raw event, ...]}` (at most 100, see Events) | 200 `{"results": [{"event_id", "status", "reason"}], "messages": [message, ...]}`, results in input order | 422 more than 100 events or body not in that shape; a bad event is reported in `results` and never fails the batch |
| GET | `/v1/messages` | bearer | none | 200 `{"messages": [message, ...]}`, oldest first, at most 50 | |

Notes:

- `GET /jobs/next` answers 204 when nothing is queued. The worker polls it; there is no push channel.
- `known` in `GET /jobs/{job_id}` is computed from the caller's marks. The model only picks the topic.
- A topic created with `private: false` (the default) is shared. A private topic and a private alias belong to the caller.
- Concept marks are a second layer under topics. `state` is `known`, `learning` or `new`; a concept is visible when its topic is visible and it is shared or owned by the caller. `GET /concepts/marks` lists only the caller's marks. Topic marks (`/marks`) are unchanged.
- A concept made through `POST /concepts` belongs to its creator. A repeated label under the same topic and owner hits the unique index; the route does not map that error to a 4xx yet.
- `POST /lesson-check` gives the state of each concept for the caller. `state` is `known`, `learning` or `abstain` from retrieval; a caller's mark gives its own state, which may be `new`. Retrieval never gives `new`: it cannot prove absence. `source` is `mark` when the caller's concept mark decides; then `evidence` is the mark's text. Otherwise `source` is `retrieval` and `evidence` is a list of `{"source_ref", "score"}` hits. An abstain has `source` `none` and `evidence` `[]`. The user id comes from the token, never from the body.

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
```

- `create-user NAME` creates a user and prints its id.
- `enrol USER_NAME` prints an enrolment code once. The code is not stored. The user redeems it with `POST /auth/enrol`.
- `revoke DEVICE_ID` revokes an active device, so its token stops working.

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
