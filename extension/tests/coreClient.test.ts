import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CoreAuthError,
  CoreClient,
  CoreConflictError,
  CoreHttpError,
  CoreOfflineError,
  CoreTimeoutError,
  CoreUnreachableError,
  NotKataServerError,
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

  it("listConceptMarks gets /concepts/marks and returns the rows", async () => {
    const rows = [
      { concept_id: 3, label: "fractions", state: "learning", evidence: "", created_at: "t0", updated_at: "t1" },
    ];
    const { fn, calls } = fakeFetch(200, rows);
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl: fn });
    expect(await client.listConceptMarks()).toEqual(rows);
    expect(calls[0].method).toBe("GET");
    expect(calls[0].url).toBe(`${BASE}/concepts/marks`);
    expect(calls[0].body).toBeUndefined();
  });

  it("setConceptMark puts state and evidence to /concepts/{id}/mark", async () => {
    const answer = { concept_id: 3, label: "fractions", state: "known", evidence: "quiz", created_at: "t0", updated_at: "t1" };
    const { fn, calls } = fakeFetch(200, answer);
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl: fn });
    expect(await client.setConceptMark(3, "known", "quiz")).toEqual(answer);
    expect(calls[0].method).toBe("PUT");
    expect(calls[0].url).toBe(`${BASE}/concepts/3/mark`);
    expect(calls[0].body).toEqual({ state: "known", evidence: "quiz" });
  });

  it("setConceptMark sends empty evidence when none is given", async () => {
    const { fn, calls } = fakeFetch(200, {});
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl: fn });
    await client.setConceptMark(5, "new");
    expect(calls[0].body).toEqual({ state: "new", evidence: "" });
  });

  it("lessonCheck posts concept_ids to /lesson-check and returns the results array", async () => {
    const results = [
      { concept_id: 3, label: "fractions", state: "abstain", source: "none", evidence: "" },
    ];
    const { fn, calls } = fakeFetch(200, { results });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl: fn });
    expect(await client.lessonCheck([3, 4])).toEqual(results);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].url).toBe(`${BASE}/lesson-check`);
    expect(calls[0].body).toEqual({ concept_ids: [3, 4] });
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

  it("throws CoreHttpError with 404 when a concept is missing", async () => {
    const { fn } = fakeFetch(404, { detail: "concept not found" });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    const err = await client.setConceptMark(99, "known").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(CoreHttpError);
    expect((err as CoreHttpError).status).toBe(404);
  });

  it("accepts a 204 answer without a body", async () => {
    const { fn } = fakeFetch(204);
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    await expect(client.setKnown(7)).resolves.toBeUndefined();
  });
});

describe("CoreClient course routes", () => {
  it("listCourses gets /v1/courses and keeps only ready courses", async () => {
    const items = [
      { id: 2, title: "B", status: "ready", concept_ids: [1], error: null, created_at: "t", updated_at: "t" },
      { id: 1, title: "A", status: "building", concept_ids: [], error: null, created_at: "t", updated_at: "t" },
    ];
    const { fn, calls } = fakeFetch(200, { items, next_before_id: null });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    const courses = await client.listCourses();
    expect(calls[0].method).toBe("GET");
    expect(calls[0].url).toBe(`${BASE}/v1/courses`);
    expect(calls[0].headers["Authorization"]).toBe("Bearer t");
    expect(courses.map((c) => c.id)).toEqual([2]);
  });

  it("openCourse posts to /v1/courses/{id}/open and returns the url", async () => {
    const { fn, calls } = fakeFetch(200, { url: "http://127.0.0.1:8080/c/5?sig=x" });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    expect(await client.openCourse(5)).toBe("http://127.0.0.1:8080/c/5?sig=x");
    expect(calls[0].method).toBe("POST");
    expect(calls[0].url).toBe(`${BASE}/v1/courses/5/open`);
  });

  it("getProgress gets the progress document and revision", async () => {
    const { fn, calls } = fakeFetch(200, { revision: 3, doc: { items: { "7": { ok: 1, bad: 0 } } } });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    const progress = await client.getProgress(5);
    expect(calls[0].method).toBe("GET");
    expect(calls[0].url).toBe(`${BASE}/v1/courses/5/progress`);
    expect(progress).toEqual({ revision: 3, doc: { items: { "7": { ok: 1, bad: 0 } } } });
  });

  it("putProgress sends the doc as the raw body with If-Match set to the revision", async () => {
    const { fn, calls } = fakeFetch(200, { revision: 4, evidence_written: 2 });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    const doc = '{"items":{"7":{"ok":1,"bad":0}}}';
    expect(await client.putProgress(5, doc, 3)).toEqual({ revision: 4, evidence_written: 2 });
    expect(calls[0].method).toBe("PUT");
    expect(calls[0].url).toBe(`${BASE}/v1/courses/5/progress`);
    expect(calls[0].headers["If-Match"]).toBe('"3"');
    expect(calls[0].headers["Content-Type"]).toBe("application/json");
    expect(calls[0].body).toEqual({ items: { "7": { ok: 1, bad: 0 } } });
  });

  it("putProgress throws CoreConflictError with the stored revision and doc on 412", async () => {
    const stored = { items: { "7": { ok: 2, bad: 1 } } };
    const { fn } = fakeFetch(412, { revision: 6, doc: stored });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    const err = await client.putProgress(5, "{}", 3).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(CoreConflictError);
    expect((err as CoreConflictError).status).toBe(412);
    expect((err as CoreConflictError).revision).toBe(6);
    expect((err as CoreConflictError).doc).toEqual(stored);
  });

  it("putProgress keeps CoreHttpError with status 413 for an oversized doc", async () => {
    const { fn } = fakeFetch(413, { detail: "progress document too large" });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    const err = await client.putProgress(5, "{}", 3).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(CoreHttpError);
    expect((err as CoreHttpError).status).toBe(413);
  });

  it("course calls throw CoreAuthError on 401", async () => {
    const { fn } = fakeFetch(401, { detail: "nope" });
    const client = new CoreClient({ baseUrl: BASE, token: "bad", timeoutMs: 500, fetchImpl: fn });
    await expect(client.getProgress(5)).rejects.toBeInstanceOf(CoreAuthError);
    await expect(client.putProgress(5, "{}", 1)).rejects.toBeInstanceOf(CoreAuthError);
  });
});

describe("CoreClient health probe", () => {
  const KATA_OK = { status: "ok", checks: { db: true, migrations: true } };

  it("GETs /v1/health/deep without an Authorization header and resolves with the report", async () => {
    const { fn, calls } = fakeFetch(200, KATA_OK);
    const client = new CoreClient({ baseUrl: `${BASE}/`, token: "tok-1", timeoutMs: 500, fetchImpl: fn });
    await expect(client.probe()).resolves.toEqual(KATA_OK);
    expect(calls[0].method).toBe("GET");
    expect(calls[0].url).toBe(`${BASE}/v1/health/deep`);
    expect(calls[0].headers["Authorization"]).toBeUndefined();
  });

  it("resolves for a kata 503 'fail' report, so the caller can show the failed checks", async () => {
    const failed = { status: "fail", failed: ["db"], checks: { db: false, migrations: false } };
    const { fn } = fakeFetch(503, failed);
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 500, fetchImpl: fn });
    await expect(client.probe()).resolves.toMatchObject({ status: "fail", checks: { db: false } });
  });

  it("throws CoreUnreachableError when the network fails", async () => {
    const failing = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 500, fetchImpl: failing });
    await expect(client.probe()).rejects.toBeInstanceOf(CoreUnreachableError);
  });

  it("throws CoreUnreachableError when the address never answers", async () => {
    vi.useFakeTimers();
    try {
      const client = new CoreClient({ baseUrl: BASE, timeoutMs: 500, fetchImpl: hangingFetch() });
      const pending = client.probe();
      const assertion = expect(pending).rejects.toBeInstanceOf(CoreUnreachableError);
      await vi.advanceTimersByTimeAsync(500);
      await assertion;
    } finally {
      vi.useRealTimers();
    }
  });

  it("throws NotKataServerError on a 200 JSON reply that is not the health document", async () => {
    const { fn } = fakeFetch(200, { hello: "world" });
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 500, fetchImpl: fn });
    await expect(client.probe()).rejects.toBeInstanceOf(NotKataServerError);
  });

  it("throws NotKataServerError on a 200 reply with a non-JSON body", async () => {
    const html = vi.fn(async () => new Response("<html>router</html>", { status: 200 })) as unknown as typeof fetch;
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 500, fetchImpl: html });
    await expect(client.probe()).rejects.toBeInstanceOf(NotKataServerError);
  });

  it("throws NotKataServerError when checks are not a map of booleans", async () => {
    const { fn } = fakeFetch(200, { status: "ok", checks: { db: "yes" } });
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 500, fetchImpl: fn });
    await expect(client.probe()).rejects.toBeInstanceOf(NotKataServerError);
  });
});
