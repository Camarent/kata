import { CORE_ORIGIN } from "./config";
import { installStub, type StubWindow } from "./pageStub";

/** The part of `chrome.runtime` the bridge uses; tests pass a fake with this member. */
export interface BridgeRuntime {
  sendMessage(message: unknown): Promise<unknown>;
}

/** Messages the bridge sends to the background script. */
export type BridgeMessage =
  | { type: "bridge:load"; courseId: number }
  | { type: "bridge:save"; courseId: number; doc: unknown };

/** Stub ops the bridge serves, mapped to background message types (the stub sends `get` and `set`). */
const OP_TYPES = new Map<unknown, BridgeMessage["type"]>([
  ["get", "bridge:load"],
  ["set", "bridge:save"],
]);

/** Stub path of a course progress document: `progress-<id>`, optionally behind a folder prefix. */
const COURSE_PATH = /(?:^|\/)progress-(\d+)$/;

/** Longest error text sent to the page. */
const ERROR_LIMIT = 200;

/** A fresh random channel id: 16 random bytes in hex. */
export function newChannel(cryptoImpl: Crypto): string {
  const bytes = cryptoImpl.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/**
 * Puts the page stub into the page as inline script text. The browser runs it when inserted;
 * the element is removed again at once. Page CSP must allow inline scripts.
 */
export function injectStub(doc: Document, channel: string): void {
  const script = doc.createElement("script");
  script.textContent = "(" + installStub.toString() + ")(window," + JSON.stringify(channel) + ")";
  doc.documentElement.appendChild(script);
  script.remove();
}

/** Course id of a stub path `progress-<id>`, or undefined for any other path. */
function courseIdOf(path: unknown): number | undefined {
  if (typeof path !== "string") return undefined;
  const match = COURSE_PATH.exec(path);
  return match ? Number(match[1]) : undefined;
}

/** Message text for a failed send, short and safe to show the page. */
function errorText(err: unknown): string {
  return String(err instanceof Error ? err.message : err).slice(0, ERROR_LIMIT);
}

/**
 * Answers the stub's requests on `win` through `runtime`. Only requests on `channel`, from `win`
 * itself and from its own origin, are answered; anything else is ignored. Each reply goes back
 * as `{channel, dir: "res", id, ok, body}` or `{channel, dir: "res", id, ok: false, error}`.
 */
export function startBridge(win: StubWindow, runtime: BridgeRuntime, channel: string): void {
  const reply = (id: number, result: { ok: true; body: unknown } | { ok: false; error: string }) => {
    win.postMessage({ channel, dir: "res", id, ...result }, win.location.origin);
  };
  win.addEventListener("message", (event) => {
    if (event.source !== win || event.origin !== win.location.origin) return;
    const data = event.data as Record<string, unknown> | null;
    if (!data || typeof data !== "object" || data.channel !== channel || data.dir !== "req") return;
    if (typeof data.id !== "number") return;
    const id = data.id;
    const type = OP_TYPES.get(data.op);
    const courseId = courseIdOf(data.path);
    if (type === undefined || courseId === undefined) {
      reply(id, { ok: false, error: "bad request" });
      return;
    }
    const message: BridgeMessage =
      type === "bridge:save" ? { type, courseId, doc: data.body } : { type, courseId };
    runtime.sendMessage(message).then(
      (answer) => {
        const result = answer as { ok?: unknown; data?: unknown; error?: unknown } | undefined;
        if (result?.ok === true) reply(id, { ok: true, body: result.data });
        else reply(id, { ok: false, error: typeof result?.error === "string" ? result.error.slice(0, ERROR_LIMIT) : "bridge error" });
      },
      (err: unknown) => reply(id, { ok: false, error: errorText(err) }),
    );
  });
}

/**
 * Bridge entry on a course page: injects the stub with a fresh channel and starts answering it.
 * Does nothing unless the page is on the core origin.
 */
export function runBridge(win: StubWindow, doc: Document, runtime: BridgeRuntime, cryptoImpl: Crypto): void {
  if (win.location.origin !== CORE_ORIGIN) return;
  const channel = newChannel(cryptoImpl);
  startBridge(win, runtime, channel);
  injectStub(doc, channel);
}

// Bridge entry: runs only as the dynamically registered content script (not under tests).
if (typeof chrome !== "undefined" && chrome.runtime) {
  runBridge(
    window,
    document,
    { sendMessage: (message) => chrome.runtime.sendMessage(message) },
    crypto,
  );
}
