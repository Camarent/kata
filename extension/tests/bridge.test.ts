import { describe, expect, it, vi } from "vitest";
import { createBackend, wireBackground, type ChromeLike } from "../src/background";
import { injectStub, newChannel, runBridge, startBridge, type BridgeRuntime } from "../src/bridge";
import { CORE_ORIGIN } from "../src/config";
import { installStub, type StubWindow } from "../src/pageStub";
import { TokenStore, type StorageArea } from "../src/tokenStore";

const TOKEN = "SECRET-TOKEN-never-to-the-page";
const PARTS = 8;

/** A window the stub and the bridge share. Posted messages reach its listeners on the next microtask. */
interface FakePage extends StubWindow {
  posted: unknown[];
  deliver(event: { source: unknown; origin: string; data: unknown }): void;
}

function fakePage(origin: string = CORE_ORIGIN): FakePage {
  const listeners: Array<(event: MessageEvent) => void> = [];
  const page: FakePage = {
    location: { origin },
    posted: [],
    postMessage(message, targetOrigin) {
      page.posted.push(message);
      if (targetOrigin !== origin) return;
      queueMicrotask(() => page.deliver({ source: page, origin, data: message }));
    },
    addEventListener(_type, listener) {
      listeners.push(listener);
    },
    deliver(event) {
      for (const listener of listeners) listener(event as unknown as MessageEvent);
    },
  };
  return page;
}

/** The inline script text `injectStub` puts into a page, captured with a stand-in document. */
function injectedText(channel: string): string {
  let text = "";
  const doc = {
    createElement: () => ({ textContent: "", remove() {} }),
    documentElement: {
      appendChild(node: { textContent: string }) {
        text = node.textContent;
      },
    },
  };
  injectStub(doc as unknown as Document, channel);
  return text;
}

/** Starts the bridge on `page` and runs the stub on it, the way the page gets the stub. */
function attach(page: FakePage, runtime: BridgeRuntime): string {
  const channel = newChannel(crypto);
  startBridge(page, runtime, channel);
  new Function("window", injectedText(channel))(page);
  return channel;
}

interface Db {
  doc(path: string): {
    get(): Promise<{ exists: boolean; data(): unknown }>;
    set(body: unknown): Promise<unknown>;
  };
}

function dbOf(page: StubWindow): Db {
  return (page.claude as { use(name: string): Db }).use("db");
}

/** In-memory storage area with the StorageArea shape. */
function memoryArea(): StorageArea {
  const items = new Map<string, unknown>();
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

function response(status: number, body: unknown): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as unknown as Response;
}

/** Fake core: one progress document with a revision; checks If-Match and records the token it sees. */
function fakeCore() {
  const state = {
    revision: 0,
    doc: null as unknown,
    puts: [] as string[],
    gets: 0,
    failAuth: false,
    auths: [] as string[],
  };
  const fetchImpl = (async (_url: string, init?: RequestInit) => {
    const headers = (init?.headers ?? {}) as Record<string, string>;
    state.auths.push(headers["Authorization"] ?? "");
    if (state.failAuth) return response(401, {});
    if (init?.method === "PUT") {
      const expected = Number(String(headers["If-Match"]).replace(/"/g, ""));
      if (expected !== state.revision) return response(412, { revision: state.revision, doc: state.doc });
      state.puts.push(String(init.body));
      state.doc = JSON.parse(String(init.body));
      state.revision += 1;
      return response(200, { revision: state.revision, evidence_written: 0 });
    }
    state.gets += 1;
    return response(200, { revision: state.revision, doc: state.doc });
  }) as typeof fetch;
  return { state, fetchImpl };
}

/** Fake `chrome`: captures the message listener; `runtime` sends through it like the content script does. */
function fakeApi(): { api: ChromeLike; runtime: BridgeRuntime } {
  let listener: ((message: unknown, sender: unknown, reply: (answer: unknown) => void) => boolean | void) | undefined;
  const api = {
    action: { onClicked: { addListener() {} } },
    tabs: { query: async () => [], sendMessage: async () => undefined },
    runtime: {
      onMessage: {
        addListener(next: typeof listener) {
          listener = next;
        },
      },
    },
  } as unknown as ChromeLike;
  const runtime: BridgeRuntime = {
    sendMessage: (message) => new Promise((resolve) => listener?.(message, {}, resolve)),
  };
  return { api, runtime };
}

/** A progress document split into PARTS parts of about 350 KB in all, and the whole document. */
function splitDoc() {
  const all: Record<string, unknown> = {};
  const parts: Record<string, unknown>[] = [];
  for (let p = 1; p <= PARTS; p++) {
    const items: Record<string, unknown> = {};
    for (let i = 0; i < 200; i++) items[`item-${p}-${i}`] = { ok: i, bad: p, note: "n".repeat(200) };
    Object.assign(all, items);
    parts.push({ items });
  }
  return { parts, expected: { items: all } };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

/** Wires the real background (progress service and message routing) over a fake core. */
async function wiredBackend() {
  const { api, runtime } = fakeApi();
  const core = fakeCore();
  const area = memoryArea();
  await new TokenStore(area).saveSession({ baseUrl: CORE_ORIGIN, token: TOKEN });
  wireBackground(api, createBackend(api, area, core.fetchImpl));
  return { runtime, core };
}

describe("injected stub", () => {
  it("the injected text is the stub source called with the window and the channel", () => {
    expect(injectedText("chan-1")).toBe(`(${installStub.toString()})(window,"chan-1")`);
  });

  it("injection on a real document leaves no script element behind", () => {
    const before = document.querySelectorAll("script").length;
    injectStub(document, newChannel(crypto));
    expect(document.querySelectorAll("script").length).toBe(before);
  });

  it("channel ids are 32 hex characters and differ between calls", () => {
    const first = newChannel(crypto);
    expect(first).toMatch(/^[0-9a-f]{32}$/);
    expect(newChannel(crypto)).not.toBe(first);
  });

  it("the bridge does nothing on a page outside the core origin", () => {
    const page = fakePage("https://evil.test");
    const createElement = vi.fn();
    const doc = { createElement, documentElement: { appendChild: vi.fn() } } as unknown as Document;
    const runtime = { sendMessage: vi.fn() };
    runBridge(page, doc, runtime, crypto);
    expect(createElement).not.toHaveBeenCalled();
    expect(runtime.sendMessage).not.toHaveBeenCalled();
    expect(page.posted).toEqual([]);
  });
});

describe("bridge end to end", () => {
  it("a 350 KB split doc written through the stub is stored whole once and read back deep-equal", async () => {
    const { runtime, core } = await wiredBackend();
    const { parts, expected } = splitDoc();

    const writer = fakePage();
    attach(writer, runtime);
    const writerDb = dbOf(writer);
    for (let k = 0; k < PARTS; k++) await writerDb.doc(`progress-1.part${k + 1}`).set(parts[k]);
    await writerDb.doc("progress-1").set({ parts: PARTS, items: {} });

    expect(core.state.puts).toHaveLength(1);
    expect(JSON.parse(core.state.puts[0])).toEqual(expected);

    // A fresh page holds no local copy, so its read goes through the bridge to the core.
    const reader = fakePage();
    attach(reader, runtime);
    const snap = await dbOf(reader).doc("progress-1").get();
    expect(snap.exists).toBe(true);
    expect(snap.data()).toEqual(expected);
  });

  it("messages with a wrong channel, a foreign source or a foreign origin are ignored", async () => {
    const { runtime, core } = await wiredBackend();
    const page = fakePage();
    const channel = attach(page, runtime);

    page.deliver({ source: page, origin: CORE_ORIGIN, data: { channel: "not-ours", dir: "req", id: 1, op: "get", path: "progress-1" } });
    page.deliver({ source: {}, origin: CORE_ORIGIN, data: { channel, dir: "req", id: 2, op: "get", path: "progress-1" } });
    page.deliver({ source: page, origin: "https://evil.test", data: { channel, dir: "req", id: 3, op: "get", path: "progress-1" } });
    await tick();

    expect(core.state.gets).toBe(0);
    expect(page.posted).toEqual([]);
  });

  it("error replies are short text and no message posted to the page ever holds the token", async () => {
    const { runtime, core } = await wiredBackend();
    const page = fakePage();
    attach(page, runtime);
    const db = dbOf(page);

    core.state.failAuth = true;
    await expect(db.doc("progress-1").get()).rejects.toThrow("sign in again");
    core.state.failAuth = false;
    await expect(db.doc("notes").get()).rejects.toThrow("bad request");
    await expect(db.doc("progress-0").get()).rejects.toThrow("bad course id");

    expect(JSON.stringify(page.posted)).not.toContain(TOKEN);
    expect(core.state.auths).toContain(`Bearer ${TOKEN}`);
  });

  it("a rejected runtime send answers the page with its short error", async () => {
    const page = fakePage();
    attach(page, { sendMessage: async () => Promise.reject(new Error("no background")) });
    await expect(dbOf(page).doc("progress-1").get()).rejects.toThrow("no background");
  });
});
