import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CoreAuthError,
  CoreClient,
  CoreHttpError,
  CoreOfflineError,
  CoreTimeoutError,
} from "../src/coreClient";

const BASE = "http://127.0.0.1:8080";

interface Call {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

/** Fake fetch that records calls and answers with `reply` (status and JSON body). */
function fakeFetch(status: number, json: unknown = {}) {
  const calls: Call[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const headers = (init?.headers ?? {}) as Record<string, string>;
    calls.push({
      url: String(input),
      method: init?.method ?? "GET",
      headers,
      body: init?.body === undefined ? undefined : JSON.parse(String(init.body)),
    });
    return new Response(status === 204 ? null : JSON.stringify(json), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  return { fn: fn as unknown as typeof fetch, calls };
}

/** Fake fetch that never answers, but rejects when its signal aborts (like real fetch). */
function hangingFetch(): typeof fetch {
  return ((_input: RequestInfo | URL, init?: RequestInit) =>
    new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    })) as unknown as typeof fetch;
}

describe("CoreClient routes", () => {
  it("enrol posts code and label, returns token and keeps it for later calls", async () => {
    const { fn, calls } = fakeFetch(200, { token: "tok-1", expires_in: 3600 });
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 1000, fetchImpl: fn });
    expect(await client.enrol("CODE", "laptop")).toBe("tok-1");
    expect(calls[0].method).toBe("POST");
    expect(calls[0].url).toBe(`${BASE}/auth/enrol`);
    expect(calls[0].body).toEqual({ code: "CODE", label: "laptop" });
    expect(calls[0].headers["Authorization"]).toBeUndefined();

    await client.enqueue("page text");
    expect(calls[1].headers["Authorization"]).toBe("Bearer tok-1");
  });

  it("enqueue posts payload to /jobs and returns the id", async () => {
    const { fn, calls } = fakeFetch(200, { id: 42 });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl: fn });
    expect(await client.enqueue("hello")).toBe(42);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].url).toBe(`${BASE}/jobs`);
    expect(calls[0].body).toEqual({ payload: "hello" });
    expect(calls[0].headers["Authorization"]).toBe("Bearer t");
  });

  it("jobStatus gets /jobs/{id} and returns status, topic and known", async () => {
    const answer = { status: "done", topic: { id: 7, category: "c", label: "l" }, known: false };
    const { fn, calls } = fakeFetch(200, answer);
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl: fn });
    expect(await client.jobStatus(9)).toEqual(answer);
    expect(calls[0].method).toBe("GET");
    expect(calls[0].url).toBe(`${BASE}/jobs/9`);
    expect(calls[0].body).toBeUndefined();
  });

  it("setKnown puts status known to /marks/{id}", async () => {
    const { fn, calls } = fakeFetch(200, { topic_id: 7, category: "c", topic: "l", status: "known" });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl: fn });
    await client.setKnown(7);
    expect(calls[0].method).toBe("PUT");
    expect(calls[0].url).toBe(`${BASE}/marks/7`);
    expect(calls[0].body).toEqual({ status: "known" });
  });

  it("listMarks gets /marks and returns the rows", async () => {
    const rows = [{ topic_id: 7, category: "c", topic: "l", status: "known" }];
    const { fn, calls } = fakeFetch(200, rows);
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl: fn });
    expect(await client.listMarks()).toEqual(rows);
    expect(calls[0].method).toBe("GET");
    expect(calls[0].url).toBe(`${BASE}/marks`);
  });

  it("sends no Authorization header when there is no token", async () => {
    const { fn, calls } = fakeFetch(200, []);
    const client = new CoreClient({ baseUrl: `${BASE}/`, timeoutMs: 1000, fetchImpl: fn });
    await client.listMarks();
    expect(calls[0].headers["Authorization"]).toBeUndefined();
    expect(calls[0].url).toBe(`${BASE}/marks`);
  });
});

describe("CoreClient errors", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("times out when the core never answers", async () => {
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 500, fetchImpl: hangingFetch() });
    const pending = client.listMarks();
    const assertion = expect(pending).rejects.toBeInstanceOf(CoreTimeoutError);
    await vi.advanceTimersByTimeAsync(500);
    await assertion;
  });

  it("throws CoreOfflineError when the network fails", async () => {
    const failing = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 500, fetchImpl: failing });
    await expect(client.jobStatus(1)).rejects.toBeInstanceOf(CoreOfflineError);
  });

  it("throws CoreAuthError on 401", async () => {
    const { fn } = fakeFetch(401, { detail: "nope" });
    const client = new CoreClient({ baseUrl: BASE, token: "bad", timeoutMs: 500, fetchImpl: fn });
    await expect(client.enqueue("x")).rejects.toBeInstanceOf(CoreAuthError);
  });

  it("throws CoreHttpError on other failures", async () => {
    const { fn } = fakeFetch(404, { detail: "job not found" });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    const err = await client.jobStatus(3).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(CoreHttpError);
    expect((err as CoreHttpError).status).toBe(404);
  });

  it("accepts a 204 answer without a body", async () => {
    const { fn } = fakeFetch(204);
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    await expect(client.setKnown(7)).resolves.toBeUndefined();
  });
});
