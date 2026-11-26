import { describe, expect, it, vi } from "vitest";
import { CoreAuthError, CoreClient, CoreOfflineError } from "../src/coreClient";
import {
  addDecisionPoint,
  addQuizSource,
  confirmExamResult,
  createTrack,
  deleteTrack,
  dismissExamResult,
  getTrack,
  importExamResult,
  listTracks,
  patchTrack,
} from "../src/coreClientTracks";

const BASE = "http://127.0.0.1:8080";

interface Call {
  url: string;
  method: string;
  body: unknown;
  raw: string | undefined;
}

/** Fake fetch that records calls and answers with `status` and `json`. */
function fakeFetch(status: number, json: unknown = {}) {
  const calls: Call[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = init?.body === undefined ? undefined : String(init.body);
    calls.push({
      url: String(input),
      method: init?.method ?? "GET",
      body: raw === undefined ? undefined : JSON.parse(raw),
      raw,
    });
    return new Response(status === 204 ? null : JSON.stringify(json), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  return { fn: fn as unknown as typeof fetch, calls };
}

/** Fake fetch that fails like a network down (no answer at all). */
function offlineFetch(): typeof fetch {
  return vi.fn(async () => {
    throw new TypeError("fetch failed");
  }) as unknown as typeof fetch;
}

function clientWith(fetchImpl: typeof fetch): CoreClient {
  return new CoreClient({ baseUrl: BASE, token: "t", timeoutMs: 1000, fetchImpl });
}

const TRACK = {
  id: 4,
  name: "Algebra",
  deadline: "2027-01-01",
  priority: 2,
  status: "active",
  items: [{ position: 1, label: "Fractions", action: "read", minutes: 20, module_id: null }],
  created_at: "t0",
  updated_at: "t1",
};
const POINT = {
  id: 9,
  track_id: 4,
  after_position: 1,
  due_on: "2027-02-01",
  status: "open",
  choice: null,
  target_track_id: null,
  decided_at: null,
  created_at: "t0",
};
const EXAM = {
  id: 6,
  origin: "import",
  taken_at: "2026-11-01T10:00:00Z",
  passed: true,
  score: 0.8,
  status: "pending",
  concepts: [{ concept_id: 3, correct: true, confirmed: false }],
};

/** One call per client function: how it is invoked, and the method, path and body it must send. */
const CALLS = [
  {
    name: "listTracks",
    run: (c: CoreClient) => listTracks(c, { limit: 5, beforeId: 12 }),
    method: "GET",
    url: `${BASE}/v1/tracks?limit=5&before_id=12`,
    body: undefined,
    reply: { items: [TRACK], next_before_id: null },
  },
  {
    name: "listTracks without options",
    run: (c: CoreClient) => listTracks(c),
    method: "GET",
    url: `${BASE}/v1/tracks`,
    body: undefined,
    reply: { items: [TRACK], next_before_id: null },
  },
  {
    name: "createTrack",
    run: (c: CoreClient) => createTrack(c, { name: "Algebra", deadline: "2027-01-01" }),
    method: "POST",
    url: `${BASE}/v1/tracks`,
    body: { name: "Algebra", deadline: "2027-01-01" },
    reply: TRACK,
  },
  {
    name: "getTrack",
    run: (c: CoreClient) => getTrack(c, 4),
    method: "GET",
    url: `${BASE}/v1/tracks/4`,
    body: undefined,
    reply: TRACK,
  },
  {
    name: "patchTrack",
    run: (c: CoreClient) => patchTrack(c, 4, { status: "paused" }),
    method: "PATCH",
    url: `${BASE}/v1/tracks/4`,
    body: { status: "paused" },
    reply: { ...TRACK, status: "paused" },
  },
  {
    name: "deleteTrack",
    run: (c: CoreClient) => deleteTrack(c, 4),
    method: "DELETE",
    url: `${BASE}/v1/tracks/4`,
    body: undefined,
    reply: undefined,
  },
  {
    name: "addDecisionPoint",
    run: (c: CoreClient) => addDecisionPoint(c, 4, { after_position: 1, due_on: "2027-02-01" }),
    method: "POST",
    url: `${BASE}/v1/tracks/4/decision-points`,
    body: { after_position: 1, due_on: "2027-02-01" },
    reply: POINT,
  },
  {
    name: "addQuizSource",
    run: (c: CoreClient) => addQuizSource(c, "https://example.org/a"),
    method: "POST",
    url: `${BASE}/quiz/sources`,
    body: { url: "https://example.org/a" },
    reply: { id: 77 },
  },
  {
    name: "importExamResult",
    run: (c: CoreClient) => importExamResult(c, '{"score":0.8}'),
    method: "POST",
    url: `${BASE}/exams/import`,
    body: { score: 0.8 },
    raw: '{"score":0.8}',
    reply: EXAM,
  },
  {
    name: "confirmExamResult",
    run: (c: CoreClient) => confirmExamResult(c, 6, [3, 5]),
    method: "POST",
    url: `${BASE}/exams/6/confirm`,
    body: { concept_ids: [3, 5] },
    reply: EXAM,
  },
  {
    name: "dismissExamResult",
    run: (c: CoreClient) => dismissExamResult(c, 6),
    method: "POST",
    url: `${BASE}/exams/6/dismiss`,
    body: undefined,
    reply: { ...EXAM, status: "dismissed" },
  },
];

describe("coreClientTracks: ok replies", () => {
  for (const call of CALLS) {
    it(`${call.name} sends ${call.method} ${call.url} and returns the reply`, async () => {
      const { fn, calls } = fakeFetch(call.name === "deleteTrack" ? 204 : 200, call.reply);
      const result = await call.run(clientWith(fn));
      expect(calls).toHaveLength(1);
      expect(calls[0].method).toBe(call.method);
      expect(calls[0].url).toBe(call.url);
      expect(calls[0].body).toEqual(call.body);
      if ("raw" in call) expect(calls[0].raw).toBe(call.raw);
      if (call.name === "addQuizSource") expect(result).toBe(77);
      else if (call.name === "deleteTrack") expect(result).toBeUndefined();
      else expect(result).toEqual(call.reply);
    });
  }
});

describe("coreClientTracks: auth and offline", () => {
  for (const call of CALLS) {
    it(`${call.name} throws CoreAuthError on 401`, async () => {
      const { fn } = fakeFetch(401, { detail: "nope" });
      await expect(call.run(clientWith(fn))).rejects.toBeInstanceOf(CoreAuthError);
    });

    it(`${call.name} throws CoreOfflineError when the network fails`, async () => {
      await expect(call.run(clientWith(offlineFetch()))).rejects.toBeInstanceOf(CoreOfflineError);
    });
  }
});
