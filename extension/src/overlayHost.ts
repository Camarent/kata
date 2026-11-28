import { CLASS_HL, highlightItem, type HighlightResult } from "./highlight";
import type { HlMenuOptions } from "./ui/overlay/hlMenu";
import { attachHlHover } from "./ui/overlay/hlMenu";
import { BLOCK_ATTR } from "./scanner";
import type { PanelMessage, PanelReply, RuntimeLike } from "./messages";
import type { ScanConceptItem } from "./coreClientTypes";
import { type ConceptAction, renderBlockMenu, renderConceptActions, type OverlayState } from "./ui/overlay/blockMenu";

/** Undo window of the block menu's Delete / Ignore, in milliseconds before the change is sent. */
const CONCEPT_UNDO_WINDOW_MS = 3000;

/** The page overlays on highlighted words: one hover menu per `.hl` word span. */
export interface OverlayHost {
  /** Attaches a hover menu to every `.hl` word of `doc`, replacing the menus attached before. */
  attach(doc: Document, results: HighlightResult[]): void;
  /** Removes every hover menu attached so far. */
  clear(): void;
}

/** Sends one panel message through the background; throws the background's error when it failed. */
async function sendPanel(runtime: RuntimeLike, message: PanelMessage): Promise<void> {
  const reply = (await runtime.sendMessage(message)) as PanelReply | undefined;
  if (reply?.ok !== true) throw new Error(reply?.ok === false ? reply.error : "no reply from background");
}

/** Menu options for one word: the concept actions go to the background as panel messages. */
function menuOptions(runtime: RuntimeLike, topicId: number, item: ScanConceptItem): HlMenuOptions {
  return {
    topicId,
    word: item.word,
    item,
    offline: false,
    client: {
      chooseConcept: (topic, word, conceptId) =>
        sendPanel(runtime, { type: "panel:chooseConcept", topicId: topic, word, conceptId }),
      reassignConcept: (topic, word, fromConceptId, toConceptId) =>
        sendPanel(runtime, { type: "panel:reassignConcept", topicId: topic, word, fromConceptId, toConceptId }),
    },
    onState: (state) => {
      // A word without a concept has no mark to set.
      if (item.conceptId === null) return;
      return sendPanel(runtime, { type: "panel:setConcept", conceptId: item.conceptId, state });
    },
  };
}

/**
 * Block state of the block menu, from the block's scan result: a block with no concepts is empty.
 * Only ready and empty are reached: the background sends highlights only after a scan completed
 * without error (backgroundBackend.ts scanConcepts), so loading, error and offline never reach a block.
 */
function blockState(result: HighlightResult): OverlayState {
  return (result.concepts ?? []).length > 0 ? "ready" : "empty";
}

/** Places the menu under its block, in page coordinates. */
function placeBelow(menu: HTMLElement, block: HTMLElement): void {
  const rect = block.getBoundingClientRect();
  const view = block.ownerDocument.defaultView;
  menu.style.position = "absolute";
  menu.style.top = `${rect.bottom + (view?.scrollY ?? 0)}px`;
  menu.style.left = `${rect.left + (view?.scrollX ?? 0)}px`;
}

/** The block menu: the bulk card, then one row per concept with its Delete / Ignore actions. */
function blockMenuCard(doc: Document, runtime: RuntimeLike, result: HighlightResult): HTMLElement {
  // Bulk actions are not wired yet, so the card omits the bulk buttons (renderBlockMenu without onBulk).
  const menu = renderBlockMenu(doc, blockState(result), {});
  for (const item of result.concepts ?? []) {
    if (item.conceptId === null) continue;
    const conceptId = item.conceptId;
    const row = doc.createElement("div");
    row.className = "concept-row";
    const label = doc.createElement("p");
    label.className = "menu-note";
    label.textContent = item.label;
    const onCommit = (action: ConceptAction): void => {
      const message: PanelMessage =
        action === "ignore" ? { type: "panel:ignoreConcept", conceptId } : { type: "panel:deleteConcept", conceptId };
      sendPanel(runtime, message).catch(() => undefined);
    };
    row.append(label, renderConceptActions(doc, { windowMs: CONCEPT_UNDO_WINDOW_MS, onCommit }));
    menu.append(row);
  }
  return menu;
}

/**
 * Shows the block menu while the pointer or keyboard focus is on the block or on the menu.
 * Returns the detach that removes the listeners and any open menu.
 */
function attachBlockMenu(doc: Document, runtime: RuntimeLike, block: HTMLElement, result: HighlightResult): () => void {
  let menu: HTMLElement | null = null;
  const close = (): void => {
    menu?.remove();
    menu = null;
  };
  // Leaving the block or the menu closes it, unless the pointer or focus moves to the other one.
  const leave = (event: Event): void => {
    const next = (event as MouseEvent | FocusEvent).relatedTarget;
    if (next instanceof Node && (block.contains(next) || (menu?.contains(next) ?? false))) return;
    close();
  };
  const open = (): void => {
    if (menu !== null) return;
    menu = blockMenuCard(doc, runtime, result);
    menu.addEventListener("mouseleave", leave);
    menu.addEventListener("focusout", leave);
    placeBelow(menu, block);
    doc.body.append(menu);
  };
  block.addEventListener("mouseenter", open);
  block.addEventListener("focusin", open);
  block.addEventListener("mouseleave", leave);
  block.addEventListener("focusout", leave);
  return () => {
    block.removeEventListener("mouseenter", open);
    block.removeEventListener("focusin", open);
    block.removeEventListener("mouseleave", leave);
    block.removeEventListener("focusout", leave);
    close();
  };
}

/** Creates the overlay host of one page; `runtime` carries the menu actions to the background. */
export function createOverlayHost(runtime: RuntimeLike): OverlayHost {
  let detaches: (() => void)[] = [];
  const clear = (): void => {
    for (const detach of detaches) detach();
    detaches = [];
  };
  return {
    clear,
    attach(doc, results) {
      clear();
      const topics = new Map<string, number>();
      for (const result of results) {
        if (result.topic !== null) topics.set(result.blockId, result.topic.id);
      }
      const blocks = new Map<string, HTMLElement>();
      for (const block of Array.from(doc.querySelectorAll<HTMLElement>(`[${BLOCK_ATTR}]`))) {
        blocks.set(block.getAttribute(BLOCK_ATTR) ?? "", block);
      }
      for (const result of results) {
        const block = blocks.get(result.blockId);
        if (block !== undefined) detaches.push(attachBlockMenu(doc, runtime, block, result));
      }
      for (const span of Array.from(doc.querySelectorAll<HTMLElement>(`.${CLASS_HL}`))) {
        const item = highlightItem(span);
        const blockId = span.closest(`[${BLOCK_ATTR}]`)?.getAttribute(BLOCK_ATTR);
        const topicId = blockId === undefined || blockId === null ? undefined : topics.get(blockId);
        if (item === undefined || topicId === undefined) continue;
        detaches.push(attachHlHover(span, menuOptions(runtime, topicId, item)));
      }
    },
  };
}
