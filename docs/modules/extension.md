---
paths: [extension/]
summary: Browser extension (WebExtension MV3, TypeScript) - manifest, npm package, and sources in src/ (background, content script, side panel, core client, offline queue)
---
# extension

## Purpose
Client for Milestones 0 and 2: a Manifest V3 browser extension that scans the open lesson page, shows topic marks in a side panel, and (Milestone 2) offers a review screen to set the user's concept marks. Sources in `extension/src/`; the build (`extension/build/build.mjs`) bundles `background.ts` (ESM), `content.ts` (IIFE) and `sidepanelBoot.ts` (ESM) into `dist/<browser>/` for `chrome` and `firefox`. The e2e test bundles the same modules through `tests/e2e/driver.ts`.

## Public surface
- `extension/manifest.base.json:3` name `kata`; `:5` shared permissions `storage`, `activeTab`; `:6` host permission `http://127.0.0.1:8080/*`; `:9` content script match `http://*/*`, `https://*/*`; `:10` content script `content.js`.
- `extension/build/manifest.mjs:32` Chrome adds permission `sidePanel` and `:33` `side_panel`, `:34` service worker `background.js`; `:38` Firefox `sidebar_action`, `:39` background scripts, `:41` `gecko` id `kata@kata.local`, min version `128.0`.
- `extension/build/build.mjs` `composeManifest` output and bundles written per browser to `dist/<browser>/`.
- `extension/src/browser.ts:15` `openPanel` (`sidePanel` on Chrome, `sidebarAction` on Firefox).
- `extension/package.json:6` `build` = `tsc --noEmit && node build/build.mjs`; `:7` `test` = `vitest run`; devDependencies `esbuild`, `jsdom`, `typescript`, `vitest`.
- `extension/tsconfig.json:6` `strict: true`; `:7` `outDir: dist`.
- `extension/src/background.ts:53` `createBackend`, `:159` `wireBackground`.
- `extension/src/content.ts:23` `handleContentMessage`, `:44` `registerContentScript`.
- `extension/src/scanner.ts:96` `scanBlocks`; `extension/src/scanSession.ts:33` `runScan`.
- `extension/src/coreClient.ts:76` `CoreClient`; `:118` `listConceptMarks`, `:123` `setConceptMark` (concept marks); error classes `CoreTimeoutError`, `CoreOfflineError`, `CoreAuthError`, `CoreHttpError`.
- `extension/src/offlineQueue.ts:31` `OfflineQueue`.
- `extension/src/tokenStore.ts:21` `TokenStore`.
- `extension/src/sidepanel.ts:178` `renderPanel`; `extension/src/sidepanelBoot.ts:17` `bootPanel`.
- Side panel "Open course": `extension/src/sidepanel.ts:168` Courses section, one `Open course` button per ready course (`:175`); a failed open shows its error text. `extension/src/sidepanelBoot.ts:74` `onOpenCourse` sends `panel:openCourse`; `extension/src/background.ts:35` message type, `:148` `openCourse` checks the course is ready (`:151`), gets the link (`:154`), refuses a link outside the core (`:155` `isCoreUrl`) and opens it in a new tab (`:156`); `extension/src/coreClient.ts:186` `openCourse` calls `POST /v1/courses/{id}/open`.
- Bridge stub and registration: `extension/src/bridge.ts:36` `injectStub` puts the page stub at document_start; `extension/src/bridgeRegister.ts:38` `bridgeMatchPatterns` builds `<core scheme>//*/c/*`, `:47` `registerBridge` re-registers `bridge.js` as `kata-bridge` on every install and startup (`:61` `wireBridgeRegistration`).
- `extension/src/reviewScreen.ts:32` `renderReview` (one row per concept, three-state control); types `ReviewRow`, `ReviewState`.
- `extension/src/background.ts:28` message `panel:review` (`:95` `review()` merges marks with lesson-check); `:29` message `panel:setConcept` (`:117` `setConcept`).
- `extension/src/sidepanelBoot.ts:41` sends `panel:review`; `:50` `onSetConcept` sends `panel:setConcept`.
- `extension/src/highlight.ts:47` `applyHighlights`, `:60` `clearHighlights`; CSS classes `CLASS_KNOWN` = `kata-known` (`:12`), `CLASS_NEW` = `kata-new` (`:14`).
- `extension/src/config.ts:13` `DEFAULT_BASE_URL` (build-time `__KATA_BASE_URL__`, fallback `http://127.0.0.1:8080`); `:17` `REQUEST_TIMEOUT_MS`, `:20` `POLL_MS`, `:23` `MAX_WAIT_MS`.
- `extension/build/build.mjs:24` `BASE_URL_ENV` = `KATA_EXTENSION_BASE_URL`; `:58` defines `__KATA_BASE_URL__` when it is set; `:75` reads it at build.
- `extension/build/manifest.mjs:53` `host_permissions` becomes the base URL origin plus `/*` when a base URL is given (`:29` `hostOrigin`).
- `extension/src/bridge.ts:27` `newChannel` (random channel id), `:36` `injectStub` (inline page stub at document_start), `:60` `startBridge`, `:93` `runBridge` (exact-origin check); message types `bridge:load` and `bridge:save`.
- `extension/src/bridgeRegister.ts:38` `bridgeMatchPatterns`, `:47` `registerBridge` (id `kata-bridge`, `bridge.js`, document_start, persists across sessions), `:61` `wireBridgeRegistration` (install and startup).
- `extension/src/background.ts:135` `handleBridgeMessage` (`bridge:load` / `bridge:save` to the progress service; replies `{ok,data}` or `{ok:false,error}`).
- `extension/manifest.base.json` permission `scripting` (dynamic registration of `bridge.js`); `extension/build/build.mjs` builds `bridge.js` as an IIFE.

## Key files
- `extension/manifest.base.json` - shared manifest fields and permissions; change only with the feature that needs them.
- `extension/build/manifest.mjs` - per-browser keys (Chrome side panel, Firefox sidebar and gecko id). See `docs/decisions.md`.
- `extension/build/build.mjs` - writes `dist/<browser>/` for each browser.
- `extension/package.json` - build and test commands.
- `extension/tsconfig.json` - compiler settings.
- `extension/src/background.ts` - service worker; message bridge to the core client.
- `extension/src/content.ts` - content script: `scan` returns block ids and text, `highlight` and `clear` change the page.
- `extension/src/bridge.ts` - content bridge for the course pages: a page stub posts whole-document progress load/save requests; only the core origin, the bridge channel and the `progress-<id>` path are accepted.
- `extension/src/bridgeRegister.ts` - registers `bridge.js` with `chrome.scripting` for the core's course pages (`http://*/c/*` on the core scheme; the bridge checks the exact origin).
- `extension/src/coreClient.ts` - HTTP client for the core API.
- `extension/src/reviewScreen.ts` - review screen: one row per concept, buttons 1/2/3 (known, learning, new); arrow keys move between rows.
- `extension/src/offlineQueue.ts` - queues mark presses while the core is unreachable.

## Invariants and gotchas
- Clients talk to the core only over HTTP; the extension must fall back to cache with a short timeout (see `docs/design/overview.md`).
- Page content is read only when the user has the page open; never crawl (`docs/design/overview.md`).
- Review screen: a stored concept mark wins over the lesson-check result; with no mark, an abstaining check shows the row unset (state null).
- Review keyboard: Tab moves focus through the rows and buttons; ArrowUp/ArrowDown move between rows; keys 1, 2, 3 set known, learning, new.
- No `extension/manifest.json` in the repo: `extension/build/build.mjs:47` writes one into each `dist/<browser>/`; edit `manifest.base.json` or `build/manifest.mjs`.
- Core base URL is fixed at build time: `KATA_EXTENSION_BASE_URL=https://<name> npm run build` in `extension/` (the VM build, `docs/deployment.md`). Unset, the build keeps the loopback URL and the `host_permissions` of `manifest.base.json`. The fallback in `config.ts` must match `manifest.base.json`.
- Firefox first; Chrome later from the same code.
- Adding a permission widens what users grant; keep the list minimal. `scripting` is there only for the bridge registration.
- Match patterns cannot name a port: the bridge pattern uses `*` as host, so a core on a non-default port still gets `bridge.js`; `runBridge` returns early on any other origin.

## Depends on / used by
- Depends on: Node/npm for `build` and `test` (TODO(verify) Node version: no `engines` or `.nvmrc` in repo); talks to `core` HTTP API (`docs/api.md`).
- Used by: `tests/browser/conftest.py` loads `dist/<browser>/` in Firefox and Chrome (`docs/e2e.md`, "Browser tests"); `tests/e2e/driver.ts` imports `extension/src/scanner`, `scanSession`, `coreClient`, `offlineQueue`, `tokenStore`; `tests/foundation/test_extension_scaffold.py` checks manifest and package.json.
