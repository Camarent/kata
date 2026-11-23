import { CORE_ORIGIN } from "./config";

/** Id of the dynamically registered bridge content script. */
export const BRIDGE_SCRIPT_ID = "kata-bridge";

/** Bundle the bridge content script is registered with, relative to the extension root. */
export const BRIDGE_SCRIPT = "bridge.js";

/** Path of the course pages on the core. */
const COURSE_PATH = "/c/*";

/** One dynamically registered content script (the fields of chrome.scripting used here). */
export interface RegisteredScript {
  id: string;
  matches: string[];
  js: string[];
  runAt: "document_start";
  persistAcrossSessions: boolean;
}

/** The part of `chrome.scripting` the registration uses; tests pass a fake with these members. */
export interface ScriptingLike {
  registerContentScripts(scripts: RegisteredScript[]): Promise<void>;
  unregisterContentScripts(filter: { ids: string[] }): Promise<void>;
}

/** The part of `chrome.runtime` that reports install and browser start. */
export interface LifecycleLike {
  onInstalled: { addListener(listener: () => void): void };
  onStartup: { addListener(listener: () => void): void };
}

/**
 * Match patterns for the course pages of the core. Match patterns cannot name a port, and a
 * host pattern without a port matches only the default port, so the pattern uses a wildcard
 * host on the origin's scheme; the bridge itself checks the exact origin (runBridge).
 */
export function bridgeMatchPatterns(origin: string = CORE_ORIGIN): string[] {
  const { protocol } = new URL(origin);
  return [`${protocol}//*${COURSE_PATH}`];
}

/**
 * Registers the bridge content script for the core's course pages, replacing any earlier
 * registration under the same id. A missing earlier registration is not an error.
 */
export async function registerBridge(scripting: ScriptingLike, origin: string = CORE_ORIGIN): Promise<void> {
  await scripting.unregisterContentScripts({ ids: [BRIDGE_SCRIPT_ID] }).catch(() => undefined);
  await scripting.registerContentScripts([
    {
      id: BRIDGE_SCRIPT_ID,
      matches: bridgeMatchPatterns(origin),
      js: [BRIDGE_SCRIPT],
      runAt: "document_start",
      persistAcrossSessions: true,
    },
  ]);
}

/** Registers the bridge on install and on browser start. */
export function wireBridgeRegistration(
  runtime: LifecycleLike,
  scripting: ScriptingLike,
  origin: string = CORE_ORIGIN,
): void {
  const register = () => {
    registerBridge(scripting, origin).catch((err: unknown) => console.error(err));
  };
  runtime.onInstalled.addListener(register);
  runtime.onStartup.addListener(register);
}
