/**
 * Image pin menu: the page overlay menu for an image's concepts. Text comes from the approved strings.
 */
import { IMAGE_PIN_MENU_TEXT, REVIEW_TEXT, TEXT_IMAGE_PIN_MENU } from "../strings";
import { type OverlayState, menuButton, overlayStatus, statusParagraph } from "./blockMenu";

const NOTE = IMAGE_PIN_MENU_TEXT.note;
const HEADER = IMAGE_PIN_MENU_TEXT.header;
const ERROR_IMAGE = IMAGE_PIN_MENU_TEXT.error;
/** Menu buttons by inventory index: every label except the note, the header and the error line. */
const BUTTON_INDEXES = [0, 1, 4, 5, 6, 7, 8, 9] as const;

/** Callbacks of the image menu: `onPick` gets the chosen label. */
export interface ImageMenuActions {
  onPick(label: string): void;
}

/** Builds the image pin menu card: heading, note, one button per action, and the state line. */
export function renderImageMenu(doc: Document, state: OverlayState, actions: ImageMenuActions): HTMLElement {
  const menu = doc.createElement("div");
  menu.className = "image-pin-menu";

  const title = doc.createElement("h2");
  title.textContent = HEADER;
  const note = doc.createElement("p");
  note.className = "menu-note";
  note.textContent = NOTE;
  menu.append(title, note);

  const list = doc.createElement("div");
  list.className = "menu-list";
  for (const index of BUTTON_INDEXES) {
    const label = TEXT_IMAGE_PIN_MENU[index];
    list.append(menuButton(doc, label, "btn", () => actions.onPick(label), state === "loading"));
  }
  menu.append(list);

  menu.append(statusParagraph(doc, overlayStatus(state, { empty: REVIEW_TEXT.noConcepts, error: ERROR_IMAGE })));
  return menu;
}
