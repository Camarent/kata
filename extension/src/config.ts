/** Settings of the extension. The only place these literals live. */

/**
 * Build-time core base URL, injected by esbuild from `KATA_EXTENSION_BASE_URL` (see build/build.mjs).
 * Unset in unbundled runs such as vitest, where the fallback below applies.
 */
declare const __KATA_BASE_URL__: string;

/**
 * Loopback address of the local kata core. The fallback must match `host_permissions` in manifest.base.json.
 * The build sets the host permission from the same URL.
 */
export const DEFAULT_BASE_URL: string =
  typeof __KATA_BASE_URL__ !== "undefined" ? __KATA_BASE_URL__ : "http://127.0.0.1:8080";

/** Origin (scheme, host, port) of the core: the only origin whose course pages get the progress bridge. */
export const CORE_ORIGIN: string = new URL(DEFAULT_BASE_URL).origin;

/** Longest a single core request may take, in milliseconds. */
export const REQUEST_TIMEOUT_MS = 5000;

/** Delay between two job status polls, in milliseconds. */
export const POLL_MS = 500;

/** Time after which an unfinished tagging job counts as timed out, in milliseconds. */
export const MAX_WAIT_MS = 30000;
