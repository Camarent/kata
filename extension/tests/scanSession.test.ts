import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { runScan, type ScanClient, type ScanResult } from "../src/scanSession";
import type { JobStatus } from "../src/coreClient";

const done = (topicId: number, known: boolean): JobStatus => ({
  status: "done",
  topic: { id: topicId, category: "cat", label: `topic ${topicId}` },
  known,
});
const running: JobStatus = { status: "running", topic: null, known: null };
const failed: JobStatus = { status: "failed", topic: null, known: null };

/**
 * Fake client: each payload text maps to a script of statuses; the last status repeats.
 * Job ids are the index of the payload in `scripts`.
 */
function fakeClient(scripts: Record<string, JobStatus[]>): ScanClient {
  const texts = Object.keys(scripts);
  const polls = new Map<number, number>();
  return {
    enqueue: vi.fn(async (payload: string) => {
      const id = texts.indexOf(payload);
      if (id < 0) throw new Error(`no script for ${payload}`);
      return id;
    }),
    jobStatus: vi.fn(async (id: number) => {
      const script = scripts[texts[id]];
      const n = polls.get(id) ?? 0;
      polls.set(id, n + 1);
      return script[Math.min(n, script.length - 1)];
    }),
  };
}

describe("runScan", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns results in input order and reports them in completion order", async () => {
    const client = fakeClient({
      "slow text": [running, running, done(1, true)],
      "fast text": [done(2, false)],
    });
    const order: string[] = [];
    const promise = runScan(
      client,
      [
        { id: "a", text: "slow text" },
        { id: "b", text: "fast text" },
      ],
      { pollMs: 100, maxWaitMs: 10_000, onResult: (r: ScanResult) => order.push(r.blockId) },
    );
    await vi.advanceTimersByTimeAsync(1_000);
    const results = await promise;

    expect(results).toEqual([
      { blockId: "a", topic: { id: 1, category: "cat", label: "topic 1" }, known: true },
      { blockId: "b", topic: { id: 2, category: "cat", label: "topic 2" }, known: false },
    ]);
    expect(order).toEqual(["b", "a"]);
  });

  it("reports a failed job and a failed enqueue as null topic without rejecting", async () => {
    const client = fakeClient({
      "bad text": [failed],
      "good text": [done(3, true)],
    });
    const promise = runScan(
      client,
      [
        { id: "bad", text: "bad text" },
        { id: "good", text: "good text" },
        { id: "unknown", text: "missing text" },
      ],
      { pollMs: 100, maxWaitMs: 10_000 },
    );
    await vi.advanceTimersByTimeAsync(1_000);
    const results = await promise;

    expect(results[0]).toEqual({ blockId: "bad", topic: null, known: null, reason: "job failed" });
    expect(results[1].topic?.id).toBe(3);
    expect(results[2]).toEqual({
      blockId: "unknown",
      topic: null,
      known: null,
      reason: "no script for missing text",
    });
  });

  it("times out a job that never finishes", async () => {
    const client = fakeClient({ "stuck text": [running] });
    const promise = runScan(client, [{ id: "stuck", text: "stuck text" }], {
      pollMs: 100,
      maxWaitMs: 1_000,
    });
    await vi.advanceTimersByTimeAsync(5_000);
    const results = await promise;

    expect(results).toEqual([{ blockId: "stuck", topic: null, known: null, reason: "timed out" }]);
    expect(client.jobStatus).toHaveBeenCalled();
  });

  it("passes the known flag through from the job status", async () => {
    const client = fakeClient({
      "known text": [done(4, true)],
      "unknown text": [done(5, false)],
    });
    const promise = runScan(
      client,
      [
        { id: "k", text: "known text" },
        { id: "u", text: "unknown text" },
      ],
      { pollMs: 100, maxWaitMs: 10_000 },
    );
    await vi.advanceTimersByTimeAsync(1_000);
    const results = await promise;

    expect(results.map((r) => r.known)).toEqual([true, false]);
  });
});
