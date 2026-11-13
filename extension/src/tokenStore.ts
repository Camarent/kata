import type { Session } from "./types";

/** Storage key holding the whole session as one value. */
const SESSION_KEY = "kata.session";

/** Subset of chrome.storage.local used here; injected so tests can fake it. */
export interface StorageArea {
  get(key: string): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
  remove(key: string): Promise<void>;
}

/** True when value has the Session shape (both fields are strings). */
function isSession(value: unknown): value is Session {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.baseUrl === "string" && typeof v.token === "string";
}

/** Keeps the local kata session (base URL and token) in extension storage. */
export class TokenStore {
  constructor(private readonly area: StorageArea) {}

  /** Writes the session, replacing any earlier one. Never logs the token. */
  async saveSession(session: Session): Promise<void> {
    await this.area.set({
      [SESSION_KEY]: { baseUrl: session.baseUrl, token: session.token },
    });
  }

  /** Returns the stored session, or null when none is stored or the value is malformed. */
  async loadSession(): Promise<Session | null> {
    const items = await this.area.get(SESSION_KEY);
    const value = items[SESSION_KEY];
    return isSession(value) ? { baseUrl: value.baseUrl, token: value.token } : null;
  }

  /** Removes the stored session. */
  async clearSession(): Promise<void> {
    await this.area.remove(SESSION_KEY);
  }
}
