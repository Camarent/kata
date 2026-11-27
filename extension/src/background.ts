import type { BridgeMessage } from "./bridge";
import { openPanel } from "./browser";
import { type Backend, createBackend } from "./backgroundBackend";
import { wireBridgeRegistration } from "./bridgeRegister";
import { TokenStore } from "./tokenStore";
import { handlePanelMessage, isPanelMessage } from "./backgroundPanel";
import type { ProgressDoc } from "./coreClient";
import type { ChromeLike, PageMutatedMessage, PanelReply } from "./messages";
import type { ProgressBridge } from "./progressBridge";

export type { ChromeLike, PanelReply } from "./messages";
export type { Backend, ServerSignIn } from "./backgroundBackend";
export { createBackend } from "./backgroundBackend";

/**
 * Routes one content-bridge message to the progress service. Its reply is the document or
 * the short error text only; the session token never leaves this service.
 */
async function handleBridgeMessage(progress: ProgressBridge, message: BridgeMessage): Promise<PanelReply> {
  if (!Number.isInteger(message.courseId) || message.courseId < 1) throw new Error("bad course id");
  if (message.type === "bridge:load") return { ok: true, data: await progress.load(message.courseId) };
  if (typeof message.doc !== "object" || message.doc === null) throw new Error("bad progress document");
  return { ok: true, data: await progress.save(message.courseId, message.doc as ProgressDoc) };
}

/** True when `message` is the content script's report of a DOM change on a watched page. */
function isPageMutatedMessage(message: unknown): message is PageMutatedMessage {
  return typeof message === "object" && message !== null && (message as { type?: unknown }).type === "page:mutated";
}

/** True when `message` is one of the content-bridge message shapes. */
function isBridgeMessage(message: unknown): message is BridgeMessage {
  if (typeof message !== "object" || message === null) return false;
  const type = (message as { type?: unknown }).type;
  return type === "bridge:load" || type === "bridge:save";
}

/**
 * Registers the background listeners: the toolbar button opens the side panel and
 * flushes the offline mark queue; panel messages go to the backend; bridge messages
 * from the course pages go to the progress service.
 */
export function wireBackground(api: ChromeLike, backend: Backend): void {
  api.action.onClicked.addListener((tab) => {
    if (tab.windowId === undefined) return;
    openPanel(api, tab.windowId).catch((err: unknown) => console.error(err));
    // A failed flush stays queued; the next panel open retries it.
    backend.flush().catch(() => undefined);
  });

  api.tabs.onUpdated.addListener((tabId, changes) => {
    if (changes.url !== undefined) backend.tabNavigated(tabId);
  });

  api.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (isPageMutatedMessage(message)) {
      const tabId = (sender as { tab?: { id?: number } }).tab?.id;
      if (tabId !== undefined) backend.pageMutated(tabId);
      return false;
    }
    if ((message as { type?: unknown } | null)?.type === "card:openPanel") {
      const windowId = (sender as { tab?: { windowId?: number } }).tab?.windowId;
      if (windowId !== undefined) openPanel(api, windowId).catch((err: unknown) => console.error(err));
      return false;
    }
    const route = isPanelMessage(message)
      ? handlePanelMessage(backend, message)
      : isBridgeMessage(message)
        ? handleBridgeMessage(backend.progress, message)
        : undefined;
    if (route === undefined) return false;
    route.then(
      (reply) => sendResponse(reply),
      (err: unknown) => sendResponse({ ok: false, error: err instanceof Error ? err.message : String(err) }),
    );
    return true;
  });
}

// Service worker entry: runs only where the extension runtime exists (not under tests).
if (typeof chrome !== "undefined" && chrome.action) {
  wireBackground(chrome, createBackend(chrome, chrome.storage.local));
  wireBridgeRegistration(chrome.runtime, chrome.scripting, chrome.permissions, new TokenStore(chrome.storage.local));
}
