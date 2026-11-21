// Review screen: one row per concept with a three-state control (known / learning / new).

export type ReviewState = "known" | "learning" | "new";

export interface ReviewRow {
  conceptId: number;
  label: string;
  /** null = abstain / not set yet. */
  state: ReviewState | null;
  evidence: string;
}

export interface ReviewHandlers {
  onSet(conceptId: number, state: ReviewState): Promise<void>;
}

const STATES: ReviewState[] = ["known", "learning", "new"];
const KEY_STATE: Record<string, ReviewState> = { "1": "known", "2": "learning", "3": "new" };

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  text?: string,
  className?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className !== undefined) node.className = className;
  return node;
}

/** Render the review list into `root`, replacing its content. */
export function renderReview(root: HTMLElement, rows: ReviewRow[], handlers: ReviewHandlers): void {
  root.replaceChildren();
  if (rows.length === 0) {
    root.append(el("p", "No concepts to review"));
    return;
  }
  const list = el("ul", undefined, "review");
  for (const row of rows) list.append(renderRow(row, handlers));
  root.append(list);
}

/** Move focus to the first button of the neighbouring row. */
function focusNeighbour(item: HTMLElement, step: -1 | 1): void {
  const sibling = step === 1 ? item.nextElementSibling : item.previousElementSibling;
  sibling?.querySelector("button")?.focus();
}

function renderRow(row: ReviewRow, handlers: ReviewHandlers): HTMLElement {
  const item = el("li", undefined, "review-row");
  item.append(el("span", row.label, "label"));
  const group = el("div", undefined, "states");
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", `State of ${row.label}`);
  const note = el("span", undefined, "note");
  const buttons = new Map<ReviewState, HTMLButtonElement>();
  let current = row.state;
  let saving = false;

  const paint = (): void => {
    for (const [state, button] of buttons) {
      button.setAttribute("aria-pressed", String(state === current));
    }
  };

  const choose = async (state: ReviewState): Promise<void> => {
    if (saving) return;
    saving = true;
    for (const button of buttons.values()) button.disabled = true;
    note.textContent = "";
    try {
      await handlers.onSet(row.conceptId, state);
      current = state;
      note.textContent = "saved";
    } catch {
      note.textContent = "failed";
    } finally {
      saving = false;
      for (const button of buttons.values()) button.disabled = false;
      paint();
    }
  };

  for (const state of STATES) {
    const button = el("button", state, "state-button");
    button.type = "button";
    button.addEventListener("click", () => void choose(state));
    buttons.set(state, button);
    group.append(button);
  }
  paint();
  item.append(group, note);

  item.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      focusNeighbour(item, event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    const state = KEY_STATE[event.key];
    if (state !== undefined) {
      event.preventDefault();
      void choose(state);
    }
  });
  return item;
}
