---
paths: [extension/]
summary: Browser extension (WebExtension MV3, TypeScript) - manifest, npm package, and sources in src/ (background, content script, side panel, core client, offline queue)
---
# extension

## Purpose
Client for Milestone 0: a Manifest V3 browser extension that scans the open lesson page and shows topic marks in a side panel. Sources in `extension/src/`; the build bundles `content.ts` (IIFE) and `sidepanelBoot.ts` (ESM) into `dist/`. The e2e test bundles the same modules through `tests/e2e/driver.ts`.

## Public surface
- `extension/manifest.json:3` name `kata`; `:5` permissions `storage`, `sidePanel`, `activeTab`; `:6` host permission `http://127.0.0.1:8080/*`; `:8` service worker `dist/background.js`; `:14` content script `dist/content.js`; `:18` `side_panel` key.
- `extension/package.json:6` `build` = `tsc && npm run build:content && npm run build:sidepanel`; `:9` `test` = `vitest run`; devDependencies `esbuild`, `jsdom`, `typescript`, `vitest`.
- `extension/tsconfig.json:6` `strict: true`; `:7` `outDir: dist`.
- `extension/src/background.ts:41` `createBackend`, `:109` `wireBackground`.
- `extension/src/content.ts:23` `handleContentMessage`, `:44` `registerContentScript`.
- `extension/src/scanner.ts:96` `scanBlocks`; `extension/src/scanSession.ts:33` `runScan`.
- `extension/src/coreClient.ts:57` `CoreClient`; error classes `CoreTimeoutError`, `CoreOfflineError`, `CoreAuthError`, `CoreHttpError`.
- `extension/src/offlineQueue.ts:31` `OfflineQueue`.
- `extension/src/tokenStore.ts:21` `TokenStore`.
- `extension/src/sidepanel.ts:161` `renderPanel`; `extension/src/sidepanelBoot.ts:16` `bootPanel`.
- `extension/src/highlight.ts:47` `applyHighlights`, `:60` `clearHighlights`; CSS classes `CLASS_KNOWN` = `kata-known` (`:12`), `CLASS_NEW` = `kata-new` (`:14`).
- `extension/src/config.ts:4` `DEFAULT_BASE_URL`, `:7` `REQUEST_TIMEOUT_MS`, `:10` `POLL_MS`, `:13` `MAX_WAIT_MS`.

## Key files
- `extension/manifest.json` - permissions; change only with the feature that needs them.
- `extension/package.json` - build and test commands.
- `extension/tsconfig.json` - compiler settings.
- `extension/src/background.ts` - service worker; message bridge to the core client.
- `extension/src/content.ts` - content script: `scan` returns block ids and text, `highlight` and `clear` change the page.
- `extension/src/coreClient.ts` - HTTP client for the core API.
- `extension/src/offlineQueue.ts` - queues mark presses while the core is unreachable.

## Invariants and gotchas
- Clients talk to the core only over HTTP; the extension must fall back to cache with a short timeout (see `docs/design/overview.md`).
- Page content is read only when the user has the page open; never crawl (`docs/design/overview.md`).
- Firefox first; Chrome later from the same code.
- Adding a permission widens what users grant; keep the list minimal.

## Depends on / used by
- Depends on: Node/npm for `build` and `test` (TODO(verify) Node version: no `engines` or `.nvmrc` in repo); talks to `core` HTTP API (`docs/api.md`).
- Used by: `tests/e2e/driver.ts` imports `extension/src/scanner`, `scanSession`, `coreClient`, `offlineQueue`, `tokenStore`; `tests/foundation/test_extension_scaffold.py` checks manifest and package.json.
