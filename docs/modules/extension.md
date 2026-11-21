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
- `extension/src/reviewScreen.ts:32` `renderReview` (one row per concept, three-state control); types `ReviewRow`, `ReviewState`.
- `extension/src/background.ts:28` message `panel:review` (`:95` `review()` merges marks with lesson-check); `:29` message `panel:setConcept` (`:117` `setConcept`).
- `extension/src/sidepanelBoot.ts:41` sends `panel:review`; `:50` `onSetConcept` sends `panel:setConcept`.
- `extension/src/highlight.ts:47` `applyHighlights`, `:60` `clearHighlights`; CSS classes `CLASS_KNOWN` = `kata-known` (`:12`), `CLASS_NEW` = `kata-new` (`:14`).
- `extension/src/config.ts:4` `DEFAULT_BASE_URL`, `:7` `REQUEST_TIMEOUT_MS`, `:10` `POLL_MS`, `:13` `MAX_WAIT_MS`.

## Key files
- `extension/manifest.base.json` - shared manifest fields and permissions; change only with the feature that needs them.
- `extension/build/manifest.mjs` - per-browser keys (Chrome side panel, Firefox sidebar and gecko id). See `docs/decisions.md`.
- `extension/build/build.mjs` - writes `dist/<browser>/` for each browser.
- `extension/package.json` - build and test commands.
- `extension/tsconfig.json` - compiler settings.
- `extension/src/background.ts` - service worker; message bridge to the core client.
- `extension/src/content.ts` - content script: `scan` returns block ids and text, `highlight` and `clear` change the page.
- `extension/src/coreClient.ts` - HTTP client for the core API.
- `extension/src/reviewScreen.ts` - review screen: one row per concept, buttons 1/2/3 (known, learning, new); arrow keys move between rows.
- `extension/src/offlineQueue.ts` - queues mark presses while the core is unreachable.

## Invariants and gotchas
- Clients talk to the core only over HTTP; the extension must fall back to cache with a short timeout (see `docs/design/overview.md`).
- Page content is read only when the user has the page open; never crawl (`docs/design/overview.md`).
- Review screen: a stored concept mark wins over the lesson-check result; with no mark, an abstaining check shows the row unset (state null).
- Review keyboard: Tab moves focus through the rows and buttons; ArrowUp/ArrowDown move between rows; keys 1, 2, 3 set known, learning, new.
- Firefox first; Chrome later from the same code.
- Adding a permission widens what users grant; keep the list minimal.

## Depends on / used by
- Depends on: Node/npm for `build` and `test` (TODO(verify) Node version: no `engines` or `.nvmrc` in repo); talks to `core` HTTP API (`docs/api.md`).
- Used by: `tests/browser/conftest.py` loads `dist/<browser>/` in Firefox and Chrome (`docs/e2e.md`, "Browser tests"); `tests/e2e/driver.ts` imports `extension/src/scanner`, `scanSession`, `coreClient`, `offlineQueue`, `tokenStore`; `tests/foundation/test_extension_scaffold.py` checks manifest and package.json.
