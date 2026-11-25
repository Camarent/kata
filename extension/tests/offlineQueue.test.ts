import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CoreAuthError,
  CoreHttpError,
  CoreOfflineError,
  CoreTimeoutError,
} from "../src/coreClient";
import { OfflineQueue, type QueuedMark } from "../src/offlineQueue";
import type { StorageArea } from "../src/tokenStore";

const QUEUE_KEY = "kata.markQueue";
const LEGACY_KEY = "kata.pending";

/** In-memory StorageArea. Each test makes its own, so no state is shared. */
function memoryArea(): StorageArea & { data: Map<string, unknown> } {
  const data = new Map<string, unknown>();
  return {
    data,
    async get(key: string) {
      return data.has(key) ? { [key]: data.get(key) } : {};
    },
    async set(items: Record<string, unknown>) {
      for (const [k, v] of Object.entries(items)) data.set(k, v);
    },
    async remove(key: string) {
      data.delete(key);
    },
  };
}

/** Fake client: each call takes the next answer (Error to throw, null to succeed). */
function fakeClient(answers: Array<Error | null> = []) {
  const queue = [...answers];
  const next = async () => {
    const answer = queue.shift() ?? null;
    if (answer) throw answer;
  };
  const setKnown = vi.fn(async (_topicId: number) => next());
  const setConceptMark = vi.fn(async (_conceptId: number, _state: string) => next());
  return { setKnown, setConceptMark, client: { setKnown, setConceptMark } };
}

const topic = (id: number): QueuedMark => ({ kind: "topic", id, state: "known" });
const concept = (id: number, state: QueuedMark["state"]): QueuedMark => ({
  kind: "concept",
  id,
  state,
});

describe("OfflineQueue", () => {
  // Each test builds its own storage and client above; this clears any mock calls as well.
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("online: markKnown saves at once and queues nothing", async () => {
    const area = memoryArea();
    const { setKnown, client } = fakeClient();
    const queue = new OfflineQueue(area, client);

    expect(await queue.markKnown(7)).toBe("saved");
    expect(setKnown).toHaveBeenCalledWith(7);
    expect(await queue.pending()).toEqual([]);
  });

  it("offline: markKnown queues the topic, flush sends it after recovery", async () => {
    const area = memoryArea();
    const { client } = fakeClient([new CoreOfflineError(), new CoreTimeoutError()]);
    const queue = new OfflineQueue(area, client);

    expect(await queue.markKnown(1)).toBe("queued");
    expect(await queue.markKnown(2)).toBe("queued");
    expect(await queue.pending()).toEqual([topic(1), topic(2)]);
    expect(area.data.get(QUEUE_KEY)).toEqual([topic(1), topic(2)]);

    // Core is back: both marks go out, the queue is empty.
    const result = await queue.flush();
    expect(result).toEqual({ sent: 2, dropped: 0, kept: 0 });
    expect(await queue.pending()).toEqual([]);
  });

  it("duplicate click: a topic that is already queued is queued once", async () => {
    const area = memoryArea();
    const { client } = fakeClient([new CoreOfflineError(), new CoreOfflineError()]);
    const queue = new OfflineQueue(area, client);

    expect(await queue.markKnown(5)).toBe("queued");
    expect(await queue.markKnown(5)).toBe("queued");
    expect(await queue.pending()).toEqual([topic(5)]);
  });

  it("auth error: markKnown rethrows and does not queue", async () => {
    const area = memoryArea();
    const { client } = fakeClient([new CoreAuthError()]);
    const queue = new OfflineQueue(area, client);

    await expect(queue.markKnown(9)).rejects.toBeInstanceOf(CoreAuthError);
    expect(await queue.pending()).toEqual([]);
  });

  it("flush: failures stay queued, 404 drops the item, auth stops the run", async () => {
    const area = memoryArea();
    area.data.set(LEGACY_KEY, [1, 2, 3, 4]);
    const { client } = fakeClient([
      new CoreOfflineError(), // 1 stays
      new CoreHttpError(404), // 2 dropped, topic gone
      null, // 3 sent
      new CoreAuthError(), // 4 stays, run stops
    ]);
    const queue = new OfflineQueue(area, client);

    await expect(queue.flush()).rejects.toBeInstanceOf(CoreAuthError);
    expect(await queue.pending()).toEqual([topic(1), topic(4)]);
  });

  it("flush: reports sent, dropped and kept counts", async () => {
    const area = memoryArea();
    area.data.set(LEGACY_KEY, [1, 2, 3]);
    const { client } = fakeClient([new CoreTimeoutError(), new CoreHttpError(404), null]);
    const queue = new OfflineQueue(area, client);

    expect(await queue.flush()).toEqual({ sent: 1, dropped: 1, kept: 1 });
    expect(await queue.pending()).toEqual([topic(1)]);
  });

  it("legacy key: topic ids are converted once, then the old key is removed", async () => {
    const area = memoryArea();
    area.data.set(LEGACY_KEY, [4, 8]);
    const { client } = fakeClient();
    const queue = new OfflineQueue(area, client);

    expect(await queue.pending()).toEqual([topic(4), topic(8)]);
    expect(area.data.has(LEGACY_KEY)).toBe(false);
    expect(area.data.get(QUEUE_KEY)).toEqual([topic(4), topic(8)]);
    // Second read: no legacy key left, the list is unchanged.
    expect(await queue.pending()).toEqual([topic(4), topic(8)]);
  });

  it("legacy key with a queue: legacy marks go first, a queued mark for the same topic wins", async () => {
    const area = memoryArea();
    area.data.set(QUEUE_KEY, [concept(3, "learning"), topic(2)]);
    area.data.set(LEGACY_KEY, [1, 2]);
    const { client } = fakeClient();
    const queue = new OfflineQueue(area, client);

    expect(await queue.pending()).toEqual([topic(1), concept(3, "learning"), topic(2)]);
    expect(area.data.has(LEGACY_KEY)).toBe(false);
    expect(area.data.get(QUEUE_KEY)).toEqual([topic(1), concept(3, "learning"), topic(2)]);
  });

  it("malformed entries are skipped: valid marks and legacy ids are kept", async () => {
    const area = memoryArea();
    area.data.set(QUEUE_KEY, [topic(1), { kind: "other", id: 2 }, 5, concept(3, "known")]);
    area.data.set(LEGACY_KEY, [4, "bad", 6]);
    const { client } = fakeClient();
    const queue = new OfflineQueue(area, client);

    expect(await queue.pending()).toEqual([topic(4), topic(6), topic(1), concept(3, "known")]);
    expect(await queue.count()).toBe(4);
  });

  it("flush: a mark queued while the flush awaits the network is kept", async () => {
    const area = memoryArea();
    area.data.set(QUEUE_KEY, [topic(1)]);
    let queue!: OfflineQueue;
    let queuedDuringFlush: "saved" | "queued" | undefined;
    const client = {
      setKnown: vi.fn(async (id: number) => {
        if (id === 1) {
          // Offline click while the flush is still sending topic 1: topic 9 is queued.
          queuedDuringFlush = await queue.markKnown(9);
          return;
        }
        throw new CoreOfflineError();
      }),
      setConceptMark: vi.fn(async () => {
        throw new CoreOfflineError();
      }),
    };
    queue = new OfflineQueue(area, client);

    expect(await queue.flush()).toEqual({ sent: 1, dropped: 0, kept: 0 });
    expect(queuedDuringFlush).toBe("queued");
    expect(await queue.pending()).toEqual([topic(9)]);
  });

  it("concept marks queue in order with topic marks and flush sends them", async () => {
    const area = memoryArea();
    const { setConceptMark, setKnown, client } = fakeClient([
      new CoreOfflineError(), // topic 1 queued
      new CoreOfflineError(), // concept 3 queued
    ]);
    const queue = new OfflineQueue(area, client);

    expect(await queue.markKnown(1)).toBe("queued");
    expect(await queue.markConcept(3, "learning")).toBe("queued");
    expect(await queue.pending()).toEqual([topic(1), concept(3, "learning")]);
    expect(await queue.count()).toBe(2);

    expect(await queue.flush()).toEqual({ sent: 2, dropped: 0, kept: 0 });
    expect(setKnown).toHaveBeenCalledWith(1);
    expect(setConceptMark).toHaveBeenCalledWith(3, "learning");
    expect(await queue.count()).toBe(0);
  });

  it("last mark wins: a newer concept mark replaces the queued one", async () => {
    const area = memoryArea();
    const { client } = fakeClient([new CoreOfflineError(), new CoreOfflineError()]);
    const queue = new OfflineQueue(area, client);

    expect(await queue.markConcept(3, "learning")).toBe("queued");
    expect(await queue.markConcept(3, "known")).toBe("queued");
    expect(await queue.pending()).toEqual([concept(3, "known")]);
    expect(await queue.count()).toBe(1);
  });

  it("a mark sent now drops the older queued mark for the same item", async () => {
    const area = memoryArea();
    const { client } = fakeClient([new CoreOfflineError(), null]);
    const queue = new OfflineQueue(area, client);

    expect(await queue.markConcept(3, "learning")).toBe("queued");
    expect(await queue.markConcept(3, "known")).toBe("saved");
    expect(await queue.pending()).toEqual([]);
  });
});
