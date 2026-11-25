import { applyHighlights, clearHighlights, type HighlightResult } from "./highlight";
import { scanBlocks } from "./scanner";

/** Message the side panel sends to the page through the background script. */
export type ContentMessage =
  | { type: "scan" }
  | { type: "highlight"; results: HighlightResult[] }
  | { type: "clear" }
  | { type: "watch" }
  | { type: "unwatch" };

/** Sent by the page to the background script after a DOM change while watched. */
export interface PageMutatedMessage {
  type: "page:mutated";
}

/** Answer to `scan`: the page blocks, id and text only (no DOM references). */
export interface ScanResponse {
  blocks: { id: string; text: string }[];
}

/** Minimal shape of the `chrome.runtime` messaging API used here. */
export interface RuntimeLike {
  onMessage: {
    addListener(listener: (message: unknown, sender: unknown, sendResponse: (response: unknown) => void) => boolean | void): void;
  };
  sendMessage(message: PageMutatedMessage): Promise<unknown>;
}

/** Starts a mutation observer on the page body; `onChange` runs on each batch of changes. Returns the stop function. */
export function watchPage(doc: Document, onChange: () => void): () => void {
  const observer = new MutationObserver(() => onChange());
  observer.observe(doc.body, { subtree: true, childList: true, characterData: true });
  return () => observer.disconnect();
}

/** Answers one content message against `doc`; unknown messages get no answer. */
export function handleContentMessage(message: ContentMessage, doc: Document): ScanResponse | undefined {
  switch (message.type) {
    case "scan":
      return { blocks: scanBlocks(doc).map((block) => ({ id: block.id, text: block.text })) };
    case "highlight":
      applyHighlights(doc, message.results);
      return undefined;
    case "clear":
      clearHighlights(doc);
      return undefined;
    case "watch":
    case "unwatch":
      // Handled by registerContentScript, which owns the observer.
      return undefined;
  }
}

/** True when `message` has one of the content message shapes. */
function isContentMessage(message: unknown): message is ContentMessage {
  if (typeof message !== "object" || message === null) return false;
  const type = (message as { type?: unknown }).type;
  return type === "scan" || type === "highlight" || type === "clear" || type === "watch" || type === "unwatch";
}

/** Registers the page listener on the runtime; called once by the content script. */
export function registerContentScript(runtime: RuntimeLike, doc: Document): void {
  let stopWatching: (() => void) | undefined;
  runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!isContentMessage(message)) return false;
    if (message.type === "watch" || message.type === "unwatch") {
      stopWatching?.();
      stopWatching = undefined;
      if (message.type === "watch") {
        stopWatching = watchPage(doc, () => {
          runtime.sendMessage({ type: "page:mutated" }).catch(() => undefined);
        });
      }
      sendResponse(undefined);
      return false;
    }
    sendResponse(handleContentMessage(message, doc));
    return false;
  });
}

// Content script entry: runs only where the extension runtime exists (not under tests).
if (typeof chrome !== "undefined" && chrome.runtime) {
  registerContentScript(chrome.runtime, document);
}
