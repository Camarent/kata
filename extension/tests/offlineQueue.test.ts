import { describe, expect, it, vi } from "vitest";
import {
  CoreAuthError,
  CoreHttpError,
  CoreOfflineError,
  CoreTimeoutError,
} from "../src/coreClient";
import { OfflineQueue } from "../src/offlineQueue";
import type { StorageArea } from "../src/tokenStore";

/** In-memory StorageArea. */
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

/** Fake client: `setKnown` follows the queue of answers (Error to throw, null to succeed). */
function fakeClient(answers: Array<Error | null> = []) {
  const queue = [...answers];
  const setKnown = vi.fn(async (_topicId: number) => {
    const next = queue.shift() ?? null;
    if (next) throw next;
  });
  return { setKnown, client: { setKnown } };
}

describe("OfflineQueue", () => {
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
    expect(await queue.pending()).toEqual([1, 2]);
    expect(area.data.get("kata.pending")).toEqual([1, 2]);

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
    expect(await queue.pending()).toEqual([5]);
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
    area.data.set("kata.pending", [1, 2, 3, 4]);
    const { client } = fakeClient([
      new CoreOfflineError(), // 1 stays
      new CoreHttpError(404), // 2 dropped, topic gone
      null, // 3 sent
      new CoreAuthError(), // 4 stays, run stops
    ]);
    const queue = new OfflineQueue(area, client);

    await expect(queue.flush()).rejects.toBeInstanceOf(CoreAuthError);
    expect(await queue.pending()).toEqual([1, 4]);
  });

  it("flush: reports sent, dropped and kept counts", async () => {
    const area = memoryArea();
    area.data.set("kata.pending", [1, 2, 3]);
    const { client } = fakeClient([new CoreTimeoutError(), new CoreHttpError(404), null]);
    const queue = new OfflineQueue(area, client);

    expect(await queue.flush()).toEqual({ sent: 1, dropped: 1, kept: 1 });
    expect(await queue.pending()).toEqual([1]);
  });
});
