import { describe, expect, it, vi } from "vitest";
import {
  CoreAuthError,
  CoreConflictError,
  CoreHttpError,
  CoreOfflineError,
  type CourseProgress,
  type ProgressDoc,
} from "../src/coreClient";
import { createProgressBridge, type ProgressClient } from "../src/progressBridge";
import type { Session } from "../src/types";

const TOKEN = "secret-device-token-123";
const SESSION: Session = { baseUrl: "http://127.0.0.1:8000", token: TOKEN };

/** Token store fake: returns the session, or null when `signedIn` is false. */
function tokensFor(signedIn = true) {
  return {
    loadSession: vi.fn(async (): Promise<Session | null> => (signedIn ? SESSION : null)),
  };
}

/**
 * Fake core client. `getProgress` answers `stored`; `putProgress` follows `puts`
 * (an Error to throw, null to store the doc and bump the revision).
 */
function fakeCore(stored: CourseProgress, puts: Array<Error | null> = []) {
  let current = stored;
  const queue = [...puts];
  const getProgress = vi.fn(async (_courseId: number) => current);
  const putProgress = vi.fn(async (_courseId: number, docJson: string, revision: number) => {
    const next = queue.shift() ?? null;
    if (next) throw next;
    current = { revision: revision + 1, doc: JSON.parse(docJson) as ProgressDoc };
    return { revision: current.revision, evidence_written: 0 };
  });
  const client: ProgressClient = { getProgress, putProgress };
  return { client, getProgress, putProgress };
}

const DOC_A: ProgressDoc = { "1": { ok: 2, bad: 0 } };
const DOC_B: ProgressDoc = { "1": { ok: 3, bad: 1 } };
const NEVER_SAVED: CourseProgress = { revision: 0, doc: null };

describe("createProgressBridge", () => {
  it("happy path: load returns null when never saved, then save and load return the doc", async () => {
    const core = fakeCore(NEVER_SAVED);
    const bridge = createProgressBridge(() => core.client, tokensFor());

    expect(await bridge.load(7)).toBeNull();
    const saved = await bridge.save(7, DOC_A);
    expect(saved).toEqual({ revision: 1, evidence_written: 0 });
    expect(await bridge.load(7)).toEqual(DOC_A);
  });

  it("remembers the revision per course: a save after load sends no extra GET", async () => {
    const core = fakeCore({ revision: 4, doc: DOC_A });
    const bridge = createProgressBridge(() => core.client, tokensFor());

    await bridge.load(7);
    await bridge.save(7, DOC_B);
    await bridge.save(7, DOC_A);

    expect(core.getProgress).toHaveBeenCalledTimes(1);
    expect(core.putProgress.mock.calls.map((call) => call[2])).toEqual([4, 5]);
  });

  it("save loads first when the revision is unknown", async () => {
    const core = fakeCore({ revision: 2, doc: DOC_A });
    const bridge = createProgressBridge(() => core.client, tokensFor());

    await bridge.save(9, DOC_B);

    expect(core.getProgress).toHaveBeenCalledTimes(1);
    expect(core.putProgress).toHaveBeenCalledWith(9, JSON.stringify(DOC_B), 2);
  });

  it("412 with an unchanged document retries the PUT once and succeeds", async () => {
    const core = fakeCore({ revision: 1, doc: DOC_A });
    const bridge = createProgressBridge(() => core.client, tokensFor());
    await bridge.load(7);
    // Someone else bumped the revision but left the document as it was.
    core.putProgress.mockImplementationOnce(async () => {
      throw new CoreConflictError(2, DOC_A);
    });

    const saved = await bridge.save(7, DOC_B);

    expect(saved.revision).toBe(3);
    expect(core.putProgress).toHaveBeenCalledTimes(2);
    expect(core.putProgress.mock.calls[1]).toEqual([7, JSON.stringify(DOC_B), 2]);
  });

  it("412 with a changed document rejects with no second PUT", async () => {
    const core = fakeCore({ revision: 1, doc: DOC_A });
    const bridge = createProgressBridge(() => core.client, tokensFor());
    await bridge.load(7);
    core.putProgress.mockImplementationOnce(async () => {
      throw new CoreConflictError(2, { "1": { ok: 9, bad: 9 } });
    });

    await expect(bridge.save(7, DOC_B)).rejects.toThrow("conflict: stored progress changed");
    expect(core.putProgress).toHaveBeenCalledTimes(1);
  });

  it("412 again after the one retry rejects as conflict and never PUTs a third time", async () => {
    const core = fakeCore({ revision: 1, doc: DOC_A });
    const bridge = createProgressBridge(() => core.client, tokensFor());
    await bridge.load(7);
    core.putProgress.mockImplementation(async () => {
      throw new CoreConflictError(5, DOC_A);
    });

    await expect(bridge.save(7, DOC_B)).rejects.toThrow("conflict");
    expect(core.putProgress).toHaveBeenCalledTimes(2);
  });

  it("413 maps to 'progress too large'", async () => {
    const core = fakeCore(NEVER_SAVED, [new CoreHttpError(413)]);
    const bridge = createProgressBridge(() => core.client, tokensFor());

    await expect(bridge.save(7, DOC_A)).rejects.toThrow("progress too large");
  });

  it("401 maps to 'sign in again' on load and on save", async () => {
    const core = fakeCore(NEVER_SAVED, [new CoreAuthError()]);
    const bridge = createProgressBridge(() => core.client, tokensFor());
    await expect(bridge.save(7, DOC_A)).rejects.toThrow("sign in again");

    const denied = fakeCore(NEVER_SAVED);
    denied.getProgress.mockRejectedValueOnce(new CoreAuthError());
    const other = createProgressBridge(() => denied.client, tokensFor());
    await expect(other.load(7)).rejects.toThrow("sign in again");
  });

  it("offline and timeout map to 'core unreachable'", async () => {
    const core = fakeCore(NEVER_SAVED, [new CoreOfflineError()]);
    const bridge = createProgressBridge(() => core.client, tokensFor());

    await expect(bridge.save(7, DOC_A)).rejects.toThrow("core unreachable");
  });

  it("no stored session rejects with 'not signed in' and never builds a client", async () => {
    const core = fakeCore(NEVER_SAVED);
    const clientFor = vi.fn(() => core.client);
    const bridge = createProgressBridge(clientFor, tokensFor(false));

    await expect(bridge.load(7)).rejects.toThrow("not signed in");
    await expect(bridge.save(7, DOC_A)).rejects.toThrow("not signed in");
    expect(clientFor).not.toHaveBeenCalled();
    expect(core.putProgress).not.toHaveBeenCalled();
  });

  it("the token string appears in no returned value and no error", async () => {
    const core = fakeCore(NEVER_SAVED, [null, new CoreHttpError(413)]);
    const bridge = createProgressBridge(() => core.client, tokensFor());
    const seen: string[] = [];

    seen.push(JSON.stringify(await bridge.load(7)));
    seen.push(JSON.stringify(await bridge.save(7, DOC_A)));
    try {
      await bridge.save(7, DOC_B);
    } catch (err) {
      seen.push(String(err));
    }
    const noSession = createProgressBridge(() => core.client, tokensFor(false));
    try {
      await noSession.load(7);
    } catch (err) {
      seen.push(String(err));
    }

    for (const text of seen) expect(text).not.toContain(TOKEN);
    expect(seen.length).toBe(4);
  });
});
