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
});
