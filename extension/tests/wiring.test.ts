import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createBackend, wireBackground, type ChromeLike, type PanelReply } from "../src/background";
import { handleContentMessage, registerContentScript, type RuntimeLike } from "../src/content";
import type { StorageArea } from "../src/tokenStore";

const LONG = "This paragraph is long enough to count as a readable block of page text.";

/** In-memory storage area with the StorageArea shape. */
function memoryArea(initial: Record<string, unknown> = {}): StorageArea {
  const items = new Map<string, unknown>(Object.entries(initial));
  return {
    async get(key) {
      return items.has(key) ? { [key]: items.get(key) } : {};
    },
    async set(values) {
      for (const [key, value] of Object.entries(values)) items.set(key, value);
    },
    async remove(key) {
      items.delete(key);
    },
  };
}

/** Fake `chrome` object: captures the listeners so tests can fire them. */
function fakeChrome(overrides: Partial<ChromeLike["tabs"]> = {}) {
  let clickListener: ((tab: { windowId?: number }) => void) | undefined;
  let messageListener:
    | ((message: unknown, sender: unknown, sendResponse: (response: unknown) => void) => boolean | void)
    | undefined;
  const open = vi.fn(async () => undefined);
  const api: ChromeLike = {
    action: {
      onClicked: {
        addListener(listener) {
          clickListener = listener;
        },
      },
    },
    sidePanel: { open },
    tabs: {
      query: vi.fn(async () => [{ id: 7 }]),
      sendMessage: vi.fn(async () => ({ blocks: [] })),
      create: vi.fn(async () => ({})),
      ...overrides,
    },
    runtime: {
      onMessage: {
        addListener(listener) {
          messageListener = listener;
        },
      },
    },
  };
  return {
    api,
    open,
    click: (tab: { windowId?: number }) => clickListener?.(tab),
    /** Sends a runtime message and resolves with what `sendResponse` got. */
    send: (message: unknown) =>
      new Promise<unknown>((resolve) => {
        const handled = messageListener?.(message, {}, resolve);
        if (handled !== true) resolve(undefined);
      }),
  };
}

describe("content script", () => {
  it("answers scan with the page blocks, id and text only", () => {
    document.body.innerHTML = `<h2>Alpha</h2><p>${LONG}</p>`;
    const response = handleContentMessage({ type: "scan" }, document);
    expect(response?.blocks).toHaveLength(1);
    expect(Object.keys(response?.blocks[0] ?? {}).sort()).toEqual(["id", "text"]);
    expect(response?.blocks[0].text).toContain("readable block");
  });

  it("answers highlight and clear without a reply", () => {
    document.body.innerHTML = `<p>${LONG}</p>`;
    expect(handleContentMessage({ type: "highlight", results: [] }, document)).toBeUndefined();
    expect(handleContentMessage({ type: "clear" }, document)).toBeUndefined();
  });

  it("registers a runtime listener that replies to scan", () => {
    document.body.innerHTML = `<p>${LONG}</p>`;
    let listener: ((m: unknown, s: unknown, r: (x: unknown) => void) => boolean | void) | undefined;
    const runtime: RuntimeLike = {
      onMessage: {
        addListener(l) {
          listener = l;
        },
      },
    };
    registerContentScript(runtime, document);
    let reply: unknown;
    listener?.({ type: "scan" }, {}, (r) => {
      reply = r;
    });
    expect(reply).toMatchObject({ blocks: [{ text: expect.stringContaining("readable") }] });
  });
});

describe("background wiring", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("opens the side panel on action click and flushes the queue", async () => {
    const area = memoryArea({
      "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" },
      "kata.pending": [3],
    });
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 })) as unknown as typeof fetch;
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, area, fetchImpl));
    chrome.click({ windowId: 2 });
    expect(chrome.open).toHaveBeenCalledWith({ windowId: 2 });
    await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalled());
    await vi.waitFor(async () => expect(await area.get("kata.pending")).toEqual({ "kata.pending": [] }));
  });

  it("opens the panel through sidebarAction when the browser has no sidePanel", async () => {
    const area = memoryArea({ "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } });
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 })) as unknown as typeof fetch;
    const chrome = fakeChrome();
    const sidebarOpen = vi.fn(async () => undefined);
    const api: ChromeLike = { ...chrome.api, sidePanel: undefined, sidebarAction: { open: sidebarOpen } };
    wireBackground(api, createBackend(api, area, fetchImpl));
    chrome.click({ windowId: 2 });
    expect(sidebarOpen).toHaveBeenCalledOnce();
    expect(chrome.open).not.toHaveBeenCalled();
  });

  it("known click while the core is offline returns queued", async () => {
    const area = memoryArea({ "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } });
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, area, fetchImpl));
    const reply = (await chrome.send({ type: "panel:known", topicId: 9 })) as PanelReply;
    expect(reply).toEqual({ ok: true, data: "queued" });
    expect(await area.get("kata.pending")).toEqual({ "kata.pending": [9] });
  });

  it("scan message asks the active tab for blocks and polls each job", async () => {
    const area = memoryArea({ "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } });
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST" && url.endsWith("/jobs")) {
        return new Response(JSON.stringify({ id: 1 }), { status: 201 });
      }
      return new Response(JSON.stringify({ status: "done", topic: { id: 5, category: "c", label: "l" }, known: false }), {
        status: 200,
      });
    }) as unknown as typeof fetch;
    const chrome = fakeChrome({ sendMessage: vi.fn(async () => ({ blocks: [{ id: "b1", text: LONG }] })) });
    wireBackground(chrome.api, createBackend(chrome.api, area, fetchImpl));
    const reply = (await chrome.send({ type: "panel:scan" })) as PanelReply;
    expect(chrome.api.tabs.sendMessage).toHaveBeenCalledWith(7, { type: "scan" });
    expect(reply).toEqual({
      ok: true,
      data: [{ blockId: "b1", topic: { id: 5, category: "c", label: "l" }, known: false }],
    });
  });

  it("scan without a session replies with the auth error", async () => {
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea()));
    const reply = (await chrome.send({ type: "panel:scan" })) as PanelReply;
    expect(reply).toEqual({ ok: false, error: "not signed in" });
  });

  it("scan fails clearly when the page gives no blocks", async () => {
    const area = memoryArea({ "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } });
    const chrome = fakeChrome({ sendMessage: vi.fn(async () => undefined) });
    wireBackground(chrome.api, createBackend(chrome.api, area));
    const reply = (await chrome.send({ type: "panel:scan" })) as PanelReply;
    expect(reply).toEqual({ ok: false, error: "page gave no blocks" });
  });

  it("review merges each concept mark with its lesson check, mark state wins", async () => {
    const area = memoryArea({ "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } });
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST" && url.endsWith("/lesson-check")) {
        return new Response(
          JSON.stringify({
            results: [
              { concept_id: 1, label: "A", state: "abstain", source: "", evidence: "" },
              { concept_id: 2, label: "B", state: "learning", source: "", evidence: "from check" },
            ],
          }),
          { status: 200 },
        );
      }
      return new Response(
        JSON.stringify([
          { concept_id: 1, label: "A", state: "known", evidence: "marked", created_at: "", updated_at: "" },
          { concept_id: 2, label: "B", state: "new", evidence: "", created_at: "", updated_at: "" },
        ]),
        { status: 200 },
      );
    }) as unknown as typeof fetch;
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, area, fetchImpl));
    const reply = (await chrome.send({ type: "panel:review" })) as PanelReply;
    expect(reply).toEqual({
      ok: true,
      data: [
        { conceptId: 1, label: "A", state: "known", evidence: "marked" },
        { conceptId: 2, label: "B", state: "new", evidence: "" },
      ],
    });
    const checkCall = vi.mocked(fetchImpl).mock.calls.find(([input]) => String(input).endsWith("/lesson-check"));
    expect(JSON.parse(String(checkCall?.[1]?.body))).toEqual({ concept_ids: [1, 2] });
  });

  it("review with no concept marks returns no rows and makes no lesson-check call", async () => {
    const area = memoryArea({ "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } });
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })) as unknown as typeof fetch;
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, area, fetchImpl));
    const reply = (await chrome.send({ type: "panel:review" })) as PanelReply;
    expect(reply).toEqual({ ok: true, data: [] });
    const urls = vi.mocked(fetchImpl).mock.calls.map(([input]) => String(input));
    expect(urls.some((url) => url.endsWith("/lesson-check"))).toBe(false);
  });

  it("setConcept PUTs the new state of one concept mark", async () => {
    const area = memoryArea({ "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } });
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({}), { status: 200 })) as unknown as typeof fetch;
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, area, fetchImpl));
    const reply = (await chrome.send({ type: "panel:setConcept", conceptId: 3, state: "known" })) as PanelReply;
    expect(reply).toEqual({ ok: true });
    const [input, init] = vi.mocked(fetchImpl).mock.calls[0] as unknown as [string, RequestInit];
    expect(String(input).endsWith("/concepts/3/mark")).toBe(true);
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual({ state: "known", evidence: "" });
  });

  it("review and setConcept without a session reply with the auth error", async () => {
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea()));
    expect(await chrome.send({ type: "panel:review" })).toEqual({ ok: false, error: "not signed in" });
    expect(await chrome.send({ type: "panel:setConcept", conceptId: 3, state: "known" })).toEqual({
      ok: false,
      error: "not signed in",
    });
  });

  /** Fake core for the course calls: one ready course (4) and one still processing (5). */
  function courseFetch(openUrl: string) {
    const course = (id: number, status: string) => ({
      id,
      title: `Course ${id}`,
      status,
      concept_ids: [],
      error: null,
      created_at: "",
      updated_at: "",
    });
    return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/v1/courses")) {
        return new Response(JSON.stringify({ items: [course(4, "ready"), course(5, "processing")] }), { status: 200 });
      }
      if (init?.method === "POST" && url.endsWith("/v1/courses/4/open")) {
        return new Response(JSON.stringify({ url: openUrl }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
    }) as unknown as typeof fetch;
  }
  const signedInArea = () => memoryArea({ "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } });

  it("courses lists only the ready courses, as id and title", async () => {
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), courseFetch("http://127.0.0.1:8080/c/4/")));
    const reply = (await chrome.send({ type: "panel:courses" })) as PanelReply;
    expect(reply).toEqual({ ok: true, data: [{ id: 4, title: "Course 4" }] });
  });

  it("openCourse opens the core URL in a new tab", async () => {
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), courseFetch("http://127.0.0.1:8080/c/4/")));
    const reply = (await chrome.send({ type: "panel:openCourse", courseId: 4 })) as PanelReply;
    expect(reply).toEqual({ ok: true });
    expect(chrome.api.tabs.create).toHaveBeenCalledWith({ url: "http://127.0.0.1:8080/c/4/" });
  });

  it("openCourse refuses a URL on a foreign origin and opens no tab", async () => {
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), courseFetch("https://evil.example/c/4/")));
    const reply = (await chrome.send({ type: "panel:openCourse", courseId: 4 })) as PanelReply;
    expect(reply).toEqual({ ok: false, error: "course link is outside the core" });
    expect(chrome.api.tabs.create).not.toHaveBeenCalled();
  });

  it("openCourse refuses a course that is not ready and opens no tab", async () => {
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), courseFetch("http://127.0.0.1:8080/c/5/")));
    const reply = (await chrome.send({ type: "panel:openCourse", courseId: 5 })) as PanelReply;
    expect(reply).toEqual({ ok: false, error: "course is not ready" });
    expect(chrome.api.tabs.create).not.toHaveBeenCalled();
  });

  it("courses and openCourse without a session reply with the auth error", async () => {
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea()));
    expect(await chrome.send({ type: "panel:courses" })).toEqual({ ok: false, error: "not signed in" });
    expect(await chrome.send({ type: "panel:openCourse", courseId: 4 })).toEqual({
      ok: false,
      error: "not signed in",
    });
  });
});
