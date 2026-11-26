/**
 * Block menu: the page overlay menu for a text block (bulk add and status), plus the
 * Delete / Ignore actions for a concept. Text comes from the approved strings.
 * Delete and Ignore ask for confirmation, then offer one Undo before the change is committed.
 */
import { askConfirm } from "../confirm";
import { TEXT_BLOCK_MENU, TEXT_PIN, TEXT_REVIEW } from "../strings";
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
      return TEXT_PIN[4];
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

const [BLOCK_ALL_NEW, BLOCK_ALL_KNOWN, BLOCK_ALL_LEARNING, BLOCK_ADD_ALL, BLOCK_MIXED, BLOCK_TITLE, BLOCK_NOT_IN_TEXT] =
  TEXT_BLOCK_MENU;
// TEXT_REVIEW entries by inventory index: concept empty and error lines, Delete / Ignore and their confirm.
const EMPTY_CONCEPTS = TEXT_REVIEW[19];
const ERROR_CONCEPTS = TEXT_REVIEW[20];
const DELETE = TEXT_REVIEW[27];
const IGNORE = TEXT_REVIEW[28];
const YES_DELETE = TEXT_REVIEW[29];
const YES_IGNORE = TEXT_REVIEW[30];
const CANCEL = TEXT_REVIEW[31];
const DELETE_NOTE = TEXT_REVIEW[32];
const IGNORE_NOTE = TEXT_REVIEW[33];
const UNDO = TEXT_PIN[6];

/** Bulk actions shown in the block menu, in the inventory order. */
const BULK_LABELS = [BLOCK_ALL_NEW, BLOCK_ALL_KNOWN, BLOCK_ALL_LEARNING, BLOCK_ADD_ALL] as const;

/** Callbacks of the block menu: `onBulk` gets the chosen bulk label. */
export interface BlockMenuActions {
  onBulk(label: string): void;
}

/** Builds the block menu card: heading, bulk buttons, the mixed and not-in-text notes, and the state line. */
export function renderBlockMenu(doc: Document, state: OverlayState, actions: BlockMenuActions): HTMLElement {
  const menu = doc.createElement("div");
  menu.className = "block-menu";

  const title = doc.createElement("h2");
  title.textContent = BLOCK_TITLE;
  menu.append(title);

  const list = doc.createElement("div");
  list.className = "menu-list";
  for (const label of BULK_LABELS) {
    list.append(menuButton(doc, label, "btn", () => actions.onBulk(label), state === "loading"));
  }
  menu.append(list);

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
