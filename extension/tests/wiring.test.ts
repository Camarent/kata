import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createBackend, wireBackground, type ChromeLike, type PanelReply } from "../src/background";
import {
  handleContentMessage,
  mountFloatingUi,
  registerContentScript,
  type ContentMessage,
  type RuntimeLike,
} from "../src/content";
import type { ScriptingLike } from "../src/bridgeRegister";
import type { StorageArea } from "../src/tokenStore";
import { PinPositionStore } from "../src/ui/card/pinPosition";
import { SCREENS } from "../src/ui/panel/screens";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/** The approved screen inventory: every id here must have a registry entry. */
const INVENTORY: { id: string; surface: string }[] = JSON.parse(
  readFileSync(join(process.cwd(), "tests/fixtures/screen-inventory.json"), "utf-8"),
);

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
  let updatedListener: ((tabId: number, changes: { url?: string }) => void) | undefined;
  let messageListener:
    | ((message: unknown, sender: unknown, sendResponse: (response: unknown) => void) => boolean | void)
    | undefined;
  const open = vi.fn(async () => undefined);
  /** Bridge registration calls in order: "register:<id>:<matches>" and "unregister:<id>". */
  const calls: string[] = [];
  const scripting: ScriptingLike = {
    async registerContentScripts(scripts) {
      for (const script of scripts) calls.push(`register:${script.id}:${script.matches.join(",")}`);
    },
    async unregisterContentScripts({ ids }) {
      for (const id of ids) calls.push(`unregister:${id}`);
    },
  };
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
      onUpdated: {
        addListener(listener) {
          updatedListener = listener;
        },
      },
      ...overrides,
    },
    runtime: {
      onMessage: {
        addListener(listener) {
          messageListener = listener;
        },
      },
      sendMessage: vi.fn(async () => undefined),
    },
    scripting,
  };
  return {
    api,
    open,
    calls,
    click: (tab: { windowId?: number }) => clickListener?.(tab),
    /** Fires a tab update, as the browser does on navigation. */
    updated: (tabId: number, changes: { url?: string }) => updatedListener?.(tabId, changes),
    /** Sends the content script's page-changed report from tab `tabId`. */
    mutate: (tabId: number) => messageListener?.({ type: "page:mutated" }, { tab: { id: tabId } }, () => undefined),
    /** Sends a runtime message and resolves with what `sendResponse` got. */
    send: (message: unknown, sender: unknown = {}) =>
      new Promise<unknown>((resolve) => {
        const handled = messageListener?.(message, sender, resolve);
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
      sendMessage: async () => undefined,
    };
    registerContentScript(runtime, document);
    let reply: unknown;
    listener?.({ type: "scan" }, {}, (r) => {
      reply = r;
    });
    expect(reply).toMatchObject({ blocks: [{ text: expect.stringContaining("readable") }] });
  });

  it("reports each DOM change to the background while watched, and stops on unwatch", async () => {
    vi.useFakeTimers();
    try {
      document.body.innerHTML = `<p>${LONG}</p>`;
      let listener: ((m: unknown, s: unknown, r: (x: unknown) => void) => boolean | void) | undefined;
      const sent: unknown[] = [];
      const runtime: RuntimeLike = {
        onMessage: {
          addListener(l) {
            listener = l;
          },
        },
        sendMessage: async (message) => {
          sent.push(message);
          return undefined;
        },
      };
      registerContentScript(runtime, document);
      listener?.({ type: "watch" }, {}, () => undefined);
      document.body.appendChild(document.createElement("p"));
      await vi.advanceTimersByTimeAsync(0);
      expect(sent).toEqual([{ type: "page:mutated" }]);
      listener?.({ type: "unwatch" }, {}, () => undefined);
      document.body.appendChild(document.createElement("p"));
      await vi.advanceTimersByTimeAsync(0);
      expect(sent).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
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
    await vi.waitFor(async () => expect(await area.get("kata.markQueue")).toEqual({ "kata.markQueue": [] }));
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

  it("opens the side panel for a card:openPanel message from a page tab", async () => {
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea(), vi.fn() as unknown as typeof fetch));
    expect(await chrome.send({ type: "card:openPanel" }, { tab: { id: 7, windowId: 4 } })).toBeUndefined();
    expect(chrome.open).toHaveBeenCalledWith({ windowId: 4 });
    chrome.open.mockClear();
    await chrome.send({ type: "card:openPanel" }, {});
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
    expect(await area.get("kata.markQueue")).toEqual({
      "kata.markQueue": [{ kind: "topic", id: 9, state: "known" }],
    });
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
        { conceptId: 1, label: "A", state: "known", evidence: "marked", onPage: false },
        { conceptId: 2, label: "B", state: "new", evidence: "", onPage: false },
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

  it("setConcept offline queues the mark, the pending count shows it, and flush sends in order", async () => {
    const area = memoryArea({ "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } });
    let online = false;
    const sent: string[] = [];
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      if (!online) throw new TypeError("fetch failed");
      sent.push(String(input));
      return new Response(JSON.stringify({}), { status: 200 });
    }) as unknown as typeof fetch;
    const chrome = fakeChrome();
    const backend = createBackend(chrome.api, area, fetchImpl);
    wireBackground(chrome.api, backend);
    expect(await chrome.send({ type: "panel:setConcept", conceptId: 3, state: "known" })).toEqual({ ok: true });
    expect(await chrome.send({ type: "panel:setConcept", conceptId: 4, state: "unknown" })).toEqual({ ok: true });
    expect(await chrome.send({ type: "panel:pending" })).toEqual({ ok: true, data: 2 });
    online = true;
    expect(await backend.flush()).toEqual({ sent: 2, dropped: 0, kept: 0 });
    expect(sent.map((url) => url.slice(url.indexOf("/concepts/")))).toEqual(["/concepts/3/mark", "/concepts/4/mark"]);
    expect(await chrome.send({ type: "panel:pending" })).toEqual({ ok: true, data: 0 });
  });

  it("setConcept rethrows an auth error instead of queueing it", async () => {
    const area = memoryArea({ "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } });
    const fetchImpl = vi.fn(async () => new Response(null, { status: 401 })) as unknown as typeof fetch;
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, area, fetchImpl));
    const reply = (await chrome.send({ type: "panel:setConcept", conceptId: 3, state: "known" })) as PanelReply;
    expect(reply.ok).toBe(false);
    expect(await area.get("kata.markQueue")).toEqual({});
  });

  it("pending count is zero without a session", async () => {
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea()));
    expect(await chrome.send({ type: "panel:pending" })).toEqual({ ok: true, data: 0 });
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
        return new Response(
          JSON.stringify({ items: [course(4, "ready"), course(5, "processing")], limit: 5, total: 2 }),
          { status: 200 },
        );
      }
      if (init?.method === "POST" && url.endsWith("/v1/courses/4/open")) {
        return new Response(JSON.stringify({ url: openUrl }), { status: 200 });
      }
      if (init?.method === "DELETE" && url.endsWith("/v1/courses/4")) {
        return new Response(null, { status: 204 });
      }
      return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
    }) as unknown as typeof fetch;
  }
  const signedInArea = () => memoryArea({ "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } });

  it("courses lists only the ready courses, as id and title, with the limit and total", async () => {
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), courseFetch("http://127.0.0.1:8080/c/4/")));
    const reply = (await chrome.send({ type: "panel:courses" })) as PanelReply;
    expect(reply).toEqual({
      ok: true,
      data: { items: [{ id: 4, title: "Course 4" }], limit: 5, total: 2 },
    });
  });

  it("deleteCourse deletes the course and replies ok on 204", async () => {
    const chrome = fakeChrome();
    const fetchImpl = courseFetch("http://127.0.0.1:8080/c/4/");
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl));
    const reply = (await chrome.send({ type: "panel:deleteCourse", courseId: 4 })) as PanelReply;
    expect(reply).toEqual({ ok: true });
    const deleteCall = vi.mocked(fetchImpl).mock.calls.find(([, init]) => init?.method === "DELETE");
    expect(String(deleteCall?.[0])).toBe("http://127.0.0.1:8080/v1/courses/4");
  });

  it("deleteCourse replies ok when the course is already gone (404)", async () => {
    const chrome = fakeChrome();
    const gone = vi.fn(async () => new Response(JSON.stringify({ detail: "not found" }), { status: 404 }));
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), gone as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:deleteCourse", courseId: 4 })).toEqual({ ok: true });
  });

  /** Fake core that answers every call with one status and body; the request is kept for inspection. */
  function createFetch(status: number, body: unknown) {
    return vi.fn(async () => new Response(JSON.stringify(body), { status }));
  }

  it("createCourse posts the title and replies ok on 202", async () => {
    const chrome = fakeChrome();
    const fetchImpl = createFetch(202, { id: 6, title: "Rust basics", status: "processing" });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    const reply = (await chrome.send({ type: "panel:createCourse", title: "Rust basics" })) as PanelReply;
    expect(reply).toEqual({ ok: true });
    const [url, init] = vi.mocked(fetchImpl).mock.calls[0] as [RequestInfo | URL, RequestInit];
    expect(String(url)).toBe("http://127.0.0.1:8080/v1/courses");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ title: "Rust basics" });
  });

  it("createCourse replies with the core status and course_limit code on 409", async () => {
    const chrome = fakeChrome();
    const fetchImpl = createFetch(409, { detail: { code: "course_limit", message: "course limit of 3 reached" } });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    const reply = (await chrome.send({ type: "panel:createCourse", title: "X" })) as PanelReply;
    expect(reply).toMatchObject({ ok: false, status: 409, code: "course_limit" });
    expect(reply).toEqual(expect.objectContaining({ error: expect.any(String) }));
  });

  it("createCourse replies with the course_name_taken code on 409", async () => {
    const chrome = fakeChrome();
    const fetchImpl = createFetch(409, { detail: { code: "course_name_taken", message: "taken" } });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    const reply = (await chrome.send({ type: "panel:createCourse", title: "X" })) as PanelReply;
    expect(reply).toMatchObject({ ok: false, status: 409, code: "course_name_taken" });
  });

  it("regenerateCourse posts to the core regenerate route and replies ok on 202", async () => {
    const chrome = fakeChrome();
    const fetchImpl = createFetch(202, { id: 7, title: "Rust basics", status: "processing" });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    const reply = (await chrome.send({ type: "panel:regenerateCourse", courseId: 7 })) as PanelReply;
    expect(reply).toEqual({ ok: true });
    const [url, init] = vi.mocked(fetchImpl).mock.calls[0] as [RequestInfo | URL, RequestInit];
    expect(String(url)).toBe("http://127.0.0.1:8080/v1/courses/7/regenerate");
    expect(init.method).toBe("POST");
  });

  it("regenerateCourse replies with the core status and code on 409", async () => {
    const chrome = fakeChrome();
    const fetchImpl = createFetch(409, { detail: { code: "course_limit", message: "course limit of 3 reached" } });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    const reply = (await chrome.send({ type: "panel:regenerateCourse", courseId: 7 })) as PanelReply;
    expect(reply).toMatchObject({ ok: false, status: 409, code: "course_limit" });
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
    expect(await chrome.send({ type: "panel:deleteCourse", courseId: 4 })).toEqual({
      ok: false,
      error: "not signed in",
    });
  });
});

/** Fake core for sign-in: the health probe and the enrol call; each answer can be replaced. */
function signInFetch(
  health: () => Response = () => new Response(JSON.stringify({ status: "ok", checks: {} }), { status: 200 }),
  enrol: () => Response = () => new Response(JSON.stringify({ token: "tok-new" }), { status: 200 }),
) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    return url.endsWith("/v1/health/deep") ? health() : enrol();
  }) as unknown as typeof fetch;
}

describe("background tracks, exam results and ignored list wiring", () => {
  /** Fake core that answers every call with one status and body; the request is kept for inspection. */
  const coreReply = (status: number, body: unknown) =>
    vi.fn(async () => new Response(status === 204 ? null : JSON.stringify(body), { status }));
  const signedInArea = () => memoryArea({ "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } });
  const track = { id: 3, name: "Rust", deadline: "2026-12-01", priority: 1, status: "active", items: [], created_at: "", updated_at: "" };
  const sentTo = (fetchImpl: unknown, index = 0) => vi.mocked(fetchImpl as ReturnType<typeof vi.fn>).mock.calls[index] as [RequestInfo | URL, RequestInit | undefined];

  it("tracks lists one page with the limit and the before_id query", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(200, { items: [track], next_before_id: null });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    const result = (await chrome.send({ type: "panel:tracks", limit: 5, beforeId: 12 })) as PanelReply;
    expect(result).toEqual({ ok: true, data: { items: [track], next_before_id: null } });
    expect(String(sentTo(fetchImpl)[0])).toBe("http://127.0.0.1:8080/v1/tracks?limit=5&before_id=12");
  });

  it("getTrack reads one track by id", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(200, track);
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:getTrack", trackId: 3 })).toEqual({ ok: true, data: track });
    expect(String(sentTo(fetchImpl)[0])).toBe("http://127.0.0.1:8080/v1/tracks/3");
  });

  it("createTrack posts the track input and replies with the new track", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(201, track);
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    const input = { name: "Rust", deadline: "2026-12-01" };
    expect(await chrome.send({ type: "panel:createTrack", input })).toEqual({ ok: true, data: track });
    const [url, init] = sentTo(fetchImpl);
    expect(String(url)).toBe("http://127.0.0.1:8080/v1/tracks");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual(input);
  });

  it("patchTrack sends only the patch fields to the track", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(200, { ...track, status: "paused" });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    const reply = (await chrome.send({ type: "panel:patchTrack", trackId: 3, patch: { status: "paused" } })) as PanelReply;
    expect(reply).toEqual({ ok: true, data: { ...track, status: "paused" } });
    const [url, init] = sentTo(fetchImpl);
    expect(String(url)).toBe("http://127.0.0.1:8080/v1/tracks/3");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ status: "paused" });
  });

  it("deleteTrack deletes the track and replies ok on 204", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(204, null);
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:deleteTrack", trackId: 3 })).toEqual({ ok: true });
    expect(sentTo(fetchImpl)[1]?.method).toBe("DELETE");
  });

  it("addDecisionPoint posts the point after a plan position", async () => {
    const chrome = fakeChrome();
    const point = { id: 8, track_id: 3, after_position: 2, due_on: "2026-12-05" };
    const fetchImpl = coreReply(201, point);
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    const input = { after_position: 2, due_on: "2026-12-05" };
    expect(await chrome.send({ type: "panel:addDecisionPoint", trackId: 3, input })).toEqual({ ok: true, data: point });
    const [url, init] = sentTo(fetchImpl);
    expect(String(url)).toBe("http://127.0.0.1:8080/v1/tracks/3/decision-points");
    expect(JSON.parse(String(init?.body))).toEqual(input);
  });

  it("addQuizSource queues the URL and replies with the job id", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(202, { id: 9 });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:addQuizSource", url: "https://example.org/q" })).toEqual({ ok: true, data: 9 });
    const [url, init] = sentTo(fetchImpl);
    expect(String(url)).toBe("http://127.0.0.1:8080/quiz/sources");
    expect(JSON.parse(String(init?.body))).toEqual({ url: "https://example.org/q" });
  });

  it("panel:miniQuiz fetches the mini quiz and replies with its questions", async () => {
    const chrome = fakeChrome();
    const questions = [{ id: 4, question: "What is SYN?" }];
    const fetchImpl = coreReply(200, questions);
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:miniQuiz" })).toEqual({ ok: true, data: questions });
    const [url, init] = sentTo(fetchImpl);
    expect(String(url)).toBe("http://127.0.0.1:8080/quiz/mini");
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("importExamResult posts the raw payload and replies with the stored result", async () => {
    const chrome = fakeChrome();
    const result = { id: 2, origin: "exam", taken_at: "", passed: null, score: null, status: "pending", concepts: [] };
    const fetchImpl = coreReply(200, result);
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:importExamResult", payload: '{"score":7}' })).toEqual({ ok: true, data: result });
    const [url, init] = sentTo(fetchImpl);
    expect(String(url)).toBe("http://127.0.0.1:8080/exams/import");
    expect(String(init?.body)).toBe('{"score":7}');
  });

  it("confirmExamResult posts the confirmed concept ids", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(200, { id: 2, status: "confirmed", concepts: [] });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    await chrome.send({ type: "panel:confirmExamResult", resultId: 2, conceptIds: [4, 5] });
    const [url, init] = sentTo(fetchImpl);
    expect(String(url)).toBe("http://127.0.0.1:8080/exams/2/confirm");
    expect(JSON.parse(String(init?.body))).toEqual({ concept_ids: [4, 5] });
  });

  it("dismissExamResult posts to the dismiss route", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(200, { id: 2, status: "dismissed", concepts: [] });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    await chrome.send({ type: "panel:dismissExamResult", resultId: 2 });
    expect(String(sentTo(fetchImpl)[0])).toBe("http://127.0.0.1:8080/exams/2/dismiss");
  });

  it("ignored lists the ignored concepts; ignoreConcept and unignoreConcept use the ignore route", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(200, [{ concept_id: 4, label: "Borrow" }]);
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:ignored" })).toEqual({ ok: true, data: [{ concept_id: 4, label: "Borrow" }] });
    expect(await chrome.send({ type: "panel:ignoreConcept", conceptId: 4 })).toEqual({ ok: true });
    expect(sentTo(fetchImpl, 1)[1]?.method).toBe("PUT");
    expect(await chrome.send({ type: "panel:unignoreConcept", conceptId: 4 })).toEqual({ ok: true });
    expect(sentTo(fetchImpl, 2)[1]?.method).toBe("DELETE");
    expect(String(sentTo(fetchImpl, 2)[0])).toBe("http://127.0.0.1:8080/concepts/4/ignore");
  });

  it("a refused track write replies with the core status and code", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(409, { detail: { code: "track_name_taken", message: "taken" } });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    const reply = await chrome.send({ type: "panel:createTrack", input: { name: "Rust", deadline: "2026-12-01" } });
    expect(reply).toMatchObject({ ok: false, status: 409, code: "track_name_taken" });
  });

  it("track, exam and ignored messages without a session reply with the auth error", async () => {
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea()));
    expect(await chrome.send({ type: "panel:tracks" })).toEqual({ ok: false, error: "not signed in" });
    expect(await chrome.send({ type: "panel:ignored" })).toEqual({ ok: false, error: "not signed in" });
    expect(await chrome.send({ type: "panel:dismissExamResult", resultId: 2 })).toEqual({ ok: false, error: "not signed in" });
  });
});

describe("background feed tabs wiring: aliases, summary and jokes", () => {
  /** Fake core that answers every call with one status and body; the request is kept for inspection. */
  const coreReply = (status: number, body: unknown) =>
    vi.fn(async () => new Response(status === 204 ? null : JSON.stringify(body), { status }));
  const signedInArea = () => memoryArea({ "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } });
  const sentTo = (fetchImpl: unknown, index = 0) => vi.mocked(fetchImpl as ReturnType<typeof vi.fn>).mock.calls[index] as [RequestInfo | URL, RequestInit | undefined];

  it("markConceptViewed stamps the concept and replies ok on 204", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(204, null);
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:markConceptViewed", conceptId: 3 })).toEqual({ ok: true });
    expect(sentTo(fetchImpl)[1]?.method).toBe("POST");
    expect(String(sentTo(fetchImpl)[0])).toBe("http://127.0.0.1:8080/concepts/3/viewed");
  });

  it("listConceptAliases gets the aliases of one concept", async () => {
    const chrome = fakeChrome();
    const rows = [{ alias: "parts", shared: false }];
    const fetchImpl = coreReply(200, rows);
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:listConceptAliases", conceptId: 3 })).toEqual({ ok: true, data: rows });
    expect(String(sentTo(fetchImpl)[0])).toBe("http://127.0.0.1:8080/concepts/3/aliases");
  });

  it("addConceptAlias posts the alias and replies with the new alias", async () => {
    const chrome = fakeChrome();
    const row = { alias: "parts", shared: false };
    const fetchImpl = coreReply(201, row);
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:addConceptAlias", conceptId: 3, alias: "parts" })).toEqual({ ok: true, data: row });
    const [url, init] = sentTo(fetchImpl);
    expect(String(url)).toBe("http://127.0.0.1:8080/concepts/3/aliases");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ alias: "parts" });
  });

  it("addConceptAlias replies with the core 409 status and code when the alias exists", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(409, { detail: { code: "alias_exists", message: "taken" } });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    const reply = await chrome.send({ type: "panel:addConceptAlias", conceptId: 3, alias: "parts" });
    expect(reply).toMatchObject({ ok: false, status: 409, code: "alias_exists" });
  });

  it("requestSummary posts the url and text and replies with the summary or the job id", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(200, { status: "done", summary: "short" });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:requestSummary", url: "https://p", text: "page" })).toEqual({
      ok: true,
      data: { status: "done", summary: "short" },
    });
    const [url, init] = sentTo(fetchImpl);
    expect(String(url)).toBe("http://127.0.0.1:8080/summary");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ url: "https://p", text: "page" });
  });

  it("cachedSummary gets the cached summary by url and text hash, null when nothing is cached", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(200, { summary: "short" });
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:cachedSummary", url: "https://p", textSha256: "abc" })).toEqual({ ok: true, data: "short" });
    expect(String(sentTo(fetchImpl)[0])).toBe("http://127.0.0.1:8080/summary?url=https%3A%2F%2Fp&text_sha256=abc");
    const missingChrome = fakeChrome();
    const missing = coreReply(404, { detail: "summary not found" });
    wireBackground(missingChrome.api, createBackend(missingChrome.api, signedInArea(), missing as unknown as typeof fetch));
    expect(await missingChrome.send({ type: "panel:cachedSummary", url: "https://p", textSha256: "abc" })).toEqual({ ok: true, data: null });
  });

  it("nextJoke replies with the joke, or null when jokes are off", async () => {
    const chrome = fakeChrome();
    const joke = { id: 1, text: "Why?", source: "local" };
    const fetchImpl = coreReply(200, joke);
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:nextJoke" })).toEqual({ ok: true, data: joke });
    expect(String(sentTo(fetchImpl)[0])).toBe("http://127.0.0.1:8080/jokes/next");
    const offChrome = fakeChrome();
    const off = coreReply(404, { detail: "jokes disabled" });
    wireBackground(offChrome.api, createBackend(offChrome.api, signedInArea(), off as unknown as typeof fetch));
    expect(await offChrome.send({ type: "panel:nextJoke" })).toEqual({ ok: true, data: null });
  });

  it("listJokeSources lists the enabled sources in order", async () => {
    const chrome = fakeChrome();
    const sources = [{ id: 2, name: "dad jokes", enabled: true }];
    const fetchImpl = coreReply(200, sources);
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:listJokeSources" })).toEqual({ ok: true, data: sources });
    expect(String(sentTo(fetchImpl)[0])).toBe("http://127.0.0.1:8080/jokes/sources");
  });

  it("ignored list round trip: Restore unignores and Undo ignores again, on the ignore route", async () => {
    const chrome = fakeChrome();
    const fetchImpl = coreReply(204, null);
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    expect(await chrome.send({ type: "panel:unignoreConcept", conceptId: 5 })).toEqual({ ok: true });
    expect(sentTo(fetchImpl)[1]?.method).toBe("DELETE");
    expect(await chrome.send({ type: "panel:ignoreConcept", conceptId: 5 })).toEqual({ ok: true });
    expect(sentTo(fetchImpl, 1)[1]?.method).toBe("PUT");
    expect(String(sentTo(fetchImpl, 1)[0])).toBe("http://127.0.0.1:8080/concepts/5/ignore");
  });

  it("settings local model status queues a modelhost.status job and replies with its output", async () => {
    const chrome = fakeChrome();
    const fetchImpl = vi.fn(async (url: RequestInfo | URL) =>
      String(url).endsWith("/jobs")
        ? new Response(JSON.stringify({ id: 7 }), { status: 200 })
        : new Response(JSON.stringify({ status: "done", output: { ok: true, text: "up" } }), { status: 200 }),
    );
    wireBackground(chrome.api, createBackend(chrome.api, signedInArea(), fetchImpl as unknown as typeof fetch));
    const reply = await chrome.send({ type: "panel:modelhost", request: { action: "status" } });
    expect(reply).toEqual({ ok: true, data: { ok: true, text: "up" } });
    expect(String(sentTo(fetchImpl)[0])).toBe("http://127.0.0.1:8080/jobs");
    expect(JSON.parse(String(sentTo(fetchImpl)[1]?.body))).toEqual({ payload: "{}", kind: "modelhost.status" });
    expect(String(sentTo(fetchImpl, 1)[0])).toBe("http://127.0.0.1:8080/jobs/7");
  });

  it("feed tab messages without a session reply with the auth error", async () => {
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea()));
    expect(await chrome.send({ type: "panel:nextJoke" })).toEqual({ ok: false, error: "not signed in" });
    expect(await chrome.send({ type: "panel:requestSummary", url: "https://p", text: "page" })).toEqual({ ok: false, error: "not signed in" });
  });
});

describe("sign-in, server change and disconnect", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("probes the typed server, enrols the code and saves the normalised origin", async () => {
    const area = memoryArea();
    const fetchImpl = signInFetch();
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, area, fetchImpl));
    const input = { baseUrl: "http://kata.lan:9000/base/", code: "ABC123", deviceLabel: "laptop" };
    expect(await chrome.send({ type: "panel:signIn", input })).toEqual({ ok: true });
    expect(await area.get("kata.session")).toEqual({
      "kata.session": { baseUrl: "http://kata.lan:9000/base", token: "tok-new" },
    });
    const urls = vi.mocked(fetchImpl).mock.calls.map(([url]) => String(url));
    expect(urls).toEqual(["http://kata.lan:9000/base/v1/health/deep", "http://kata.lan:9000/base/auth/enrol"]);
    const enrolBody = vi.mocked(fetchImpl).mock.calls[1]?.[1]?.body;
    expect(JSON.parse(String(enrolBody))).toEqual({ code: "ABC123", label: "laptop" });
    expect(chrome.calls).toEqual(["unregister:kata-bridge", "register:kata-bridge:http://*/c/*"]);
  });

  it("refuses an invalid server URL before any request", async () => {
    const area = memoryArea();
    const fetchImpl = signInFetch();
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, area, fetchImpl));
    const reply = await chrome.send({ type: "panel:signIn", input: { baseUrl: "ftp://kata.lan", code: "x", deviceLabel: "d" } });
    expect(reply).toEqual({ ok: false, error: "server URL must use http or https" });
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(await area.get("kata.session")).toEqual({});
  });

  it("reports an unreachable server and saves nothing", async () => {
    const area = memoryArea();
    const fetchImpl = signInFetch(() => {
      throw new TypeError("fetch failed");
    });
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, area, fetchImpl));
    const input = { baseUrl: "http://kata.lan:9000", code: "ABC123", deviceLabel: "laptop" };
    expect(await chrome.send({ type: "panel:signIn", input })).toEqual({ ok: false, error: "core is unreachable" });
    expect(vi.mocked(fetchImpl)).toHaveBeenCalledTimes(1);
    expect(await area.get("kata.session")).toEqual({});
  });

  it("reports an address that does not answer as a kata core", async () => {
    const area = memoryArea();
    const fetchImpl = signInFetch(() => new Response("<html>not kata</html>", { status: 200 }));
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, area, fetchImpl));
    const input = { baseUrl: "http://example.org", code: "ABC123", deviceLabel: "laptop" };
    expect(await chrome.send({ type: "panel:signIn", input })).toEqual({
      ok: false,
      error: "address does not answer as a kata core",
    });
    expect(vi.mocked(fetchImpl)).toHaveBeenCalledTimes(1);
    expect(await area.get("kata.session")).toEqual({});
  });

  it("reports a bad code (HTTP 401) and saves nothing", async () => {
    const area = memoryArea();
    const fetchImpl = signInFetch(undefined, () => new Response(JSON.stringify({ detail: "bad code" }), { status: 401 }));
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, area, fetchImpl));
    const input = { baseUrl: "http://kata.lan:9000", code: "WRONG", deviceLabel: "laptop" };
    expect(await chrome.send({ type: "panel:signIn", input })).toEqual({
      ok: false,
      error: "core rejected the credentials",
    });
    expect(await area.get("kata.session")).toEqual({});
    expect(chrome.calls).toEqual([]);
  });

  it("changing the server replaces the session and moves the bridge to the new origin", async () => {
    const area = memoryArea();
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, area, signInFetch()));
    await chrome.send({ type: "panel:signIn", input: { baseUrl: "http://127.0.0.1:8080", code: "A", deviceLabel: "d" } });
    await chrome.send({ type: "panel:signIn", input: { baseUrl: "https://kata.example:9443", code: "B", deviceLabel: "d" } });
    expect(await area.get("kata.session")).toEqual({
      "kata.session": { baseUrl: "https://kata.example:9443", token: "tok-new" },
    });
    expect(chrome.calls).toEqual([
      "unregister:kata-bridge",
      "register:kata-bridge:http://*/c/*",
      "unregister:kata-bridge",
      "register:kata-bridge:https://*/c/*",
    ]);
  });

  it("openCourse accepts only the origin of the saved session", async () => {
    const area = memoryArea({ "kata.session": { baseUrl: "https://kata.example:9443", token: "t" } });
    const chrome = fakeChrome();
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/v1/courses")) {
        return new Response(JSON.stringify({ items: [{ id: 4, title: "C", status: "ready", concept_ids: [], error: null, created_at: "", updated_at: "" }] }), { status: 200 });
      }
      if (init?.method === "POST" && url.endsWith("/v1/courses/4/open")) {
        return new Response(JSON.stringify({ url: "http://127.0.0.1:8080/c/4/" }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
    }) as unknown as typeof fetch;
    wireBackground(chrome.api, createBackend(chrome.api, area, fetchImpl));
    const reply = (await chrome.send({ type: "panel:openCourse", courseId: 4 })) as PanelReply;
    expect(reply).toEqual({ ok: false, error: "course link is outside the core" });
    expect(chrome.api.tabs.create).not.toHaveBeenCalled();
  });

  it("disconnect clears the session and the bridge but keeps the offline queue", async () => {
    const area = memoryArea({
      "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" },
      "kata.pending": [3],
    });
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, area, signInFetch()));
    expect(await chrome.send({ type: "panel:disconnect" })).toEqual({ ok: true });
    expect(await area.get("kata.session")).toEqual({});
    expect(await area.get("kata.pending")).toEqual({ "kata.pending": [3] });
    expect(chrome.calls).toEqual(["unregister:kata-bridge"]);
    expect(await chrome.send({ type: "panel:scan" })).toEqual({ ok: false, error: "not signed in" });
  });
});

/** Fake core for the concept scan: a stored classification, then one finished job with `output`. */
function conceptFetch(output: unknown) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === "POST" && url.endsWith("/jobs")) {
      return new Response(JSON.stringify({ id: 1 }), { status: 201 });
    }
    if (url.includes("/scan/classification")) {
      const body = { area_id: 2, topic_id: 5, area: "a", topic: "t", candidates: [] };
      return new Response(JSON.stringify(body), { status: 200 });
    }
    return new Response(JSON.stringify({ status: "done", output }), { status: 200 });
  }) as unknown as typeof fetch;
}

/** Extraction output: one block with a known, an ignored and an unknown concept. */
const CONCEPT_OUTPUT = {
  blocks: [
    {
      blockId: "b1",
      concepts: [
        { word: "alpha", conceptId: 10, state: "known" },
        { word: "beta", conceptId: 11, state: "ignored" },
        { word: "gamma", conceptId: 12, state: "unknown" },
      ],
    },
  ],
};

/** Page scan answers with one block; any other content message gets no answer. */
const pageBlocks = async (_tabId: number, message: ContentMessage) =>
  message.type === "scan" ? { blocks: [{ id: "b1", text: LONG }] } : undefined;

describe("background concept scan and rescan", () => {
  const SESSION = { "kata.session": { baseUrl: "http://127.0.0.1:8080", token: "t" } };
  const PAGE = [{ id: 7, url: "https://ex.test/page?x=1#top" }];

  beforeEach(() => {
    vi.useRealTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("scanConcepts replies with the page concepts, ignored ones dropped, keyed by the URL without fragment", async () => {
    const fetchImpl = conceptFetch(CONCEPT_OUTPUT);
    const chrome = fakeChrome({ query: vi.fn(async () => PAGE), sendMessage: vi.fn(pageBlocks) });
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea(SESSION), fetchImpl));
    const reply = (await chrome.send({ type: "panel:scanConcepts" })) as PanelReply;
    expect(reply).toEqual({
      ok: true,
      data: {
        areaId: 2,
        topicId: 5,
        area: "a",
        topic: "t",
        blocks: [
          {
            blockId: "b1",
            concepts: [
              { word: "alpha", conceptId: 10, state: "known" },
              { word: "gamma", conceptId: 12, state: "unknown" },
            ],
          },
        ],
      },
    });
    const keyed = (fetchImpl as unknown as { mock: { calls: [RequestInfo | URL][] } }).mock.calls.some(([url]) =>
      String(url).includes(`page_key=${encodeURIComponent("https://ex.test/page?x=1")}`),
    );
    expect(keyed).toBe(true);
  });

  it("review marks concepts on the page only while the active tab shows the scanned page", async () => {
    const scanFetch = conceptFetch(CONCEPT_OUTPUT);
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/lesson-check")) {
        const results = [{ concept_id: 10, label: "alpha", state: "known", source: "", evidence: "" }];
        return new Response(JSON.stringify({ results }), { status: 200 });
      }
      if (url.includes("/concept-marks") || url.includes("/marks")) {
        const marks = [{ concept_id: 10, label: "alpha", state: "known", evidence: "", created_at: "", updated_at: "" }];
        return new Response(JSON.stringify(marks), { status: 200 });
      }
      return scanFetch(input, init);
    }) as unknown as typeof fetch;
    let tabs = PAGE;
    const chrome = fakeChrome({ query: vi.fn(async () => tabs), sendMessage: vi.fn(pageBlocks) });
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea(SESSION), fetchImpl));
    await chrome.send({ type: "panel:scanConcepts" });
    const same = (await chrome.send({ type: "panel:review" })) as PanelReply;
    expect(same).toMatchObject({ ok: true, data: [{ conceptId: 10, onPage: true, area: "a" }] });
    tabs = [{ id: 7, url: "https://ex.test/other" }];
    const other = (await chrome.send({ type: "panel:review" })) as PanelReply;
    expect(other).toMatchObject({ ok: true, data: [{ conceptId: 10, onPage: false }] });
  });

  it("scanConcepts reports a page without blocks as an error reply", async () => {
    const chrome = fakeChrome({ query: vi.fn(async () => PAGE), sendMessage: vi.fn(async () => undefined) });
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea(SESSION)));
    const reply = (await chrome.send({ type: "panel:scanConcepts" })) as PanelReply;
    expect(reply).toEqual({ ok: true, data: { error: "page gave no blocks" } });
  });

  it("chooseConcept, reassignConcept and topicOverview call the core with the topic and word", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/scan/overview?topic_id=5")) {
        const body = { topic_id: 5, area: "a", topic: "t", counts: { new: 1, learning: 0, known: 1 }, concepts: [] };
        return new Response(JSON.stringify(body), { status: 200 });
      }
      return new Response(null, { status: 204 });
    }) as unknown as typeof fetch;
    const chrome = fakeChrome();
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea(SESSION), fetchImpl));
    expect(await chrome.send({ type: "panel:chooseConcept", topicId: 5, word: "alpha", conceptId: 10 })).toEqual({ ok: true });
    expect(await chrome.send({ type: "panel:reassignConcept", topicId: 5, word: "alpha", fromConceptId: 10, toConceptId: 12 })).toEqual({ ok: true });
    const posted = (fetchImpl as unknown as { mock: { calls: [string, RequestInit?][] } }).mock.calls.filter(
      ([url]) => url.endsWith("/scan/choice") || url.endsWith("/scan/reassign"),
    );
    expect(posted.map(([url, init]) => [url.split("/").pop(), JSON.parse(String(init?.body))])).toEqual([
      ["choice", { topic_id: 5, word: "alpha", concept_id: 10 }],
      ["reassign", { topic_id: 5, word: "alpha", from_concept_id: 10, to_concept_id: 12 }],
    ]);
    const overview = (await chrome.send({ type: "panel:topicOverview", topicId: 5 })) as PanelReply;
    expect(overview).toEqual({
      ok: true,
      data: { topicId: 5, area: "a", topic: "t", counts: { new: 1, learning: 0, known: 1 }, concepts: [] },
    });
  });

  it("a burst of page changes runs one rescan after the debounce, with fake timers", async () => {
    vi.useFakeTimers();
    const sendMessage = vi.fn(pageBlocks);
    const chrome = fakeChrome({ query: vi.fn(async () => PAGE), sendMessage });
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea(SESSION), conceptFetch(CONCEPT_OUTPUT)));
    await chrome.send({ type: "panel:scanConcepts" });
    const scans = () => sendMessage.mock.calls.filter(([, message]) => message.type === "scan").length;
    expect(sendMessage).toHaveBeenCalledWith(7, { type: "watch" });
    expect(scans()).toBe(1);

    chrome.mutate(7);
    await vi.advanceTimersByTimeAsync(1000);
    chrome.mutate(7);
    await vi.advanceTimersByTimeAsync(1000);
    chrome.mutate(7);
    await vi.advanceTimersByTimeAsync(1499);
    expect(scans()).toBe(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(scans()).toBe(2);
    await vi.advanceTimersByTimeAsync(5000);
    expect(scans()).toBe(2);
  });

  it("sign-out stops the rescan: no further scan and the page is told to unwatch", async () => {
    vi.useFakeTimers();
    const sendMessage = vi.fn(pageBlocks);
    const chrome = fakeChrome({ query: vi.fn(async () => PAGE), sendMessage });
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea(SESSION), conceptFetch(CONCEPT_OUTPUT)));
    await chrome.send({ type: "panel:scanConcepts" });
    chrome.mutate(7);
    expect(await chrome.send({ type: "panel:disconnect" })).toEqual({ ok: true });
    expect(sendMessage).toHaveBeenCalledWith(7, { type: "unwatch" });
    chrome.mutate(7);
    await vi.advanceTimersByTimeAsync(5000);
    expect(sendMessage.mock.calls.filter(([, message]) => message.type === "scan")).toHaveLength(1);
  });

  it("navigating the watched tab stops its rescan", async () => {
    vi.useFakeTimers();
    const sendMessage = vi.fn(pageBlocks);
    const chrome = fakeChrome({ query: vi.fn(async () => PAGE), sendMessage });
    wireBackground(chrome.api, createBackend(chrome.api, memoryArea(SESSION), conceptFetch(CONCEPT_OUTPUT)));
    await chrome.send({ type: "panel:scanConcepts" });
    chrome.updated(8, { url: "https://other.test/" });
    chrome.updated(7, {});
    chrome.mutate(7);
    await vi.advanceTimersByTimeAsync(2000);
    expect(sendMessage.mock.calls.filter(([, message]) => message.type === "scan")).toHaveLength(2);
    chrome.updated(7, { url: "https://ex.test/next" });
    expect(sendMessage).toHaveBeenCalledWith(7, { type: "unwatch" });
    chrome.mutate(7);
    await vi.advanceTimersByTimeAsync(2000);
    expect(sendMessage.mock.calls.filter(([, message]) => message.type === "scan")).toHaveLength(2);
  });
});

describe("content script floating UI mount", () => {
  it("injects the card stylesheet and mounts the pin and cards into the page, then removes them", async () => {
    document.body.innerHTML = "";
    const styleCount = document.head.querySelectorAll("style").length;
    const sent: unknown[] = [];
    const runtime = {
      async sendMessage(message: unknown) {
        sent.push(message);
        return {
          ok: true,
          data: {
            areaId: 1,
            topicId: 1,
            area: "a",
            topic: "t",
            blocks: [
              {
                blockId: "b1",
                concepts: [
                  { word: "x", conceptId: 1, label: "X", definition: "", state: "new", candidates: [] },
                  { word: "y", conceptId: 2, label: "Y", definition: "", state: "known", candidates: [] },
                ],
              },
            ],
          },
        };
      },
    };
    const ui = await mountFloatingUi(document, memoryArea(), runtime);
    try {
      expect(document.head.querySelectorAll("style")).toHaveLength(styleCount + 1);
      expect(Array.from(document.head.querySelectorAll("style")).at(-1)?.textContent).toContain(".pinwrap");
      expect(document.body.contains(ui.pin.element)).toBe(true);
      expect(ui.pin.element.classList.contains("float")).toBe(true);

      // The expanded mascot only opens its undo menu; the collapsed icon opens the main card.
      expect(document.querySelector(".card-main")).toBeNull();
      ui.pin.element.querySelector<HTMLButtonElement>(".pinwrap .pinbtn")?.click();
      expect(document.querySelector(".card-main")).toBeNull();
      ui.pin.collapse();
      Array.from(ui.pin.element.querySelectorAll<HTMLButtonElement>(".pinbtn"))
        .find((button) => !button.closest(".pinwrap"))
        ?.click();
      expect(document.querySelector(".card-main")).not.toBeNull();
      // Scan asks the background and shows the counts.
      document.querySelector<HTMLButtonElement>(".card-main .scan")?.click();
      await vi.waitFor(() => expect(document.querySelector(".card-scan .status.done")).not.toBeNull());
      // The scan also asks for a joke to show while it runs.
      expect(sent).toEqual([{ type: "panel:nextJoke" }, { type: "panel:scanConcepts" }]);
      expect(document.querySelector(".card-scan .status")?.textContent).toContain("2");

      // A page change after the scan shows the page-changed prompt.
      document.body.append(document.createElement("p"));
      await vi.waitFor(() => expect(document.querySelector(".page-changed")).not.toBeNull());
    } finally {
      ui.dispose();
      try {
        // dispose must take down the pin, the injected stylesheet and the host by itself.
        expect(document.body.contains(ui.pin.element)).toBe(false);
        expect(document.head.querySelectorAll("style")).toHaveLength(styleCount);
      } finally {
        document.head.querySelectorAll("style").forEach((style, index) => {
          if (index >= styleCount) style.remove();
        });
      }
    }
    expect(document.querySelector(".card-host")).toBeNull();
  });

  it("summary button sends the page text to the background and shows the summary", async () => {
    document.body.innerHTML = "";
    const sent: unknown[] = [];
    const runtime = {
      async sendMessage(message: unknown) {
        sent.push(message);
        if ((message as { type: string }).type === "panel:requestSummary") {
          return { ok: true, data: { status: "done", summary: "A page about TCP." } };
        }
        return {
          ok: true,
          data: {
            blocks: [
              {
                blockId: "b1",
                concepts: [{ word: "x", conceptId: 1, label: "X", definition: "", state: "new", candidates: [] }],
              },
            ],
          },
        };
      },
    };
    const ui = await mountFloatingUi(document, memoryArea(), runtime);
    try {
      ui.pin.collapse();
      Array.from(ui.pin.element.querySelectorAll<HTMLButtonElement>(".pinbtn"))
        .find((button) => !button.closest(".pinwrap"))
        ?.click();
      document.querySelector<HTMLButtonElement>(".card-main .scan")?.click();
      await vi.waitFor(() => expect(document.querySelector(".card-scan .status.done")).not.toBeNull());
      document.querySelector<HTMLButtonElement>(".card-scan .back")?.click();
      document.querySelector<HTMLButtonElement>(".card-main .summary")?.click();
      await vi.waitFor(() => expect(document.querySelector(".card-summary")?.textContent).toContain("A page about TCP."));
      const request = sent.find((message) => (message as { type: string }).type === "panel:requestSummary");
      expect(request).toEqual(expect.objectContaining({ type: "panel:requestSummary", url: document.location.href }));
    } finally {
      ui.dispose();
    }
    expect(document.querySelector(".card-host")).toBeNull();
  });

  /** Mounts a card with a finished scan, so the summary button is enabled. */
  async function mountScannedCard(summaryReply: () => Promise<unknown>) {
    document.body.innerHTML = "";
    const runtime = {
      async sendMessage(message: unknown) {
        if ((message as { type: string }).type === "panel:requestSummary") return summaryReply();
        if ((message as { type: string }).type === "panel:nextJoke") return { ok: true, data: null };
        return {
          ok: true,
          data: {
            blocks: [
              {
                blockId: "b1",
                concepts: [{ word: "x", conceptId: 1, label: "X", definition: "", state: "new", candidates: [] }],
              },
            ],
          },
        };
      },
    };
    const ui = await mountFloatingUi(document, memoryArea(), runtime);
    ui.pin.collapse();
    Array.from(ui.pin.element.querySelectorAll<HTMLButtonElement>(".pinbtn"))
      .find((button) => !button.closest(".pinwrap"))
      ?.click();
    document.querySelector<HTMLButtonElement>(".card-main .scan")?.click();
    await vi.waitFor(() => expect(document.querySelector(".card-scan .status.done")).not.toBeNull());
    document.querySelector<HTMLButtonElement>(".card-scan .back")?.click();
    return ui;
  }

  it("a summary reply that arrives after the card was closed is dropped", async () => {
    let release: () => void = () => undefined;
    const summaryGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const ui = await mountScannedCard(async () => {
      await summaryGate;
      return { ok: true, data: { status: "done", summary: "Late summary." } };
    });
    try {
      document.querySelector<HTMLButtonElement>(".card-main .summary")?.click();
      await vi.waitFor(() => expect(document.querySelector(".card-summary .loading")).not.toBeNull());
      ui.cards.close();
      expect(document.querySelector(".card-host .card")).toBeNull();
      release();
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(document.querySelector(".card-summary")).toBeNull();
    } finally {
      ui.dispose();
    }
  });

  it("a queued summary job shows the queued text, not the loading text", async () => {
    const ui = await mountScannedCard(async () => ({ ok: true, data: { id: 3 } }));
    try {
      document.querySelector<HTMLButtonElement>(".card-main .summary")?.click();
      await vi.waitFor(() => expect(document.querySelector(".card-summary .queued")).not.toBeNull());
      expect(document.querySelector(".card-summary .loading")).toBeNull();
    } finally {
      ui.dispose();
    }
  });

  it("open panel and quiz message the background, focus is undoable from the pin, a scan shows a joke", async () => {
    document.body.innerHTML = "";
    const sent: unknown[] = [];
    const runtime = {
      async sendMessage(message: unknown) {
        sent.push(message);
        const type = (message as { type: string }).type;
        if (type === "panel:nextJoke") return { ok: true, data: { text: "A joke." } };
        // The scan reply waits until the test has seen the joke cloud.
        await scanGate;
        return { ok: true, data: { blocks: [] } };
      },
    };
    let openGate: () => void = () => undefined;
    const scanGate = new Promise<void>((resolve) => {
      openGate = resolve;
    });
    const ui = await mountFloatingUi(document, memoryArea(), runtime);
    try {
      ui.pin.collapse();
      Array.from(ui.pin.element.querySelectorAll<HTMLButtonElement>(".pinbtn"))
        .find((button) => !button.closest(".pinwrap"))
        ?.click();
      document.querySelector<HTMLButtonElement>(".card-main .open-panel")?.click();
      document.querySelector<HTMLButtonElement>(".card-main .quiz")?.click();
      expect(sent.filter((m) => (m as { type: string }).type === "card:openPanel")).toHaveLength(2);

      document.querySelector<HTMLButtonElement>(".card-main .scan")?.click();
      await vi.waitFor(() => expect(sent).toContainEqual({ type: "panel:nextJoke" }));
      await vi.waitFor(() => expect(document.querySelector(".joke-cloud .joke")?.textContent).toBe("A joke."));
      openGate();
      // The scan result replaces the card and the cloud.
      await vi.waitFor(() => expect(document.querySelector(".joke-cloud")).toBeNull());

      // Focus on is undoable from the pin mini-menu; nothing to undo before.
      document.querySelector<HTMLButtonElement>(".card-scan .back")?.click();
      const undo = () => ui.pin.element.querySelector<HTMLButtonElement>(".menu-undo");
      expect(undo()?.disabled).toBe(true);
      document.querySelector<HTMLButtonElement>(".card-main .focus")?.click();
      document.querySelector<HTMLButtonElement>(".focus-confirm .turn-on")?.click();
      expect(document.querySelector(".card-main .focus.on")).not.toBeNull();
      ui.pin.element.querySelector<HTMLButtonElement>(".pinwrap .pinbtn")?.click();
      expect(undo()?.disabled).toBe(false);
      undo()?.click();
      expect(document.querySelector(".card-main .focus.on")).toBeNull();
    } finally {
      ui.dispose();
    }
  });

  it("a joke that arrives after the card was closed mid-scan is dropped", async () => {
    document.body.innerHTML = "";
    let release: () => void = () => undefined;
    const jokeGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const runtime = {
      async sendMessage(message: unknown) {
        if ((message as { type: string }).type === "panel:nextJoke") {
          await jokeGate;
          return { ok: true, data: { text: "Late joke." } };
        }
        return new Promise(() => undefined);
      },
    };
    const ui = await mountFloatingUi(document, memoryArea(), runtime);
    try {
      ui.cards.open();
      document.querySelector<HTMLButtonElement>(".card-main .scan")?.click();
      ui.cards.close();
      release();
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(document.querySelector(".joke-cloud")).toBeNull();
    } finally {
      ui.dispose();
    }
  });

  it("a joke that arrives after the user moved on to Summary mid-scan is dropped", async () => {
    document.body.innerHTML = "";
    let release: () => void = () => undefined;
    const jokeGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const runtime = {
      async sendMessage(message: unknown) {
        if ((message as { type: string }).type === "panel:nextJoke") {
          await jokeGate;
          return { ok: true, data: { text: "Late joke." } };
        }
        return new Promise(() => undefined);
      },
    };
    const ui = await mountFloatingUi(document, memoryArea(), runtime);
    try {
      ui.cards.open();
      document.querySelector<HTMLButtonElement>(".card-main .scan")?.click();
      ui.cards.open();
      document.querySelector<HTMLButtonElement>(".card-main .summary")?.click();
      release();
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(document.querySelector(".card-summary")).not.toBeNull();
      expect(document.querySelector(".joke-cloud")).toBeNull();
    } finally {
      ui.dispose();
    }
  });

  it("asks for no joke while focus mode is on", async () => {
    document.body.innerHTML = "";
    const sent: unknown[] = [];
    const runtime = {
      async sendMessage(message: unknown) {
        sent.push(message);
        return { ok: true, data: { blocks: [] } };
      },
    };
    const ui = await mountFloatingUi(document, memoryArea(), runtime);
    try {
      ui.cards.open();
      document.querySelector<HTMLButtonElement>(".card-main .focus")?.click();
      document.querySelector<HTMLButtonElement>(".focus-confirm .turn-on")?.click();
      document.querySelector<HTMLButtonElement>(".card-main .scan")?.click();
      await vi.waitFor(() => expect(sent).toContainEqual({ type: "panel:scanConcepts" }));
      expect(sent).not.toContainEqual({ type: "panel:nextJoke" });
    } finally {
      ui.dispose();
    }
  });

  it("removes what it added and rejects when the pin position cannot be read", async () => {
    document.body.innerHTML = "";
    const styleCount = document.head.querySelectorAll("style").length;
    const load = vi.spyOn(PinPositionStore.prototype, "load").mockRejectedValue(new Error("storage down"));
    try {
      await expect(
        mountFloatingUi(document, memoryArea(), { async sendMessage() { return undefined; } } as never),
      ).rejects.toThrow("storage down");
    } finally {
      load.mockRestore();
    }
    expect(document.head.querySelectorAll("style")).toHaveLength(styleCount);
    expect(document.body.children).toHaveLength(0);
  });
});

describe("screen registry", () => {
  it("has an entry for every panel tab and settings page id in the inventory", () => {
    const pageIds = INVENTORY.filter((s) => s.surface === "panel tab" || s.surface === "settings page").map(
      (s) => s.id,
    );
    expect(pageIds).toHaveLength(30);
    for (const id of pageIds) {
      expect(typeof SCREENS[id as keyof typeof SCREENS], `no registry entry for ${id}`).toBe("function");
    }
  });
});
