import {
  CoreAuthError,
  CoreConflictError,
  CoreHttpError,
  CoreOfflineError,
  CoreTimeoutError,
  type CoreClient,
  type ProgressDoc,
  type ProgressSaved,
} from "./coreClient";
import type { TokenStore } from "./tokenStore";
import type { Session } from "./types";

/** The part of CoreClient the bridge needs; injected so tests can fake it. */
export type ProgressClient = Pick<CoreClient, "getProgress" | "putProgress">;

/** The part of TokenStore the bridge needs. */
export type ProgressTokens = Pick<TokenStore, "loadSession">;

/** The background progress operations the panel can ask for. */
export interface ProgressBridge {
  /** The stored whole document, or null when the course was never saved. */
  load(courseId: number): Promise<ProgressDoc | null>;
  /** Saves the whole document against the remembered revision. */
  save(courseId: number, doc: ProgressDoc): Promise<ProgressSaved>;
}

/** An error whose message is already short and safe to show (never holds the token). */
class ProgressError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProgressError";
  }
}

/** The revision and document this bridge last saw for one course. */
interface Remembered {
  revision: number;
  doc: ProgressDoc | null;
}

/** Deep equality for JSON-shaped values (progress documents). */
function sameDoc(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const left = a as Record<string, unknown>;
  const right = b as Record<string, unknown>;
  const keys = Object.keys(left);
  if (keys.length !== Object.keys(right).length) return false;
  return keys.every(
    (key) => Object.prototype.hasOwnProperty.call(right, key) && sameDoc(left[key], right[key]),
  );
}

/** Maps any failure to a short message for the panel. */
function shortError(err: unknown): string {
  if (err instanceof ProgressError) return err.message;
  if (err instanceof CoreAuthError) return "sign in again";
  if (err instanceof CoreConflictError) return "conflict";
  if (err instanceof CoreTimeoutError || err instanceof CoreOfflineError) return "core unreachable";
  if (err instanceof CoreHttpError && err.status === 413) return "progress too large";
  return "core error";
}

/**
 * Background progress service: loads and saves a course's whole progress document
 * through the core. Remembers each course's revision; a save that lost the revision
 * race is retried once when the stored document is unchanged since this bridge last saw it.
 */
export function createProgressBridge(
  clientFor: (session: Session) => ProgressClient,
  tokens: ProgressTokens,
): ProgressBridge {
  const remembered = new Map<number, Remembered>();

  /** Runs one operation and rethrows any failure as a short ProgressError. */
  async function run<T>(work: () => Promise<T>): Promise<T> {
    try {
      return await work();
    } catch (err) {
      throw new ProgressError(shortError(err));
    }
  }

  /** The client for the stored session; fails when no session is stored. */
  async function connect(): Promise<ProgressClient> {
    const session = await tokens.loadSession();
    if (!session) throw new ProgressError("not signed in");
    return clientFor(session);
  }

  function remember(courseId: number, revision: number, doc: ProgressDoc | null): void {
    remembered.set(courseId, { revision, doc });
  }

  /** One PUT with the given revision; remembers the saved revision and document. */
  async function put(
    client: ProgressClient,
    courseId: number,
    doc: ProgressDoc,
    revision: number,
  ): Promise<ProgressSaved> {
    const saved = await client.putProgress(courseId, JSON.stringify(doc), revision);
    remember(courseId, saved.revision, doc);
    return saved;
  }

  return {
    load(courseId: number): Promise<ProgressDoc | null> {
      return run(async () => {
        const client = await connect();
        const progress = await client.getProgress(courseId);
        const doc = progress.revision === 0 ? null : progress.doc;
        remember(courseId, progress.revision, doc);
        return doc;
      });
    },

    save(courseId: number, doc: ProgressDoc): Promise<ProgressSaved> {
      return run(async () => {
        const client = await connect();
        let known = remembered.get(courseId);
        if (!known) {
          const progress = await client.getProgress(courseId);
          known = { revision: progress.revision, doc: progress.revision === 0 ? null : progress.doc };
          remember(courseId, known.revision, known.doc);
        }
        try {
          return await put(client, courseId, doc, known.revision);
        } catch (err) {
          if (!(err instanceof CoreConflictError)) throw err;
          if (!sameDoc(err.doc, known.doc)) {
            throw new ProgressError("conflict: stored progress changed");
          }
          // Unchanged since we last saw it: retry once with the fresh revision.
          return put(client, courseId, doc, err.revision);
        }
      });
    },
  };
}
