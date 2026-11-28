/**
 * Block menu: the page overlay menu for a text block (bulk add and status), plus the
 * Delete / Ignore actions for a concept. Text comes from the approved strings.
 * Delete and Ignore ask for confirmation, then offer one Undo before the change is committed.
 */
import { askConfirm } from "../confirm";
import { BLOCK_MENU_TEXT, PIN_TEXT, REVIEW_TEXT } from "../strings";
import { type Clock, deferCommit, type DeferredCommit } from "../undo";

/** Data state of an overlay list: ready shows the items; the others show one status line. */
export type OverlayState = "ready" | "empty" | "loading" | "error" | "offline";

/** Status line for a non-ready state, or null. Loading has no approved text, so it shows none. */
export function overlayStatus(state: OverlayState, texts: { empty: string; error: string }): string | null {
  switch (state) {
    case "empty":
      return texts.empty;
    case "error":
      return texts.error;
    case "offline":
      return PIN_TEXT.offline;
    default:
      return null;
  }
}

/** A button that runs onClick; disabled while the list is loading. */
export function menuButton(doc: Document, label: string, className: string, onClick: () => void, disabled = false): HTMLButtonElement {
  const button = doc.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.disabled = disabled;
  button.addEventListener("click", () => onClick());
  return button;
}

/** Paragraph with the status line of a non-ready state; empty when the state has none. */
export function statusParagraph(doc: Document, text: string | null): HTMLElement {
  const p = doc.createElement("p");
  p.className = "menu-status";
  if (text !== null) p.textContent = text;
  return p;
}

const BLOCK_ALL_NEW = BLOCK_MENU_TEXT.allNew;
const BLOCK_ALL_KNOWN = BLOCK_MENU_TEXT.allKnown;
const BLOCK_ALL_LEARNING = BLOCK_MENU_TEXT.allLearning;
const BLOCK_ADD_ALL = BLOCK_MENU_TEXT.addAll;
const BLOCK_MIXED = BLOCK_MENU_TEXT.mixed;
const BLOCK_TITLE = BLOCK_MENU_TEXT.title;
const BLOCK_NOT_IN_TEXT = BLOCK_MENU_TEXT.notInText;
const EMPTY_CONCEPTS = REVIEW_TEXT.noConcepts;
const ERROR_CONCEPTS = REVIEW_TEXT.loadFailed;
const DELETE = REVIEW_TEXT.delete;
const IGNORE = REVIEW_TEXT.ignore;
const YES_DELETE = REVIEW_TEXT.yesDelete;
const YES_IGNORE = REVIEW_TEXT.yesIgnore;
const CANCEL = REVIEW_TEXT.cancel;
const DELETE_NOTE = REVIEW_TEXT.deleteNote;
const IGNORE_NOTE = REVIEW_TEXT.ignoreNote;
const UNDO = PIN_TEXT.undo;

/** Bulk actions shown in the block menu, in the inventory order. */
const BULK_LABELS = [BLOCK_ALL_NEW, BLOCK_ALL_KNOWN, BLOCK_ALL_LEARNING, BLOCK_ADD_ALL] as const;

/** Callbacks of the block menu: `onBulk` gets the chosen bulk label. Without it the bulk buttons are not shown. */
export interface BlockMenuActions {
  onBulk?(label: string): void;
}

/** Builds the block menu card: heading, bulk buttons (only with `onBulk`), mixed and not-in-text notes, state line. */
export function renderBlockMenu(doc: Document, state: OverlayState, actions: BlockMenuActions): HTMLElement {
  const menu = doc.createElement("div");
  menu.className = "block-menu";

  const title = doc.createElement("h2");
  title.textContent = BLOCK_TITLE;
  menu.append(title);

  const onBulk = actions.onBulk;
  if (onBulk !== undefined) {
    const list = doc.createElement("div");
    list.className = "menu-list";
    for (const label of BULK_LABELS) {
      list.append(menuButton(doc, label, "btn", () => onBulk(label), state === "loading"));
    }
    menu.append(list);
  }

  const mixed = doc.createElement("p");
  mixed.className = "menu-note";
  mixed.textContent = BLOCK_MIXED;
  const notInText = doc.createElement("p");
  notInText.className = "menu-note";
  notInText.textContent = BLOCK_NOT_IN_TEXT;
  menu.append(mixed, notInText);

  menu.append(statusParagraph(doc, overlayStatus(state, { empty: EMPTY_CONCEPTS, error: ERROR_CONCEPTS })));
  return menu;
}

/** Concept actions: Delete and Ignore. Each asks for confirmation, then offers one Undo. */
export type ConceptAction = "delete" | "ignore";

export interface ConceptActionOptions {
  /** Undo window in milliseconds before the change is committed. */
  windowMs: number;
  /** Timer source; tests inject a fake one. Defaults to the window clock. */
  clock?: Clock;
  /** Runs once the undo window has passed without Undo. */
  onCommit(action: ConceptAction): void;
}

/** Builds the Delete / Ignore buttons. Only one change is pending at a time. */
export function renderConceptActions(doc: Document, options: ConceptActionOptions): HTMLElement {
  const box = doc.createElement("div");
  box.className = "concept-actions";
  const row = doc.createElement("div");
  row.className = "menu-list";
  box.append(row);

  let pending: DeferredCommit | null = null;

  const request = async (action: ConceptAction, message: string, confirmLabel: string): Promise<void> => {
    if (pending?.pending) return;
    const ok = await askConfirm(box, { message, confirmLabel, cancelLabel: CANCEL });
    if (!ok) return;
    const undoButton = menuButton(doc, UNDO, "btn concept-undo", () => {
      if (commit.undo()) undoButton.remove();
    });
    const commit = deferCommit(
      () => {
        undoButton.remove();
        options.onCommit(action);
      },
      options.windowMs,
      options.clock,
    );
    pending = commit;
    box.append(undoButton);
  };

  row.append(
    menuButton(doc, DELETE, "btn concept-delete", () => void request("delete", DELETE_NOTE, YES_DELETE)),
    menuButton(doc, IGNORE, "btn concept-ignore", () => void request("ignore", IGNORE_NOTE, YES_IGNORE)),
  );
  return box;
}
