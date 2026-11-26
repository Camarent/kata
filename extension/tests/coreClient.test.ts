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
  courseErrorText,
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

describe("CoreClient course create, delete and limits", () => {
  const ready = { id: 2, title: "B", status: "ready", concept_ids: [1], error: null, created_at: "t", updated_at: "t" };

  it("listCoursesMeta returns ready items plus limit and total", async () => {
    const items = [ready, { ...ready, id: 1, status: "building" }];
    const { fn, calls } = fakeFetch(200, { items, next_before_id: null, limit: 10, total: 2 });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    expect(await client.listCoursesMeta()).toEqual({ items: [ready], limit: 10, total: 2 });
    expect(calls[0].method).toBe("GET");
    expect(calls[0].url).toBe(`${BASE}/v1/courses`);
  });

  it("listCourses keeps its shape when the page also carries limit and total", async () => {
    const { fn } = fakeFetch(200, { items: [ready], next_before_id: null, limit: 10, total: 1 });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    expect(await client.listCourses()).toEqual([ready]);
  });

  it("createCourse posts the title to /v1/courses and returns the accepted course", async () => {
    const accepted = { ...ready, status: "building", job_id: 77 };
    const { fn, calls } = fakeFetch(202, accepted);
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    expect(await client.createCourse("Rust basics")).toEqual(accepted);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].url).toBe(`${BASE}/v1/courses`);
    expect(calls[0].body).toEqual({ title: "Rust basics" });
    expect(calls[0].headers["Authorization"]).toBe("Bearer t");
  });

  it("createCourse throws CoreHttpError carrying course_limit from a 409 body", async () => {
    const { fn } = fakeFetch(409, { detail: { code: "course_limit", message: "course limit of 3 reached" } });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    const err = await client.createCourse("X").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(CoreHttpError);
    expect((err as CoreHttpError).status).toBe(409);
    expect((err as CoreHttpError).code).toBe("course_limit");
  });

  it("createCourse carries course_name_taken from a 409 body", async () => {
    const { fn } = fakeFetch(409, { detail: { code: "course_name_taken", message: "taken" } });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    const err = await client.createCourse("X").catch((e: unknown) => e);
    expect((err as CoreHttpError).code).toBe("course_name_taken");
  });

  it("createCourse carries course_title_empty from a 422 body", async () => {
    const { fn } = fakeFetch(422, { detail: { code: "course_title_empty", message: "course title is empty" } });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    const err = await client.createCourse("  ").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(CoreHttpError);
    expect((err as CoreHttpError).status).toBe(422);
    expect((err as CoreHttpError).code).toBe("course_title_empty");
  });

  it("CoreHttpError has no code when the body detail is a plain string or missing", async () => {
    const plain = fakeFetch(404, { detail: "job not found" });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: plain.fn });
    const err = await client.jobStatus(3).catch((e: unknown) => e);
    expect((err as CoreHttpError).code).toBeUndefined();

    const bare = fakeFetch(500, {});
    const client2 = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: bare.fn });
    const err2 = await client2.jobStatus(3).catch((e: unknown) => e);
    expect((err2 as CoreHttpError).code).toBeUndefined();
  });

  it("deleteCourse sends DELETE to /v1/courses/{id} and resolves true on 204", async () => {
    const { fn, calls } = fakeFetch(204);
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    expect(await client.deleteCourse(9)).toBe(true);
    expect(calls[0].method).toBe("DELETE");
    expect(calls[0].url).toBe(`${BASE}/v1/courses/9`);
    expect(calls[0].headers["Authorization"]).toBe("Bearer t");
  });

  it("deleteCourse resolves false on 404 (already gone)", async () => {
    const { fn } = fakeFetch(404, { detail: { code: "course_not_found", message: "no such course" } });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    expect(await client.deleteCourse(9)).toBe(false);
  });

  it("deleteCourse throws CoreHttpError on other failures", async () => {
    const { fn } = fakeFetch(500, {});
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 500, fetchImpl: fn });
    const err = await client.deleteCourse(9).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(CoreHttpError);
    expect((err as CoreHttpError).status).toBe(500);
  });

  it("deleteCourse throws CoreAuthError on 401", async () => {
    const { fn } = fakeFetch(401, { detail: "nope" });
    const client = new CoreClient({ baseUrl: BASE, token: "bad", timeoutMs: 500, fetchImpl: fn });
    await expect(client.deleteCourse(9)).rejects.toBeInstanceOf(CoreAuthError);
  });

  it("courseErrorText maps the three course codes to short texts", () => {
    const withCode = (code: string) => new CoreHttpError(409, code);
    expect(courseErrorText(withCode("course_limit"))).toBe(
      "You have reached your course limit. Delete a course to add another.",
    );
    expect(courseErrorText(withCode("course_name_taken"))).toBe(
      "A course with this name already exists. Choose another title.",
    );
    expect(courseErrorText(new CoreHttpError(422, "course_title_empty"))).toBe("Enter a course title.");
  });

  it("courseErrorText maps needs_cloud to the short cloud-token text", () => {
    expect(courseErrorText(new CoreHttpError(409, "needs_cloud"))).toBe(
      "This needs a cloud model. Add a cloud token to turn it on.",
    );
  });

  it("courseErrorText falls back to the generic text for other errors", () => {
    const generic = "Could not save the course. Try again.";
    expect(courseErrorText(new CoreHttpError(500))).toBe(generic);
    expect(courseErrorText(new CoreHttpError(409, "something_new"))).toBe(generic);
    expect(courseErrorText(new CoreOfflineError())).toBe(generic);
    expect(courseErrorText("boom")).toBe(generic);
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

describe("CoreClient modelhost jobs", () => {
  it("each modelhost enqueue posts its kind and payload to /jobs and returns the id", async () => {
    const { fn, calls } = fakeFetch(200, { id: 5 });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl: fn });
    expect(await client.modelhostUp()).toBe(5);
    expect(await client.modelhostUse("ollama")).toBe(5);
    expect(await client.modelhostMeasure()).toBe(5);
    expect(await client.modelhostStatus()).toBe(5);
    expect(calls.map((c) => c.url)).toEqual([`${BASE}/jobs`, `${BASE}/jobs`, `${BASE}/jobs`, `${BASE}/jobs`]);
    expect(calls.map((c) => c.method)).toEqual(["POST", "POST", "POST", "POST"]);
    expect(calls.map((c) => c.body)).toEqual([
      { payload: "{}", kind: "modelhost.up" },
      { payload: '{"engine":"ollama"}', kind: "modelhost.use" },
      { payload: "{}", kind: "modelhost.measure" },
      { payload: "{}", kind: "modelhost.status" },
    ]);
    expect(calls[0].headers["Authorization"]).toBe("Bearer t");
  });

  it("modelhostUse sends the chosen engine in the payload", async () => {
    const { fn, calls } = fakeFetch(200, { id: 6 });
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 1000, fetchImpl: fn });
    expect(await client.modelhostUse("none")).toBe(6);
    expect(calls[0].body).toEqual({ payload: '{"engine":"none"}', kind: "modelhost.use" });
  });

  it("a 422 from a modelhost enqueue surfaces as CoreHttpError with the status and code", async () => {
    const { fn } = fakeFetch(422, { detail: { code: "bad_payload" } });
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 1000, fetchImpl: fn });
    const err = await client.modelhostUse("strata").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(CoreHttpError);
    expect((err as CoreHttpError).status).toBe(422);
    expect((err as CoreHttpError).code).toBe("bad_payload");
  });

  it("modelhostResult returns pending while the job has no output", async () => {
    const { fn, calls } = fakeFetch(200, { status: "queued", topic: null, known: null, output: null });
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 1000, fetchImpl: fn });
    expect(await client.modelhostResult(11)).toBe("pending");
    expect(calls[0].method).toBe("GET");
    expect(calls[0].url).toBe(`${BASE}/jobs/11`);
  });

  it("modelhostResult returns the output of a done job", async () => {
    const output = { ok: true, text: "running", capabilities: { gpu: false } };
    const { fn } = fakeFetch(200, { status: "done", topic: null, known: null, output });
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 1000, fetchImpl: fn });
    expect(await client.modelhostResult(12)).toEqual(output);
  });

  it("modelhostResult throws when the job failed", async () => {
    const { fn } = fakeFetch(200, { status: "failed", topic: null, known: null, output: null });
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 1000, fetchImpl: fn });
    await expect(client.modelhostResult(13)).rejects.toThrow("modelhost job 13 failed");
  });
});

describe("CoreClient scan calls", () => {
  it("scanClassify queues scan.classify with the page key, text and taxonomy", async () => {
    const { fn, calls } = fakeFetch(200, { id: 21 });
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl: fn });
    expect(await client.scanClassify("https://ex.test/p", "page text", "tax")).toBe(21);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].url).toBe(`${BASE}/jobs`);
    expect(calls[0].body).toEqual({
      payload: JSON.stringify({ page_key: "https://ex.test/p", text: "page text", taxonomy: "tax" }),
      kind: "scan.classify",
    });
  });

  it("scanExtract queues scan.extract with area_id, topic_id, blocks, area, topic and known", async () => {
    const { fn, calls } = fakeFetch(200, { id: 22 });
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 1000, fetchImpl: fn });
    const input = {
      areaId: 3,
      topicId: 7,
      blocks: [{ blockId: "b1", text: "a block" }],
      area: "Maths",
      topic: "Algebra",
      known: ["sum"],
    };
    expect(await client.scanExtract(input)).toBe(22);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].url).toBe(`${BASE}/jobs`);
    expect(calls[0].body).toEqual({
      payload: JSON.stringify({
        area_id: 3,
        topic_id: 7,
        blocks: [{ blockId: "b1", text: "a block" }],
        area: "Maths",
        topic: "Algebra",
        known: ["sum"],
      }),
      kind: "scan.extract",
    });
  });

  it("getClassification gets /scan/classification with the encoded page key and maps the reply", async () => {
    const pageKey = "https://ex.test/p?a=1&b=2";
    const { fn, calls } = fakeFetch(200, {
      area_id: 3,
      topic_id: 7,
      area: "Maths",
      topic: "Algebra",
      candidates: [{ topic_id: 8, area: "Maths", topic: "Geometry" }],
    });
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 1000, fetchImpl: fn });
    const out = await client.getClassification(pageKey);
    expect(calls[0].method).toBe("GET");
    expect(calls[0].url).toBe(`${BASE}/scan/classification?page_key=${encodeURIComponent(pageKey)}`);
    expect(out).toEqual({
      areaId: 3,
      topicId: 7,
      area: "Maths",
      topic: "Algebra",
      candidates: [{ topicId: 8, area: "Maths", topic: "Geometry" }],
    });
  });

  it("getClassification resolves null on 404 (no classification yet)", async () => {
    const { fn } = fakeFetch(404, { detail: "not found" });
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 1000, fetchImpl: fn });
    expect(await client.getClassification("https://ex.test/none")).toBeNull();
  });

  it("getClassification throws CoreHttpError on other failures", async () => {
    const { fn } = fakeFetch(500, { detail: "boom" });
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 1000, fetchImpl: fn });
    const err = await client.getClassification("https://ex.test/p").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(CoreHttpError);
    expect((err as CoreHttpError).status).toBe(500);
  });

  it("chooseConcept posts topic, word and concept to /scan/choice", async () => {
    const { fn, calls } = fakeFetch(200, {});
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 1000, fetchImpl: fn });
    await client.chooseConcept(7, "sum", 40);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].url).toBe(`${BASE}/scan/choice`);
    expect(calls[0].body).toEqual({ topic_id: 7, word: "sum", concept_id: 40 });
  });

  it("reassignConcept posts topic, word and both concept ids to /scan/reassign", async () => {
    const { fn, calls } = fakeFetch(200, {});
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 1000, fetchImpl: fn });
    await client.reassignConcept(7, "sum", 40, 41);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].url).toBe(`${BASE}/scan/reassign`);
    expect(calls[0].body).toEqual({ topic_id: 7, word: "sum", from_concept_id: 40, to_concept_id: 41 });
  });

  it("topicOverview gets /scan/overview for the topic and maps the counts and concepts", async () => {
    const { fn, calls } = fakeFetch(200, {
      topic_id: 7,
      area: "Maths",
      topic: "Algebra",
      counts: { new: 1, learning: 2, known: 3 },
      concepts: [{ concept_id: 40, label: "sum", state: "known" }],
    });
    const client = new CoreClient({ baseUrl: BASE, timeoutMs: 1000, fetchImpl: fn });
    const out = await client.topicOverview(7);
    expect(calls[0].method).toBe("GET");
    expect(calls[0].url).toBe(`${BASE}/scan/overview?topic_id=7`);
    expect(out).toEqual({
      topicId: 7,
      area: "Maths",
      topic: "Algebra",
      counts: { new: 1, learning: 2, known: 3 },
      concepts: [{ conceptId: 40, label: "sum", state: "known" }],
    });
  });
});

describe("CoreClient review calls", () => {
  it("reviewTree gets /v1/review/tree with q, repeated states and ids, and returns the tree", async () => {
    const tree = [
      {
        area: "Maths",
        counts: { new: 1, learning: 0, known: 2 },
        topics: [{ topicId: 3, topic: "Algebra", counts: { new: 1, learning: 0, known: 2 } }],
      },
    ];
    const { fn, calls } = fakeFetch(200, tree);
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl: fn });
    const result = await client.reviewTree({ q: "sum", states: ["new", "known"], ids: [4, 9] });
    expect(calls[0].method).toBe("GET");
    expect(calls[0].url).toBe(`${BASE}/v1/review/tree?q=sum&state=new&state=known&ids=4%2C9`);
    expect(calls[0].headers["Authorization"]).toBe("Bearer t");
    expect(result).toEqual(tree);
  });

  it("reviewTree with an empty ids set sends ids= and no filter when none is given", async () => {
    const { fn, calls } = fakeFetch(200, []);
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl: fn });
    expect(await client.reviewTree({ ids: [] })).toEqual([]);
    expect(calls[0].url).toBe(`${BASE}/v1/review/tree?ids=`);
    await client.reviewTree();
    expect(calls[1].url).toBe(`${BASE}/v1/review/tree?`);
  });

  it("reviewConcepts gets /v1/review/concepts with filters, sort and order, and returns the rows", async () => {
    const rows = [
      {
        concept_id: 7,
        label: "sum",
        state: "learning",
        added_at: "2026-11-01T00:00:00",
        last_viewed_at: null,
        relevance: 2,
      },
    ];
    const { fn, calls } = fakeFetch(200, rows);
    const client = new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl: fn });
    const result = await client.reviewConcepts({
      q: "su",
      states: ["learning"],
      ids: [7],
      sort: "relevance",
      order: "desc",
    });
    expect(calls[0].method).toBe("GET");
    expect(calls[0].url).toBe(
      `${BASE}/v1/review/concepts?q=su&state=learning&ids=7&sort=relevance&order=desc`,
    );
    expect(result).toEqual(rows);
  });
});
