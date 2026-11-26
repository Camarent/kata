/**
 * List picker: the page overlay card that adds a concept to one of the user's lists.
 * Text comes from the approved strings; the list names come from the caller.
 */
import { TEXT_LIST_PICKER } from "../strings";
import { type OverlayState, menuButton, overlayStatus, statusParagraph } from "./blockMenu";

const TITLE = TEXT_LIST_PICKER[0];
const PROMPT = TEXT_LIST_PICKER[1];
const NO_LISTS = TEXT_LIST_PICKER[2];
const NEW_LIST = TEXT_LIST_PICKER[3];
const CANCEL = TEXT_LIST_PICKER[5];
const ERROR_LOAD = TEXT_LIST_PICKER[6];

/** Callbacks of the list picker: `onPick` gets the chosen list name, `onNew` opens list creation. */
export interface ListPickerActions {
  onPick(list: string): void;
  onNew(): void;
  onCancel(): void;
}

/** Builds the list picker card: title, prompt, one button per list, New list and Cancel, and the state line. */
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
  picks.append(
    menuButton(doc, NEW_LIST, "btn list-picker-new", () => actions.onNew(), busy),
    menuButton(doc, CANCEL, "btn list-picker-cancel", () => actions.onCancel()),
  );
  card.append(picks);

  const status = overlayStatus(state, { empty: NO_LISTS, error: ERROR_LOAD });
  card.append(statusParagraph(doc, status));
  return card;
}
