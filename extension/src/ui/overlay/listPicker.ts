/**
 * List picker: the page overlay card that adds a concept to one of the user's lists.
 * Text comes from the approved strings; the list names come from the caller.
 */
import { LIST_PICKER_TEXT } from "../strings";
import { type OverlayState, menuButton, overlayStatus, statusParagraph } from "./blockMenu";

const TITLE = LIST_PICKER_TEXT.title;
const PROMPT = LIST_PICKER_TEXT.prompt;
const NO_LISTS = LIST_PICKER_TEXT.noLists;
const NEW_LIST = LIST_PICKER_TEXT.newList;
const CANCEL = LIST_PICKER_TEXT.cancel;
const ERROR_LOAD = LIST_PICKER_TEXT.loadFailed;

/**
 * Callbacks of the list picker: `onPick` gets the chosen list name, `onNew` opens list creation.
 * Without `onNew` the New list button is not shown (list creation is not wired yet).
 */
export interface ListPickerActions {
  onPick(list: string): void;
  onNew?: () => void;
  onCancel(): void;
}

/** Builds the list picker card: title, prompt, one button per list, New list (when wired) and Cancel, and the state line. */
export function renderListPicker(
  doc: Document,
  state: OverlayState,
  lists: readonly string[],
  actions: ListPickerActions,
): HTMLElement {
  const card = doc.createElement("div");
  card.className = "list-picker";

  const title = doc.createElement("h2");
  title.textContent = TITLE;
  const prompt = doc.createElement("p");
  prompt.textContent = PROMPT;
  card.append(title, prompt);

  const busy = state === "loading";
  const picks = doc.createElement("div");
  picks.className = "menu-list";
  // Lists are only shown when the state is ready; loading and failed states show no stale names.
  if (state === "ready") {
    for (const name of lists) {
      picks.append(menuButton(doc, name, "btn", () => actions.onPick(name), busy));
    }
  }
  const onNew = actions.onNew;
  if (onNew) picks.append(menuButton(doc, NEW_LIST, "btn list-picker-new", () => onNew(), busy));
  picks.append(menuButton(doc, CANCEL, "btn list-picker-cancel", () => actions.onCancel()));
  card.append(picks);

  const status = overlayStatus(state, { empty: NO_LISTS, error: ERROR_LOAD });
  card.append(statusParagraph(doc, status));
  return card;
}
