import type { TokenStore } from "./tokenStore";

/** Id of the dynamically registered bridge content script. */
export const BRIDGE_SCRIPT_ID = "kata-bridge";

/** Bundle the bridge content script is registered with, relative to the extension root. */
const BRIDGE_SCRIPT = "bridge.js";

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

/** The part of `chrome.permissions` that reports removed origin permissions. */
export interface PermissionsLike {
  onRemoved: { addListener(listener: (removed: { origins?: string[] }) => void): void };
}

/** The part of the token store the registration reads: the saved session. */
export type SessionSource = Pick<TokenStore, "loadSession">;

/**
 * Match patterns for the course pages of the core. Match patterns cannot name a port, and a
 * host pattern without a port matches only the default port, so the pattern uses a wildcard
 * host on the origin's scheme; the bridge itself checks the exact origin (runBridge).
 */
export function bridgeMatchPatterns(origin: string): string[] {
  const { protocol } = new URL(origin);
  return [`${protocol}//*${COURSE_PATH}`];
}

/** Removes the bridge registration. A missing registration is not an error. */
async function unregisterBridge(scripting: ScriptingLike): Promise<void> {
  await scripting.unregisterContentScripts({ ids: [BRIDGE_SCRIPT_ID] }).catch(() => undefined);
}

/**
 * Registers the bridge content script for the course pages of `origin`, replacing any earlier
 * registration under the same id. A missing earlier registration is not an error.
 */
export async function registerBridge(scripting: ScriptingLike, origin: string): Promise<void> {
  await unregisterBridge(scripting);
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

/** Origin of a base URL, or undefined when the URL is invalid. */
export function originOf(baseUrl: string): string | undefined {
  try {
    return new URL(baseUrl).origin;
  } catch {
    return undefined;
  }
}

/** Origin of the saved session's base URL, or undefined when no session is saved or the URL is invalid. */
async function sessionOrigin(tokens: SessionSource): Promise<string | undefined> {
  const session = await tokens.loadSession();
  return session ? originOf(session.baseUrl) : undefined;
}

/**
 * Makes the bridge registration match the saved session: registers it for the session's origin,
 * or removes it when no session is saved. Firefox does not persist registrations, so this runs
 * again on every start and install.
 */
export async function syncBridge(scripting: ScriptingLike, tokens: SessionSource): Promise<void> {
  const origin = await sessionOrigin(tokens);
  if (origin === undefined) {
    await unregisterBridge(scripting);
    return;
  }
  await registerBridge(scripting, origin);
}

/**
 * Keeps the bridge registration in step with the saved session: syncs now, on install and on
 * browser start, and removes it when the permission for the session's origin is removed.
 */
export function wireBridgeRegistration(
  runtime: LifecycleLike,
  scripting: ScriptingLike,
  permissions: PermissionsLike | undefined,
  tokens: SessionSource,
): void {
  const sync = () => {
    syncBridge(scripting, tokens).catch((err: unknown) => console.error(err));
  };
  runtime.onInstalled.addListener(sync);
  runtime.onStartup.addListener(sync);
  // `chrome.permissions` exists only when the manifest declares the "permissions" API.
  permissions?.onRemoved.addListener((removed) => {
    const origins = removed.origins ?? [];
    sessionOrigin(tokens)
      .then((origin) => {
        if (origin !== undefined && origins.includes(`${origin}/*`)) return unregisterBridge(scripting);
        return undefined;
      })
      .catch((err: unknown) => console.error(err));
  });
  sync();
}
