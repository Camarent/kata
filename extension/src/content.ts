import { applyHighlights, clearHighlights, type HighlightResult } from "./highlight";
import { scanBlocks } from "./scanner";
import type { StorageArea } from "./tokenStore";
import { CARD_CSS } from "./ui/cardCss";
import { mountCardHost, type CardHost, type CardRuntime } from "./cardHost";
import { mountPin, type Pin } from "./ui/card/pin";
import { PinPositionStore } from "./ui/card/pinPosition";

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

/**
 * Starts a mutation observer on the page body; `onChange` runs on each batch of changes. Changes
 * inside `ignore` (the extension's own UI) do not count. Returns the stop function.
 */
export function watchPage(doc: Document, onChange: () => void, ignore?: Node): () => void {
  const observer = new MutationObserver((records) => {
    if (ignore && records.every((record) => ignore.contains(record.target))) return;
    onChange();
  });
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

/** The floating UI mounted in a page. */
export interface FloatingUi {
  pin: Pin;
  cards: CardHost;
  /** Removes the pin, the cards and the page watcher. */
  dispose(): void;
}

/**
 * Injects the card stylesheet into `doc`, mounts the floating pin at its stored position and the
 * page cards beside it. A pin button press opens the main card; after a scan the page is watched
 * and a change shows the page-changed prompt. The hover and block menus, image menu and list picker
 * need per-concept data and backend actions that are not wired on the page yet, so only the
 * page-changed overlay is mounted here.
 */
export async function mountFloatingUi(doc: Document, storage: StorageArea, runtime: CardRuntime): Promise<FloatingUi> {
  const style = doc.createElement("style");
  style.textContent = CARD_CSS;
  doc.head.append(style);
  const host = doc.createElement("div");
  doc.body.append(host);
  let stopWatching: (() => void) | undefined;
  let undoLast: (() => void) | null = null;
  // The side panel holds the full views and the quiz, so both card buttons ask the background to open it.
  const openPanel = (): void => void runtime.sendMessage({ type: "card:openPanel" }).catch(() => undefined);
  const cards = mountCardHost(doc, host, runtime, {
    onOpenPanel: openPanel,
    onQuiz: openPanel,
    onUndoable: (undo) => {
      undoLast = undo;
    },
    onScanned: () => {
      stopWatching?.();
      stopWatching = watchPage(doc, () => cards.pageChanged(), host);
    },
  });
  // The pin's Undo reverts the last undoable card action (turning focus on).
  let pin: Pin;
  try {
    pin = await mountPin(host, new PinPositionStore(storage), {
      canUndo: () => undoLast !== null,
      onUndo: () => {
        const undo = undoLast;
        undoLast = null;
        undo?.();
      },
    });
  } catch (error) {
    // A failed position read must not leave a half-mounted page: undo what was added.
    stopWatching?.();
    cards.dispose();
    host.remove();
    style.remove();
    throw error;
  }
  // Only the collapsed icon opens the main card; the expanded mascot keeps its undo mini-menu.
  pin.element.querySelectorAll(".pinbtn").forEach((button) => {
    if (!button.closest(".pinwrap")) button.addEventListener("click", () => cards.open());
  });
  return {
    pin,
    cards,
    dispose(): void {
      stopWatching?.();
      cards.dispose();
      pin.dispose();
      host.remove();
      style.remove();
    },
  };
}

// Content script entry: runs only where the extension runtime exists (not under tests).
if (typeof chrome !== "undefined" && chrome.runtime) {
  registerContentScript(chrome.runtime, document);
  // A failed mount is already cleaned up; the page works without the floating UI.
  mountFloatingUi(document, chrome.storage.local, chrome.runtime).catch(() => undefined);
}
