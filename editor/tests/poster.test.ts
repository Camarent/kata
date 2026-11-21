import { describe, expect, it } from "vitest";
import { readConfig } from "../src/config";
import type { FetchFn } from "../src/poster";
import { postEvent } from "../src/poster";
import type { KataConfig } from "../src/config";

const cfg: KataConfig = {
  serverUrl: "http://kata.test",
  token: "tok-123",
  stopPatterns: ["secret"],
};
const now = new Date("2026-11-21T10:00:00.000Z");
const DOCUMENT = "const greeting = 'hello there';";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status });
}

function recordingFetch(response: Response): { fetchFn: FetchFn; calls: { url: string; init: RequestInit }[] } {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchFn: FetchFn = (url, init) => {
    calls.push({ url, init });
    return Promise.resolve(response.clone());
  };
  return { fetchFn, calls };
}

describe("postEvent", () => {
  it("posts one editor event with the expected body and bearer token", async () => {
    const { fetchFn, calls } = recordingFetch(jsonResponse(200, { results: [], messages: [] }));

    const result = await postEvent(cfg, "save", "typescript", now, fetchFn, DOCUMENT);

    expect(result).toEqual({ status: "posted", messages: [] });
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("http://kata.test/v1/events");
    const headers = calls[0].init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer tok-123");
    expect(calls[0].init.method).toBe("POST");
    const body = JSON.parse(calls[0].init.body as string) as { events: Record<string, unknown>[] };
    expect(body.events).toHaveLength(1);
    const event = body.events[0];
    expect(event.event_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(event.type).toBe("editor.save");
    expect(event.occurred_at).toBe("2026-11-21T10:00:00.000Z");
    expect(event.payload).toEqual({ language: "typescript" });
  });

  it("never puts document text in the request", async () => {
    const { fetchFn, calls } = recordingFetch(jsonResponse(200, { messages: [] }));

    await postEvent(cfg, "save", "typescript", now, fetchFn, DOCUMENT);

    expect(calls[0].init.body as string).not.toContain("hello there");
    expect(calls[0].init.body as string).not.toContain("greeting");
  });

  it("does not call fetch when a stop pattern matches the document", async () => {
    const { fetchFn, calls } = recordingFetch(jsonResponse(200, { messages: [] }));

    const result = await postEvent(cfg, "save", "typescript", now, fetchFn, "the secret value");

    expect(result).toEqual({ status: "skipped" });
    expect(calls).toHaveLength(0);
  });

  it("returns the piggybacked messages from the response", async () => {
    const message = {
      id: 7,
      kind: "quiet_mark",
      body: { at: "2026-11-21T10:00:00Z", detail: {} },
      created_at: "2026-11-21T10:00:01Z",
    };
    const { fetchFn } = recordingFetch(jsonResponse(200, { results: [], messages: [message] }));

    const result = await postEvent(cfg, "save", "typescript", now, fetchFn, DOCUMENT);

    expect(result).toEqual({ status: "posted", messages: [message] });
  });

  it("returns an error result when the network fails, without throwing", async () => {
    const fetchFn: FetchFn = () => Promise.reject(new TypeError("fetch failed"));

    const result = await postEvent(cfg, "save", "typescript", now, fetchFn, DOCUMENT);

    expect(result).toEqual({ status: "error", reason: "fetch failed" });
  });

  it("returns an error result for a non-200 answer, without throwing", async () => {
    const { fetchFn } = recordingFetch(jsonResponse(422, { detail: "too long" }));

    const result = await postEvent(cfg, "save", "typescript", now, fetchFn, DOCUMENT);

    expect(result).toEqual({ status: "error", reason: "HTTP 422" });
  });
});

describe("readConfig", () => {
  it("reads kata.serverUrl, kata.token and kata.stopPatterns from the getter", () => {
    const values: Record<string, unknown> = {
      "kata.serverUrl": "http://kata.test",
      "kata.token": "tok-123",
      "kata.stopPatterns": ["secret", 5],
    };

    expect(readConfig((key) => values[key])).toEqual({
      serverUrl: "http://kata.test",
      token: "tok-123",
      stopPatterns: ["secret"],
    });
  });

  it("reads missing or mistyped values as empty", () => {
    expect(readConfig(() => undefined)).toEqual({ serverUrl: "", token: "", stopPatterns: [] });
  });
});
