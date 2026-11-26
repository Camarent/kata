/**
 * Page changed prompt: the floating card shown after the page changed in the DOM.
 * Its action rescans the page; Back dismisses the prompt. Text comes from the
 * approved strings so the card reads the same as the inventory.
 */
import { TEXT_PAGE_CHANGED } from "../strings";

/** Callbacks of the prompt: `onAction` rescans the page, `onBack` closes the prompt. */
export interface PageChangedActions {
  onAction(): void;
  onBack(): void;
}

const [TITLE, , BODY, , , ACTION_LABEL, BACK_LABEL] = TEXT_PAGE_CHANGED;

/** Builds the page changed card in `doc`; the caller attaches it to the page. */
export function renderPageChanged(doc: Document, actions: PageChangedActions): HTMLElement {
  const card = doc.createElement("div");
  card.className = "card page-changed";

  const header = doc.createElement("header");
  const title = doc.createElement("h2");
  title.textContent = TITLE;
  header.appendChild(title);

  const body = doc.createElement("p");
  body.textContent = BODY;

  const action = doc.createElement("button");
  action.type = "button";
  action.className = "page-changed-action";
  action.textContent = ACTION_LABEL;
  action.addEventListener("click", () => actions.onAction());

  const back = doc.createElement("button");
  back.type = "button";
  back.className = "x";
  back.textContent = BACK_LABEL;
  back.addEventListener("click", () => actions.onBack());

  card.append(header, body, action, back);
  return card;
}
