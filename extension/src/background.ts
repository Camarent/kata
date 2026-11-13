import type { ContentMessage, RuntimeLike, ScanResponse } from "./content";
import { DEFAULT_BASE_URL, MAX_WAIT_MS, POLL_MS, REQUEST_TIMEOUT_MS } from "./config";
import { CoreAuthError, CoreClient } from "./coreClient";
import { OfflineQueue, type FlushResult, type MarkOutcome } from "./offlineQueue";
import { runScan, type ScanResult } from "./scanSession";
import type { SignInInput } from "./sidepanel";
import { TokenStore, type StorageArea } from "./tokenStore";
import type { Session } from "./types";

/** The part of `chrome` the background script uses; tests pass a fake with these members. */
export interface ChromeLike {
  action: {
    onClicked: { addListener(listener: (tab: { windowId?: number }) => void): void };
  };
  sidePanel: { open(options: { windowId: number }): Promise<void> };
  tabs: {
    query(query: { active: boolean; currentWindow: boolean }): Promise<{ id?: number }[]>;
    sendMessage(tabId: number, message: ContentMessage): Promise<unknown>;
  };
  runtime: RuntimeLike;
}

/** Messages the side panel page sends to the background script. */
export type PanelMessage =
  | { type: "panel:signIn"; input: SignInInput }
  | { type: "panel:scan" }
  | { type: "panel:known"; topicId: number };

/** Reply to a panel message: the result, or the error text. */
export type PanelReply = { ok: true; data?: unknown } | { ok: false; error: string };

/** Business logic behind the side panel; each call talks to the core. */
export interface Backend {
  signIn(input: SignInInput): Promise<void>;
  scan(): Promise<ScanResult[]>;
  markKnown(topicId: number): Promise<MarkOutcome>;
  flush(): Promise<FlushResult | null>;
}

/** Builds the backend over the chrome tabs API and the extension storage area. */
export function createBackend(api: ChromeLike, area: StorageArea, fetchImpl?: typeof fetch): Backend {
  const tokens = new TokenStore(area);
  const clientFor = (session: Session | null): CoreClient =>
    new CoreClient({
      baseUrl: session?.baseUrl ?? DEFAULT_BASE_URL,
      token: session?.token,
      timeoutMs: REQUEST_TIMEOUT_MS,
      fetchImpl,
    });
  const requireSession = async (): Promise<Session> => {
    const session = await tokens.loadSession();
    if (!session) throw new CoreAuthError("not signed in");
    return session;
  };

  return {
    async signIn(input) {
      const client = clientFor(null);
      const token = await client.enrol(input.code, input.deviceLabel);
      await tokens.saveSession({ baseUrl: DEFAULT_BASE_URL, token });
    },

    async scan() {
      const session = await requireSession();
      const [tab] = await api.tabs.query({ active: true, currentWindow: true });
      if (tab?.id === undefined) throw new Error("no active tab");
      const page = (await api.tabs.sendMessage(tab.id, { type: "scan" })) as ScanResponse;
      if (!page?.blocks) throw new Error("page gave no blocks");
      return runScan(clientFor(session), page.blocks, { pollMs: POLL_MS, maxWaitMs: MAX_WAIT_MS });
    },

    async markKnown(topicId) {
      const session = await requireSession();
      return new OfflineQueue(area, clientFor(session)).markKnown(topicId);
    },

    async flush() {
      const session = await tokens.loadSession();
      if (!session) return null;
      return new OfflineQueue(area, clientFor(session)).flush();
    },
  };
}

/** Routes one panel message to the backend and returns its reply. */
async function handlePanelMessage(backend: Backend, message: PanelMessage): Promise<PanelReply> {
  switch (message.type) {
    case "panel:signIn":
      await backend.signIn(message.input);
      return { ok: true };
    case "panel:scan":
      return { ok: true, data: await backend.scan() };
    case "panel:known":
      return { ok: true, data: await backend.markKnown(message.topicId) };
  }
}

/** True when `message` has one of the panel message shapes. */
function isPanelMessage(message: unknown): message is PanelMessage {
  if (typeof message !== "object" || message === null) return false;
  const type = (message as { type?: unknown }).type;
  return type === "panel:signIn" || type === "panel:scan" || type === "panel:known";
}

/**
 * Registers the background listeners: the toolbar button opens the side panel and
 * flushes the offline mark queue; panel messages go to the backend.
 */
export function wireBackground(api: ChromeLike, backend: Backend): void {
  api.action.onClicked.addListener((tab) => {
    if (tab.windowId === undefined) return;
    api.sidePanel.open({ windowId: tab.windowId }).catch((err: unknown) => console.error(err));
    // A failed flush stays queued; the next panel open retries it.
    backend.flush().catch(() => undefined);
  });

  api.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!isPanelMessage(message)) return false;
    handlePanelMessage(backend, message).then(
      (reply) => sendResponse(reply),
      (err: unknown) => sendResponse({ ok: false, error: err instanceof Error ? err.message : String(err) }),
    );
    return true;
  });
}

// Service worker entry: runs only where the extension runtime exists (not under tests).
if (typeof chrome !== "undefined" && chrome.action) {
  wireBackground(chrome, createBackend(chrome, chrome.storage.local));
}
