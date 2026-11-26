import type { PanelOpenApi } from "./browser";
import type { ScriptingLike } from "./bridgeRegister";
import type { HighlightResult } from "./highlight";

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

/** Reply to a panel message: the result, or the error text; `status` and `code` are set when the core refused it (CoreHttpError). */
export type PanelReply = { ok: true; data?: unknown } | { ok: false; error: string; status?: number; code?: string };

/** The part of `chrome` the background script uses; tests pass a fake with these members. */
export interface ChromeLike extends PanelOpenApi {
  action: {
    onClicked: { addListener(listener: (tab: { windowId?: number }) => void): void };
  };
  tabs: {
    query(query: { active: boolean; currentWindow: boolean }): Promise<{ id?: number; url?: string }[]>;
    sendMessage(tabId: number, message: ContentMessage): Promise<unknown>;
    create(properties: { url: string }): Promise<unknown>;
    onUpdated: { addListener(listener: (tabId: number, changes: { url?: string }) => void): void };
  };
  runtime: RuntimeLike;
  scripting: ScriptingLike;
}
