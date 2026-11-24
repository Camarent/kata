---
paths: [editor/]
summary: Editor extension (VS Code API, TypeScript) - save poster with local stop patterns, quiet-mark diagnostics, git hook install command, info view stub
---
# editor

## Purpose
Client for the editor signal: a VS Code extension that posts one `editor.save` event to the core each time a document is saved, and shows a quiet mark from the server as an Information diagnostic. It also runs the device hook installer on command. Sources in `editor/src/`; the entry is `editor/src/extension.ts` (`main` in `editor/package.json:5` points at `dist/extension.js`). The build is `tsc --noEmit` (`editor/package.json:72`); tests are vitest (`editor/package.json:73`).

## Public surface
- `editor/src/extension.ts:23` `activate` registers the install command, the info view, the diagnostics collection and the save listener; `:36` `deactivate` (nothing to release).
- Model host commands (M18): `editor/src/extension.ts:27` registers each `MODELHOST_COMMAND_KINDS` entry (`editor/src/modelhost.ts:13`: `kata.modelhostUp`, `kata.modelhostUse`, `kata.modelhostMeasure`, `kata.modelhostStatus`) to the local wrapper `runModelhost` (`editor/src/extension.ts:53`), which calls `runModelhostJob` (`editor/src/modelhost.ts:47`); `editor/src/modelhost.ts:21` `USE_ENGINES` (`ollama`, `strata`, `none`); `:38` `payloadFor(kind, engine)`; `runModelhostJob` queues the job and polls its output (`:23-24` poll settings). The GPU-PC worker runs the job (see [worker](worker.md)).
- `editor/src/extension.ts:20` `INSTALL_COMMAND` = `kata.installHooks`; `:21` `SAVE_EVENT_NAME` = `save`.
- `editor/src/extension.ts:40` `runInstall` runs the installer in the first workspace folder; with no folder it shows a message and does nothing.
- `editor/src/extension.ts:74` `postSave` reads settings on each save (`:75`), calls `postEvent` with the document language and full text (`:76-83`), and applies the result only when status is `posted` (`:84-86`).
- `editor/src/poster.ts:23` `postEvent`; stop check `:31` (returns `skipped` before any network call); event body `:34-39` with `payload: { language }` only (`:38`); request `:42-49` to `${serverUrl}/v1/events` with a Bearer token; errors `:50-61` (network `:50-52`, non-200 `:53-55`, non-JSON `:57-61`) return `error` and never throw.
- `editor/src/poster.ts:16` `PostResult` = `posted` (with `messages`), `skipped`, or `error` (with `reason`).
- `editor/src/stopPatterns.ts:3` `matchesStop`; an invalid regular expression source is skipped (`:8-9`).
- `editor/src/diagnostics.ts:5` `QUIET_MARK_MESSAGE` = `Kata: quiet mark`; `:9` `applyMessages` sets one Information diagnostic at line 0 when a `quiet_mark` message is present (`:14-18`), else clears the document's diagnostic (`:20`).
- `editor/src/installHooks.ts:33` `installHooks` runs `python3 -m kata_device hooks install` (`:17-18`) in the workspace; `:21` `runExecFile` is the default runner over `node:child_process`. Never throws: a failure returns `ok: false` with the reason (`:37-39`).
- `editor/src/config.ts:3` `KataConfig` (`serverUrl`, `token`, `stopPatterns`); `:11` `readConfig` takes an injected getter and maps a missing or mistyped value to empty.
- `editor/src/infoView.ts:11` `registerInfoView`; `:5` `INFO_TEXT` is the stub text `Kata panel (stub)`.
- Settings and contributions in `editor/package.json`: `kata.serverUrl` (`:50`), `kata.token` (`:55`), `kata.stopPatterns` (`:60`, regular expressions), command `kata.installHooks` (`:18`), view `kata.infoView` (`:42`), activation (`:6`).
- Server route the poster calls: `POST /v1/events` (`core/kata_core/api/routes/events.py:99`; contract in `docs/api.md`, section for `POST /v1/events`).

## Key files
- `editor/src/extension.ts` - activation and the save-to-post wiring.
- `editor/src/poster.ts` - the one place that builds the event body and calls the server.
- `editor/src/stopPatterns.ts` - local stop check, run on the document text before posting.
- `editor/src/diagnostics.ts` - quiet-mark rendering.
- `editor/src/installHooks.ts` - starts the device installer; the hook files are written by `core/kata_device/hooks.py`.
- `editor/src/config.ts` - settings reader.
- `editor/src/modelhost.ts` - model host control commands: payloads, engine list, job polling.
- `editor/src/vscode.d.ts` - the VS Code API surface the sources use.
- `editor/tests/` - vitest suites for the modules above.

## Invariants and gotchas
- Privacy: no document text leaves the editor. The body carries `type` `editor.save`, `occurred_at`, a random `event_id` and `payload: { language }`. The full text is read only for the stop check (`editor/src/poster.ts:2`).
- A document whose text matches any `kata.stopPatterns` entry posts nothing, not even a `skipped` marker on the server. The check is local and runs before the network call.
- The poster never throws. A network error, a non-200 answer or a non-JSON body is `error`; no retry, no queue. Only `posted` updates diagnostics.
- Settings are read on every save, so a change applies without a reload (`editor/src/extension.ts:2`).
- Dev dependencies are pinned to exact versions in `editor/package.json:76-80`; the lock file is `editor/package-lock.json`. See `docs/decisions.md`.
- The info view is a stub; the real panel comes in a later task.
- The Node version is not pinned in `editor/`: TODO(verify) (no `engines` field and no `.nvmrc` in `editor/`; the root `.nvmrc` pins Node 26).

## Depends on / used by
- Depends on: VS Code extension host API (`vscode`); Node for `build` and `test` (`npm --prefix editor`); `python3` with the `kata_device` package for the install command; the core `POST /v1/events` route (`docs/api.md`).
- Used by: `scripts/dev/check-all.sh --editor` runs `npm --prefix editor run build` and `run test:cov` (`scripts/dev/check-all.sh:146-148`); CI runs `npm --prefix editor run build` and `npm --prefix editor test` (no coverage) (`.github/workflows/ci.yml:58-60`).
