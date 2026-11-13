import { applyHighlights, clearHighlights, type HighlightResult } from "./highlight";
import { scanBlocks } from "./scanner";

/** Message the side panel sends to the page through the background script. */
export type ContentMessage =
  | { type: "scan" }
  | { type: "highlight"; results: HighlightResult[] }
  | { type: "clear" };

/** Answer to `scan`: the page blocks, id and text only (no DOM references). */
export interface ScanResponse {
  blocks: { id: string; text: string }[];
}

/** Minimal shape of the `chrome.runtime.onMessage` listener API used here. */
export interface RuntimeLike {
  onMessage: {
    addListener(listener: (message: unknown, sender: unknown, sendResponse: (response: unknown) => void) => boolean | void): void;
  };
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
  }
}

/** True when `message` has one of the content message shapes. */
function isContentMessage(message: unknown): message is ContentMessage {
  if (typeof message !== "object" || message === null) return false;
  const type = (message as { type?: unknown }).type;
  return type === "scan" || type === "highlight" || type === "clear";
}

/** Registers the page listener on the runtime; called once by the content script. */
export function registerContentScript(runtime: RuntimeLike, doc: Document): void {
  runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!isContentMessage(message)) return false;
    sendResponse(handleContentMessage(message, doc));
    return false;
  });
}

// Content script entry: runs only where the extension runtime exists (not under tests).
if (typeof chrome !== "undefined" && chrome.runtime) {
  registerContentScript(chrome.runtime, document);
}
