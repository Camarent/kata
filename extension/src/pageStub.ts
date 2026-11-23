/** The slice of `window` the stub uses. */
export interface StubWindow {
  location: { origin: string };
  postMessage(message: unknown, targetOrigin: string): void;
  addEventListener(type: "message", listener: (event: MessageEvent) => void): void;
  claude?: unknown;
}

/**
 * Installs `window.claude` on `win`, relaying storage calls to the extension bridge over `window.postMessage`.
 *
 * Self-contained on purpose: its toString() is injected as inline script text, so the body may use only
 * its parameters, its own locals and browser globals. No imports, no references to module scope.
 *
 * Split documents: a main path whose body has `parts: k` (1..64) is stored only once parts `<main>.part1`
 * .. `<main>.part<k>` are present. The parts' `items` are merged into the main body's `items`, the `parts`
 * marker is dropped, and one save with the whole document goes to the bridge.
 */
export function installStub(win: StubWindow, channelId: string): void {
  const MAX_PARTS = 64;
  const ERROR_LIMIT = 200;
  const PART_RE = /^(.*)\.part(\d+)$/;

  type Doc = { exists: boolean; body?: unknown };
  type Listener = (snap: { exists: boolean; data: () => unknown }) => void;

  let nextId = 1;
  const pending = new Map<number, { resolve: (value: unknown) => void; reject: (error: Error) => void }>();
  // Logical document per path, as the page last left it (reassembled when its parts are complete).
  const docs: Record<string, Doc> = {};
  const listeners: Record<string, Listener[]> = {};
  // Bumped on every local change of a path, so a bridge get started earlier can tell it is stale.
  const versions: Record<string, number> = {};
  // Parts received per main path, keyed by part number.
  const partsByMain: Record<string, Record<number, Record<string, unknown>>> = {};
  // Main documents whose parts are not all present yet.
  const waiting: Record<string, { body: Record<string, unknown>; count: number }> = {};

  function send(op: string, path: string, body?: unknown): Promise<unknown> {
    const id = nextId++;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      win.postMessage({ channel: channelId, dir: "req", id, op, path, body }, win.location.origin);
    });
  }

  win.addEventListener("message", (event) => {
    const data = event.data as { channel?: unknown; dir?: unknown; id?: unknown; ok?: unknown; body?: unknown; error?: unknown } | null;
    if (event.source !== win || !data || data.channel !== channelId || data.dir !== "res") return;
    const slot = typeof data.id === "number" ? pending.get(data.id) : undefined;
    if (!slot) return;
    pending.delete(data.id as number);
    if (data.ok === true) slot.resolve(data.body);
    else slot.reject(new Error(String(data.error ?? "bridge error").slice(0, ERROR_LIMIT)));
  });

  function publish(path: string): void {
    const doc = docs[path] || { exists: false };
    const snap = { exists: doc.exists, data: () => doc.body };
    for (const next of listeners[path] || []) next(snap);
  }

  function bump(path: string): void {
    versions[path] = (versions[path] || 0) + 1;
  }

  // Current logical document: what the page wrote, else the bridge's stored whole document.
  function current(path: string): Promise<Doc> {
    if (PART_RE.test(path)) return Promise.resolve({ exists: false });
    const local = docs[path];
    if (local) return Promise.resolve(local);
    const version = versions[path] || 0;
    return send("get", path).then((body) => {
      // The page wrote this path while the get was in flight: its own copy is newer than the reply.
      if ((versions[path] || 0) !== version && docs[path]) return docs[path];
      return body === null || body === undefined ? { exists: false } : { exists: true, body };
    });
  }

  // Saves a whole document: the local copy changes at once, the bridge gets one save op.
  // A rejected save puts the previous local copy back and publishes it.
  function save(path: string, body: Record<string, unknown>): Promise<unknown> {
    const prev = docs[path];
    const doc: Doc = { exists: true, body };
    docs[path] = doc;
    bump(path);
    publish(path);
    return send("set", path, body).catch((error: Error) => {
      if (docs[path] === doc) {
        if (prev) docs[path] = prev;
        else delete docs[path];
        bump(path);
        publish(path);
      }
      throw error;
    });
  }

  function complete(bag: Record<number, unknown>, count: number): boolean {
    for (let i = 1; i <= count; i++) {
      if (!(i in bag)) return false;
    }
    return true;
  }

  // Merges the main body with parts 1..count into one document and saves it.
  function flush(main: string, body: Record<string, unknown>, count: number): Promise<unknown> {
    const bag = partsByMain[main] || {};
    const merged: Record<string, unknown> = {};
    for (const key of Object.keys(body)) {
      if (key !== "parts") merged[key] = body[key];
    }
    const items: Record<string, unknown> = Object.assign({}, body.items as Record<string, unknown> | undefined);
    const used: Array<Record<string, unknown>> = [];
    for (let i = 1; i <= count; i++) {
      used[i] = bag[i];
      Object.assign(items, (bag[i] as { items?: Record<string, unknown> }).items);
    }
    merged.items = items;
    // Parts and the waiting main stay until the save succeeds, so a rejected save can be retried.
    return save(main, merged).then((result) => {
      // Only parts this save used: a part the page rewrote meanwhile belongs to a newer save.
      for (let i = 1; i <= count; i++) {
        if (bag[i] === used[i]) delete bag[i];
      }
      if (waiting[main] && waiting[main].body === body) delete waiting[main];
      return result;
    });
  }

  function setPart(main: string, k: number, body: unknown): Promise<unknown> {
    if (!Number.isInteger(k) || k < 1 || k > MAX_PARTS) return Promise.reject(new Error("bad part path"));
    const bag = partsByMain[main] || (partsByMain[main] = {});
    bag[k] = (body || {}) as Record<string, unknown>;
    const wait = waiting[main];
    if (wait && complete(bag, wait.count)) return flush(main, wait.body, wait.count);
    return Promise.resolve(undefined);
  }

  function setMain(path: string, body: Record<string, unknown>, count: number): Promise<unknown> {
    waiting[path] = { body, count };
    if (!complete(partsByMain[path] || {}, count)) {
      docs[path] = { exists: true, body };
      bump(path);
      publish(path);
      return Promise.resolve(undefined);
    }
    return flush(path, body, count);
  }

  function setDoc(path: string, body: unknown): Promise<unknown> {
    const part = PART_RE.exec(path);
    if (part) return setPart(part[1], Number(part[2]), body);
    const doc = (body || {}) as Record<string, unknown>;
    // A plain set supersedes a main set still waiting for its parts: that set must not save later.
    if (doc.parts === undefined) {
      delete waiting[path];
      return save(path, doc);
    }
    const count = doc.parts;
    if (typeof count !== "number" || !Number.isInteger(count) || count < 1 || count > MAX_PARTS) {
      return Promise.reject(new Error("bad parts count"));
    }
    return setMain(path, doc, count);
  }

  function onSnapshot(path: string, next: Listener): () => void {
    (listeners[path] || (listeners[path] = [])).push(next);
    current(path).then((doc) => next({ exists: doc.exists, data: () => doc.body }));
    return () => {
      const list = listeners[path] || [];
      const at = list.indexOf(next);
      if (at >= 0) list.splice(at, 1);
    };
  }

  const db = {
    doc(path: string) {
      return {
        get: () => current(path).then((doc) => ({ exists: doc.exists, data: () => doc.body })),
        set: (body: unknown) => setDoc(path, body),
        onSnapshot: (next: Listener) => onSnapshot(path, next),
      };
    },
  };
  const user = { id: () => Promise.resolve("kata") };

  win.claude = {
    use(name: string) {
      if (name === "db") return db;
      if (name === "user") return user;
      return null;
    },
  };
}
