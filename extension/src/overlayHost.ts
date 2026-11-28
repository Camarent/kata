import { CLASS_HL, highlightItem, type HighlightResult } from "./highlight";
import type { HlMenuOptions } from "./ui/overlay/hlMenu";
import { attachHlHover } from "./ui/overlay/hlMenu";
import { BLOCK_ATTR } from "./scanner";
import type { PanelMessage, PanelReply, RuntimeLike } from "./messages";
import type { NamedList, ScanConceptItem } from "./coreClientTypes";
import {
  type ConceptAction,
  menuButton,
  renderBlockMenu,
  renderConceptActions,
  type OverlayState,
} from "./ui/overlay/blockMenu";
import { renderImageMenu } from "./ui/overlay/imageMenu";
import { type ListPickerActions, renderListPicker } from "./ui/overlay/listPicker";
import { BLOCK_MENU_TEXT, IMAGE_PIN_MENU_TEXT } from "./ui/strings";

/** Undo window of the block menu's Delete / Ignore, in milliseconds before the change is sent. */
const CONCEPT_UNDO_WINDOW_MS = 3000;

/** The page overlays on highlighted words: one hover menu per `.hl` word span. */
export interface OverlayHost {
  /** Attaches a hover menu to every `.hl` word of `doc`, replacing the menus attached before. */
  attach(doc: Document, results: HighlightResult[]): void;
  /** Removes every hover menu attached so far. */
  clear(): void;
}

/** Sends one panel message through the background; returns the reply data, throws the background's error when it failed. */
async function panelData(runtime: RuntimeLike, message: PanelMessage): Promise<unknown> {
  const reply = (await runtime.sendMessage(message)) as PanelReply | undefined;
  if (reply?.ok !== true) throw new Error(reply?.ok === false ? reply.error : "no reply from background");
  return reply.data;
}

/** Sends one panel message through the background; throws the background's error when it failed. */
async function sendPanel(runtime: RuntimeLike, message: PanelMessage): Promise<void> {
  await panelData(runtime, message);
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

/**
 * Swaps the block menu body for the list picker. The lists load from the background; a pick adds the
 * block's concepts to that list and closes the menu. Cancel closes the menu; New list is not shown.
 */
function openListPicker(
  doc: Document,
  runtime: RuntimeLike,
  menu: HTMLElement,
  conceptIds: number[],
  close: () => void,
): void {
  // No onNew: the New list button is hidden until list creation exists.
  const actions: ListPickerActions = {
    onPick: (listName) => {
      // A failed add shows the error state of the picker (the lists are not reloaded).
      panelData(runtime, { type: "panel:addToList", listName, conceptIds }).then(close, () => {
        menu.replaceChildren(renderListPicker(doc, "error", [], actions));
      });
    },
    onCancel: close,
  };
  menu.replaceChildren(renderListPicker(doc, "loading", [], actions));
  const listsOf = async (): Promise<string[]> => {
    const lists = (await panelData(runtime, { type: "panel:lists" })) as NamedList[];
    return lists.map((list) => list.name);
  };
  void listsOf().then(
    (names) => menu.replaceChildren(renderListPicker(doc, names.length > 0 ? "ready" : "empty", names, actions)),
    () => menu.replaceChildren(renderListPicker(doc, "error", [], actions)),
  );
}

/** The block menu: the bulk card, then one row per concept with its Delete / Ignore actions. */
function blockMenuCard(doc: Document, runtime: RuntimeLike, result: HighlightResult, close: () => void): HTMLElement {
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
  // "Add all to list" adds every concept of the block to one list, picked in the list picker.
  const conceptIds = (result.concepts ?? []).flatMap((item) => (item.conceptId === null ? [] : [item.conceptId]));
  if (conceptIds.length > 0) {
    const addAll = menuButton(doc, BLOCK_MENU_TEXT.addAll, "btn block-add-list", () =>
      openListPicker(doc, runtime, menu, conceptIds, close),
    );
    menu.append(addAll);
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
    menu = blockMenuCard(doc, runtime, result, close);
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

/**
 * Image pin: a small pin button shown over a page image while the pointer is on the image; hovering
 * the pin (or pressing it) opens the image menu under the image. Image concepts need a vision model (D33), so the menu shows
 * its empty state and its actions reach the background as `panel:imageAction`.
 */
function attachImageMenu(doc: Document, runtime: RuntimeLike, img: HTMLImageElement): () => void {
  let pin: HTMLButtonElement | null = null;
  let menu: HTMLElement | null = null;
  const hidePin = (): void => {
    pin?.remove();
    pin = null;
  };
  const closeMenu = (): void => {
    menu?.remove();
    menu = null;
  };
  const openMenu = (): void => {
    hidePin();
    if (menu !== null) return;
    const actions = {
      onPick: (label: string) => {
        sendPanel(runtime, { type: "panel:imageAction", label }).catch(() => undefined);
      },
    };
    menu = renderImageMenu(doc, "empty", actions);
    // Leaving the menu closes it, unless the pointer moves back onto the image.
    menu.addEventListener("mouseleave", (event) => {
      const next = (event as MouseEvent).relatedTarget;
      if (next instanceof Node && img.contains(next)) return;
      closeMenu();
    });
    placeBelow(menu, img);
    doc.body.append(menu);
  };
  const showPin = (): void => {
    if (pin !== null || menu !== null) return;
    const button = doc.createElement("button");
    button.type = "button";
    button.className = "image-pin";
    button.title = IMAGE_PIN_MENU_TEXT.header;
    button.setAttribute("aria-label", IMAGE_PIN_MENU_TEXT.header);
    const rect = img.getBoundingClientRect();
    const view = doc.defaultView;
    button.style.position = "absolute";
    button.style.top = `${rect.top + (view?.scrollY ?? 0)}px`;
    button.style.left = `${rect.left + (view?.scrollX ?? 0)}px`;
    // Hovering the pin opens the menu (docs/design/extension-ui.md, item 33); a press does too.
    button.addEventListener("mouseenter", openMenu);
    button.addEventListener("click", openMenu);
    button.addEventListener("mouseleave", (event) => {
      const next = (event as MouseEvent).relatedTarget;
      if (!(next instanceof Node && img.contains(next))) hidePin();
    });
    pin = button;
    doc.body.append(button);
  };
  const leaveImage = (event: Event): void => {
    const next = (event as MouseEvent).relatedTarget;
    if (!(next instanceof Node && pin?.contains(next))) hidePin();
  };
  img.addEventListener("mouseenter", showPin);
  img.addEventListener("mouseleave", leaveImage);
  return () => {
    img.removeEventListener("mouseenter", showPin);
    img.removeEventListener("mouseleave", leaveImage);
    hidePin();
    closeMenu();
  };
}

/**
 * Attaches the image menu to every `img` of `doc`, the ones present now and the ones added later
 * (lazy load, single-page apps); returns the detach that removes them all. Called once per page by
 * the content script.
 */
export function attachImageMenus(doc: Document, runtime: RuntimeLike): () => void {
  const detaches = new Map<HTMLImageElement, () => void>();
  const attachTo = (img: HTMLImageElement): void => {
    if (!detaches.has(img)) detaches.set(img, attachImageMenu(doc, runtime, img));
  };
  const attachWithin = (root: Element): void => {
    if (root instanceof HTMLImageElement) attachTo(root);
    for (const img of Array.from(root.querySelectorAll("img"))) attachTo(img);
  };
  const observer = new MutationObserver((records) => {
    for (const record of records) {
      for (const node of Array.from(record.addedNodes)) {
        if (node instanceof Element) attachWithin(node);
      }
    }
  });
  attachWithin(doc.documentElement);
  observer.observe(doc.documentElement, { childList: true, subtree: true });
  return () => {
    observer.disconnect();
    for (const detach of detaches.values()) detach();
    detaches.clear();
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
