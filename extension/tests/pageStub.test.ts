import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { installStub, type StubWindow } from "../src/pageStub";

interface Sent {
  channel: string;
  dir: string;
  id: number;
  op: string;
  path: string;
  body?: Record<string, unknown>;
}
interface Snap {
  exists: boolean;
  data(): unknown;
}
interface DocRef {
  get(): Promise<Snap>;
  set(body: unknown): Promise<unknown>;
  onSnapshot(next: (snap: Snap) => void): () => void;
}
interface Claude {
  use(name: string): { id?: () => Promise<string>; doc?: (path: string) => DocRef } | null;
}

const CHANNEL = "kata-test";
const MAIN = "data/users/kata/progress-course-1";

// Loads the stub from its source text, as the page would: proves it needs no module scope.
const install = new Function("return " + installStub.toString())() as typeof installStub;

function fakeWindow() {
  const listeners: Array<(event: MessageEvent) => void> = [];
  const sent: Sent[] = [];
  const win: StubWindow = {
    location: { origin: "https://course.test" },
    postMessage: (message: unknown) => {
      sent.push(message as Sent);
    },
    addEventListener: (_type, listener) => {
      listeners.push(listener);
    },
  };
  function raw(data: unknown, source: unknown = win) {
    const event = { source, data } as unknown as MessageEvent;
    for (const listener of listeners) listener(event);
  }
  function answer(req: Sent, res: { ok: boolean; body?: unknown; error?: string }, source: unknown = win) {
    raw({ channel: req.channel, dir: "res", id: req.id, ...res }, source);
  }
  return { win, sent, answer, raw };
}

function setup() {
  const fake = fakeWindow();
  install(fake.win, CHANNEL);
  const claude = fake.win.claude as Claude;
  const doc = (path: string): DocRef => {
    const db = claude.use("db");
    if (!db || !db.doc) throw new Error("no db");
    return db.doc(path);
  };
  return { ...fake, claude, doc };
}

const byteLength = (text: string): number => new TextEncoder().encode(text).length;

// Copy of dojo's parts.js split: items sorted by id, 120000 byte budget, main keeps no items and a `parts` count.
function dojoSplit(body: { items: Record<string, unknown> } & Record<string, unknown>) {
  const BUDGET = 120000;
  const parts: Array<{ items: Record<string, unknown> }> = [];
  let current: Record<string, unknown> = {};
  let size = 0;
  for (const id of Object.keys(body.items).sort()) {
    const entry = byteLength(JSON.stringify({ [id]: body.items[id] }));
    if (size > 0 && size + entry > BUDGET) {
      parts.push({ items: current });
      current = {};
      size = 0;
    }
    current[id] = body.items[id];
    size += entry;
  }
  if (size > 0) parts.push({ items: current });
  return { main: { ...body, items: {}, parts: parts.length }, parts };
}

function bigDoc(): { items: Record<string, unknown>; title: string } {
  const items: Record<string, unknown> = {};
  for (let i = 0; i < 1400; i++) {
    items[`block-${String(i).padStart(5, "0")}`] = { text: `lesson text ${i} é ${"x".repeat(200)}`, score: i % 7 };
  }
  return { title: "course one", items };
}

describe("installStub: window.claude surface", () => {
  it("use('user').id() resolves 'kata'; unknown use names resolve null", async () => {
    const { claude } = setup();
    const user = claude.use("user");
    expect(user && user.id ? await user.id() : undefined).toBe("kata");
    expect(claude.use("nope")).toBeNull();
  });

  it("get on a part path resolves exists false without asking the bridge", async () => {
    const { doc, sent } = setup();
    const snap = await doc(`${MAIN}.part1`).get();
    expect(snap.exists).toBe(false);
    expect(sent).toHaveLength(0);
  });

  it("get on the main path asks the bridge for the stored whole doc", async () => {
    const { doc, sent, answer } = setup();
    const pending = doc(MAIN).get();
    expect(sent[0]).toMatchObject({ channel: CHANNEL, dir: "req", op: "get", path: MAIN });
    answer(sent[0], { ok: true, body: { title: "stored" } });
    const snap = await pending;
    expect(snap.exists).toBe(true);
    expect(snap.data()).toEqual({ title: "stored" });
  });

  it("a bridge get with no document resolves exists false", async () => {
    const { doc, sent, answer } = setup();
    const pending = doc(MAIN).get();
    answer(sent[0], { ok: true, body: null });
    expect((await pending).exists).toBe(false);
  });

  it("set sends one save op and resolves on the bridge reply", async () => {
    const { doc, sent, answer } = setup();
    const body = { title: "plain", items: { a: 1 } };
    const pending = doc(MAIN).set(body);
    expect(sent[0]).toMatchObject({ op: "set", path: MAIN, body });
    answer(sent[0], { ok: true });
    await expect(pending).resolves.toBeUndefined();
  });

  it("a bridge error rejects the set with the short message", async () => {
    const { doc, sent, answer } = setup();
    const pending = doc(MAIN).set({ title: "x" });
    answer(sent[0], { ok: false, error: "e".repeat(300) });
    await expect(pending).rejects.toThrow(new Error("e".repeat(200)));
  });

  it("replies from another source, channel or direction are ignored", async () => {
    const { doc, sent, answer, raw, win } = setup();
    const pending = doc(MAIN).set({ title: "x" });
    answer(sent[0], { ok: true }, { other: true });
    raw({ channel: "other", dir: "res", id: sent[0].id, ok: true });
    raw({ channel: CHANNEL, dir: "req", id: sent[0].id, ok: true });
    let settled = false;
    void pending.then(() => (settled = true));
    await new Promise((r) => setTimeout(r, 0));
    expect(settled).toBe(false);
    answer(sent[0], { ok: true }, win);
    await expect(pending).resolves.toBeUndefined();
  });

  it("after a local set, get returns what the page last wrote", async () => {
    const { doc, sent, answer } = setup();
    const pending = doc(MAIN).set({ title: "local", items: {} });
    answer(sent[0], { ok: true });
    await pending;
    const snap = await doc(MAIN).get();
    expect(snap.data()).toEqual({ title: "local", items: {} });
    expect(sent.filter((r) => r.op === "get")).toHaveLength(0);
  });

  it("onSnapshot fires once with the current doc and again after each local set", async () => {
    const { doc, sent, answer } = setup();
    const seen: unknown[] = [];
    doc(MAIN).onSnapshot((snap) => seen.push(snap.data()));
    answer(sent[0], { ok: true, body: { title: "stored" } });
    await Promise.resolve();
    await Promise.resolve();
    expect(seen).toEqual([{ title: "stored" }]);
    const pending = doc(MAIN).set({ title: "next", items: {} });
    expect(seen).toEqual([{ title: "stored" }, { title: "next", items: {} }]);
    answer(sent[1], { ok: true });
    await pending;
    expect(seen).toHaveLength(2);
  });

  it("get and onSnapshot started before a local set return the page's write, not the stored doc", async () => {
    const { doc, sent, answer } = setup();
    const seen: unknown[] = [];
    doc(MAIN).onSnapshot((snap) => seen.push(snap.data()));
    const got = doc(MAIN).get();
    const pending = doc(MAIN).set({ title: "new", items: {} });
    answer(sent[2], { ok: true });
    await pending;
    answer(sent[0], { ok: true, body: { title: "stored" } });
    answer(sent[1], { ok: true, body: { title: "stored" } });
    expect((await got).data()).toEqual({ title: "new", items: {} });
    expect(seen[seen.length - 1]).toEqual({ title: "new", items: {} });
  });
});

describe("installStub: split documents", () => {
  it("a 350 KB doc split by the dojo logic reaches the bridge as one identical save (parts first)", async () => {
    const { doc, sent, answer } = setup();
    const body = bigDoc();
    const { main, parts } = dojoSplit(body);
    expect(parts.length).toBeGreaterThan(1);
    expect(byteLength(JSON.stringify(body))).toBeGreaterThan(340000);
    for (let k = 1; k <= parts.length; k++) {
      await expect(doc(`${MAIN}.part${k}`).set(parts[k - 1])).resolves.toBeUndefined();
    }
    expect(sent).toHaveLength(0);
    const pending = doc(MAIN).set(main);
    const saves = sent.filter((r) => r.op === "set");
    expect(saves).toHaveLength(1);
    expect(saves[0].path).toBe(MAIN);
    expect(saves[0].body).toEqual(body);
    answer(saves[0], { ok: true });
    await expect(pending).resolves.toBeUndefined();
  });

  it("main arriving first resolves locally; the last part's promise carries the save result", async () => {
    const { doc, sent, answer } = setup();
    const body = bigDoc();
    const { main, parts } = dojoSplit(body);
    await expect(doc(MAIN).set(main)).resolves.toBeUndefined();
    expect(sent).toHaveLength(0);
    for (let k = 1; k < parts.length; k++) {
      await doc(`${MAIN}.part${k}`).set(parts[k - 1]);
    }
    expect(sent).toHaveLength(0);
    const last = doc(`${MAIN}.part${parts.length}`).set(parts[parts.length - 1]);
    const saves = sent.filter((r) => r.op === "set");
    expect(saves).toHaveLength(1);
    expect(saves[0].body).toEqual(body);
    answer(saves[0], { ok: false, error: "conflict" });
    await expect(last).rejects.toThrow("conflict");
  });

  it("after a complete save, get returns the whole reassembled doc without a bridge get", async () => {
    const { doc, sent, answer } = setup();
    const body = bigDoc();
    const { main, parts } = dojoSplit(body);
    for (let k = 1; k <= parts.length; k++) void doc(`${MAIN}.part${k}`).set(parts[k - 1]);
    const pending = doc(MAIN).set(main);
    answer(sent[sent.length - 1], { ok: true });
    await pending;
    const snap = await doc(MAIN).get();
    expect(snap.data()).toEqual(body);
    expect(sent.filter((r) => r.op === "get")).toHaveLength(0);
  });

  it("a rejected save restores the previous local doc and keeps the buffered parts for a retry", async () => {
    const { doc, sent, answer } = setup();
    const first = doc(MAIN).set({ title: "a", items: {} });
    answer(sent[0], { ok: true });
    await first;
    await doc(MAIN + ".part1").set({ items: { x: 1 } });
    const failed = doc(MAIN).set({ title: "b", items: {}, parts: 1 });
    answer(sent[1], { ok: false, error: "disk full" });
    await expect(failed).rejects.toThrow("disk full");
    expect((await doc(MAIN).get()).data()).toEqual({ title: "a", items: {} });
    const retry = doc(MAIN).set({ title: "b", items: {}, parts: 1 });
    expect(sent[2]).toMatchObject({ op: "set", path: MAIN, body: { title: "b", items: { x: 1 } } });
    answer(sent[2], { ok: true });
    await expect(retry).resolves.toBeUndefined();
  });

  it("a part rewritten while a save is in flight is not lost; the final save equals the final body", async () => {
    const { doc, sent, answer } = setup();
    const part = (tag: string) => ({ items: { [tag]: 1 } });
    await doc(`${MAIN}.part1`).set(part("a1"));
    await doc(`${MAIN}.part2`).set(part("a2"));
    const s1 = doc(MAIN).set({ title: "A", items: {}, parts: 2 });
    const first = sent.filter((r) => r.op === "set")[0];
    void doc(`${MAIN}.part1`).set(part("b1")).catch(() => undefined);
    answer(first, { ok: true });
    await s1;
    await doc(`${MAIN}.part2`).set(part("b2"));
    const last = doc(MAIN).set({ title: "B", items: {}, parts: 2 });
    const saves = sent.filter((r) => r.op === "set");
    expect(saves[saves.length - 1].body).toEqual({ title: "B", items: { b1: 1, b2: 1 } });
    for (const req of saves.slice(1)) answer(req, { ok: true });
    await expect(last).resolves.toBeUndefined();
  });

  it("a plain main set after a waiting main set is not overwritten when stale parts arrive", async () => {
    const { doc, sent } = setup();
    await doc(MAIN).set({ parts: 2 });
    expect(sent).toHaveLength(0);
    void doc(MAIN).set({ title: "new", items: {} });
    const plain = sent.filter((r) => r.op === "set");
    expect(plain).toHaveLength(1);
    expect(plain[0].body).toEqual({ title: "new", items: {} });
    void doc(`${MAIN}.part1`).set({ items: { a: 1 } });
    void doc(`${MAIN}.part2`).set({ items: { b: 2 } });
    const saves = sent.filter((r) => r.op === "set");
    expect(saves).toHaveLength(1);
    expect(saves[0].body).toEqual({ title: "new", items: {} });
  });

  it("a parts count outside 1..64 or a bad part number rejects", async () => {
    const { doc } = setup();
    await expect(doc(MAIN).set({ items: {}, parts: 0 })).rejects.toThrow("bad parts count");
    await expect(doc(MAIN).set({ items: {}, parts: 65 })).rejects.toThrow("bad parts count");
    await expect(doc(MAIN).set({ items: {}, parts: 1.5 })).rejects.toThrow("bad parts count");
    await expect(doc(`${MAIN}.part0`).set({ items: {} })).rejects.toThrow("bad part path");
  });
});

describe("pageStub source", () => {
  it("contains no token string and no imports", () => {
    const source = readFileSync(join(process.cwd(), "src", "pageStub.ts"), "utf8");
    expect(source).not.toMatch(/token/i);
    expect(source).not.toMatch(/^import /m);
  });
});
