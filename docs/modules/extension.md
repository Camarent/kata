---
paths: [extension/]
summary: Browser extension (WebExtension MV3, TypeScript) - manifest, npm package, and sources in src/ (background, content script, side panel, core client, offline queue)
---
# extension

## Purpose
Client for Milestones 0 and 2: a Manifest V3 browser extension that scans the open lesson page, shows topic marks in a side panel, and (Milestone 2) offers a review screen to set the user's concept marks. Sources in `extension/src/`; the build (`extension/build/build.mjs`) bundles `background.ts` (ESM), `content.ts` (IIFE) and `sidepanelBoot.ts` (ESM) into `dist/<browser>/` for `chrome` and `firefox`. The e2e test bundles the same modules through `tests/e2e/driver.ts`.

## Public surface
- `extension/manifest.base.json:3` name `kata`; `:5` shared permissions `storage`, `activeTab`, `scripting`, `permissions`; `:6` optional host permissions `http://*/*`, `https://*/*` (the saved server's origin is granted at sign-in, never at build time); `:9` content script match `http://*/*`, `https://*/*`; `:10` content script `content.js`.
- `extension/build/manifest.mjs` Chrome adds permission `sidePanel` and `side_panel`, service worker `background.js`; Firefox `sidebar_action`, background `scripts`, `gecko` id `kata@kata.invalid`, min version `128.0`.
- `extension/build/build.mjs` `composeManifest` output and bundles written per browser to `dist/<browser>/`.
- `extension/src/browser.ts:15` `openPanel` (`sidePanel` on Chrome, `sidebarAction` on Firefox).
- `extension/package.json:7` `build` = `tsc --noEmit && node build/build.mjs`; `:8` `test` = `vitest run`; devDependencies `esbuild`, `jsdom`, `typescript`, `vitest`.
- `extension/tsconfig.json:6` `strict: true`; `:7` `outDir: dist`.
- `extension/src/background.ts:125` `createBackend`, `:342` `wireBackground`.
- `extension/src/content.ts:23` `handleContentMessage`, `:44` `registerContentScript`.
- `extension/src/scanner.ts:96` `scanBlocks`; `extension/src/scanSession.ts:33` `runScan`.
- `extension/src/coreClient.ts:202` `CoreClient`; `:313` `listConceptMarks`, `:318` `setConceptMark` (concept marks); error classes `CoreTimeoutError`, `CoreOfflineError`, `CoreAuthError`, `CoreHttpError`.
- `extension/src/offlineQueue.ts:64` `OfflineQueue`.
- `extension/src/tokenStore.ts:21` `TokenStore`.
- `extension/src/sidepanel.ts:420` `renderPanel`; `extension/src/sidepanelBoot.ts:33` `bootPanel`.
- Needs-cloud text: `extension/src/coreClient.ts:144` `courseErrorText` maps a 409 `needs_cloud` to "This needs a cloud model. Add a cloud token to turn it on." (`:153-154`); the side panel create note shows it (`extension/src/sidepanel.ts:260`). The CLI, editor and MCP call no model-class endpoint (events and read-only tools only), so `needs_cloud` surfaces in core, worker and extension only.
- Side panel "Open course": `extension/src/sidepanel.ts` `renderCourses` (`:272`) shows one `Open course` button per ready course; a failed open shows its error text. `extension/src/sidepanelBoot.ts` `onOpenCourse` (`:174`) sends `panel:openCourse`; `extension/src/background.ts` message type `panel:openCourse` (`:54`), handler `openCourse` (`:213`) checks the course is ready, gets the link, refuses a link outside the core (`isCoreUrl`, `:253`) and opens it in a new tab; `extension/src/coreClient.ts:359` `openCourse` calls `POST /v1/courses/{id}/open`.
- Side panel course list, create and delete: `extension/src/sidepanel.ts:272` `renderCourses` lists the courses and shows "n of limit" (only when the limit is above 0). Each course has a Delete button; the second click, "Confirm delete", sends the delete, and "Cancel" goes back. `extension/src/sidepanel.ts:238` `renderCreateCourse` is the create form: a blank title is not sent, and a failed create shows `courseErrorText` (`extension/src/coreClient.ts:144`). `extension/src/sidepanelBoot.ts:45` `loadCourses` reads `limit` and `total` from `listCoursesMeta` (`extension/src/coreClient.ts:337`); `extension/src/background.ts:224` `deleteCourse` and `:230` `createCourse` answer `panel:deleteCourse` and `panel:createCourse`; `extension/src/coreClient.ts:343` `createCourse` and `:348` `deleteCourse` call `POST /v1/courses` and `DELETE /v1/courses/{id}`.
- Bridge stub and registration: `extension/src/bridge.ts:37` `injectStub` puts the page stub at document_start; `extension/src/bridgeRegister.ts:46` `bridgeMatchPatterns` builds `<core scheme>//*/c/*`, `:60` `registerBridge` re-registers `bridge.js` as `kata-bridge` on every install and startup (`:106` `wireBridgeRegistration`).
- `extension/src/reviewScreen.ts:32` `renderReview` (one row per concept, three-state control); types `ReviewRow`, `ReviewState`.
- `extension/src/background.ts:51` message `panel:review` (`review()` at `:176` merges marks with lesson-check); `:52` message `panel:setConcept` (`setConcept` at `:198`).
- `extension/src/sidepanelBoot.ts:155` sends `panel:review`; `:164` `onSetConcept` sends `panel:setConcept`.
- `extension/src/highlight.ts:47` `applyHighlights`, `:60` `clearHighlights`; CSS classes `CLASS_KNOWN` = `kata-known` (`:12`), `CLASS_NEW` = `kata-new` (`:14`).
- `extension/src/config.ts` `REQUEST_TIMEOUT_MS`, `POLL_MS`, `MAX_WAIT_MS`. No default server: the URL is typed at sign-in.
- `extension/src/serverUrl.ts:11` `validateServerUrl` (http or https only; no credentials, query or fragment; returns `baseUrl`, `origin`, and the grant pattern `<origin>/*`).
- `extension/build/build.mjs` `resolveVersion`: `KATA_EXTENSION_VERSION` (`x.y.z`) when set, else the `version` of `extension/package.json`. No server URL is read at build.
- `extension/build/manifest.mjs` `composeManifest` adds no host permission; the server origin is granted at runtime.
- Scan button (side panel): `extension/src/sidepanelBoot.ts` `onScan` (`:129`) sends `panel:scan`; the `panel:scan` case of the message switch in `extension/src/background.ts` (`:281`) runs the scan on the open page (content script `scan`, then `runScan`).
- Firefox vs Chrome permissions (`extension/build/manifest.mjs`): Chrome adds `sidePanel` to `permissions` and `side_panel`; Firefox adds no side-panel permission and uses `sidebar_action` with background `scripts`.
- `extension/src/bridge.ts:28` `newChannel` (random channel id), `:37` `injectStub` (inline page stub at document_start), `:61` `startBridge`, `:97` `runBridge` (exact-origin check); message types `bridge:load` and `bridge:save`.
- `extension/src/bridgeRegister.ts` `bridgeMatchPatterns` (`<scheme>://*/c/*` of the saved origin), `registerBridge` (id `kata-bridge`, `bridge.js`, document_start, persists across sessions), `syncBridge` (`:93`, after sign-in, disconnect, install and startup), `wireBridgeRegistration` (`:106`, install, startup, origin permission removed).
- `extension/src/sidepanelBoot.ts` `onSignIn` (`:73`, origin grant, then `panel:signIn`), `onDisconnect` (`:105`); `extension/src/background.ts` `signIn` (probe `GET /v1/health/deep`, enrol, save session, sync bridge), `disconnect`.
- `extension/src/background.ts:265` `handleBridgeMessage` (`bridge:load` / `bridge:save` to the progress service; replies `{ok,data}` or `{ok:false,error}`).
- `extension/manifest.base.json` permission `scripting` (dynamic registration of `bridge.js`); `extension/build/build.mjs` builds `bridge.js` as an IIFE.

- Model host control (M18): `extension/src/coreClient.ts:261` `enqueueKind` (private) queues a `modelhost.*` job with `POST /jobs` and throws `CoreHttpError` on 422; `:267` `modelhostUp`, `:272` `modelhostUse(engine)` (payload `{"engine": ...}`), `:277` `modelhostMeasure`, `:282` `modelhostStatus`; `:290` `modelhostResult(id)` reads the job and returns its output or `"pending"`. The `output` field type is at `:79`. The control jobs are queued only; the GPU-PC worker runs them (see [worker](worker.md)).
- Page scan client (M20): `extension/src/coreClient.ts:390` `scanClassify(pageKey, text, taxonomy)` queues `scan.classify`; `:395` `scanExtract(input)` queues `scan.extract` with payload `area_id`, `topic_id`, `blocks`, `area`, `topic`, `known` (both through `enqueueKind`, return the job id).
- `extension/src/coreClient.ts:408` `getClassification(pageKey)` - `GET /scan/classification`; `null` on 404. The route returns no `area_id`, so `areaId` is undefined on a stored classification.
- `extension/src/coreClient.ts:431` `chooseConcept(topicId, word, conceptId)` - `POST /scan/choice`; `:436` `reassignConcept(topicId, word, fromConceptId, toConceptId)` - `POST /scan/reassign`; `:446` `topicOverview(topicId)` - `GET /scan/overview`, mapped to `TopicOverview` (`:161`).
- `extension/src/conceptScan.ts:100` `runConceptScan(client, page, opts)` - reuses the stored classification or queues `scan.classify` and waits for it, then queues `scan.extract` for the blocks and waits again. `waitForOutput` (`:50`) polls `jobStatus` every `pollMs` and gives up after `maxWaitMs`. Never throws: returns `ConceptScanResult` (`:31`) or `ConceptScanError` (`:40`). `:10` `ConceptScanClient` is the `Pick` of the four methods it uses; `:85` `withoutIgnored` drops ignored concepts on the client as well.
- The extract request sends `known: []` today, so the worker gets no known concept names from the extension.
- `topicOverview` reads snake_case keys (`topic_id`, `concept_id`), but `GET /scan/overview` answers camelCase (`topicId`, `conceptId`), so those mapped fields come out undefined until the two agree.
- `extension/src/background.ts:194` runs `runConceptScan` with `POLL_MS` and `MAX_WAIT_MS`; `:208` starts the rescanner.
- `extension/src/rescan.ts:53` `createRescanner(deps)` - observes page mutations; every mutation restarts one `debounceMs` timer, so a burst fires `onRescan` once; `stop()` cancels the timer and the observer. `:17` `mergeMarks(prev, next)` keeps the previous state of a concept seen before, so a rescan does not blank marks.

## Key files
- `extension/manifest.base.json` - shared manifest fields and permissions; change only with the feature that needs them.
- `extension/build/manifest.mjs` - per-browser keys (Chrome side panel, Firefox sidebar and gecko id). See `docs/decisions.md`.
- `extension/build/build.mjs` - writes `dist/<browser>/` for each browser.
- `extension/package.json` - build and test commands.
- `extension/tsconfig.json` - compiler settings.
- `extension/src/background.ts` - service worker; message bridge to the core client.
- `extension/src/content.ts` - content script: `scan` returns block ids and text, `highlight` and `clear` change the page.
- `extension/src/bridge.ts` - content bridge for the course pages: a page stub posts whole-document progress load/save requests; only the core origin, the bridge channel and the `progress-<id>` path are accepted.
- `extension/src/bridgeRegister.ts` - registers `bridge.js` with `chrome.scripting` for the core's course pages (`<scheme>://*/c/*` of the saved origin; the bridge checks the exact origin).
- `extension/src/coreClient.ts` - HTTP client for the core API.
- `extension/src/reviewScreen.ts` - review screen: one row per concept, buttons 1/2/3 (known, learning, new); arrow keys move between rows.
- `docs/design/extension-ui.md` - UI design spec for the side panel and lesson page. The static mockups, their CSS tokens and their checker tests were removed; the spec is the only design file. Not shipped in the extension build.
- `extension/src/offlineQueue.ts` - queues mark presses (topic and concept marks) while the core is unreachable, in order, under `kata.markQueue`; the legacy `kata.pending` topic list is converted on first read (`:185-197`).
- Review client (M24): `extension/src/coreClient.ts:314` `reviewTree(filter)` and `:319` `reviewConcepts(filter)` call `GET /v1/review/tree` and `GET /v1/review/concepts`; the query string comes from `reviewQuery` (`:503`).

## Invariants and gotchas
- Clients talk to the core only over HTTP; the extension must fall back to cache with a short timeout (see `docs/design/overview.md`).
- Page content is read only when the user has the page open; never crawl (`docs/design/overview.md`).
- Review screen: a stored concept mark wins over the lesson-check result; with no mark, an abstaining check shows the row unset (state null).
- Review keyboard: Tab moves focus through the rows and buttons; ArrowUp/ArrowDown move between rows; keys 1, 2, 3 set known, learning, new.
- No `extension/manifest.json` in the repo: `extension/build/build.mjs:71` writes one into each `dist/<browser>/`; edit `manifest.base.json` or `build/manifest.mjs`.
- The core URL is not in the build. One build serves every core; the user types the URL at first run, and the origin is granted by the browser at that moment (`docs/decisions.md`, "Extension has no build-time server config (M15)"). Do not add a build-time URL or a fixed host permission.
- Not tested in a real browser: the origin permission prompt, the `kata-bridge` registration and the course-page bridge. Vitest checks them with fake browser APIs only.
- Firefox first; Chrome later from the same code.
- Adding a permission widens what users grant; keep the list minimal. `scripting` is there only for the bridge registration.
- Match patterns cannot name a port: the bridge pattern uses `*` as host, so a core on a non-default port still gets `bridge.js`; `runBridge` returns early on any other origin.
- Release: a `v*` tag runs `.github/workflows/release-extension.yml`, which builds both browsers and publishes the zips and `SHA256SUMS`. Actions are pinned by major tag, like `ci.yml`.

## Depends on / used by
- Depends on: Node/npm for `build` and `test` (TODO(verify) Node version: no `engines` field in any `package.json`; root `.nvmrc` pins Node 26); talks to `core` HTTP API (`docs/api.md`).
- Used by: `tests/browser/conftest.py` loads `dist/<browser>/` in Firefox and Chrome (`docs/e2e.md`, "Browser tests"), and the layout and contrast checks in `tests/browser/test_ui_layout.py` and `test_panel_contrast.py` open the same built panel page; `tests/e2e/driver.ts` imports `extension/src/scanner`, `scanSession`, `coreClient`, `offlineQueue`, `tokenStore`; `tests/foundation/test_extension_scaffold.py` checks manifest and package.json.
