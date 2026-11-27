// Review screen: concepts grouped by area (collapsed, with counts), searchable and filterable,
// one row per concept with a local state menu (ui/stateMenu.ts).
import { el } from "../dom";
import { STATE_ORDER, renderStateMenu } from "../stateMenu";
import { REVIEW_PENDING_COPY, REVIEW_TEXT } from "../strings";
import type { ReviewHandlers, ReviewRow, ReviewState } from "../../types";

const SEARCH_LABEL = REVIEW_TEXT.search;
const COUNT_LABEL = REVIEW_TEXT.count;
const ONLY_PAGE_LABEL = REVIEW_TEXT.onlyPage;
const COLLAPSE_LABEL = REVIEW_TEXT.collapseAll;
const EXPAND_LABEL = REVIEW_TEXT.expandAll;
const STATE_TEXT: Record<ReviewState, string> = {
  new: REVIEW_TEXT.new,
  learning: REVIEW_TEXT.learning,
  known: REVIEW_TEXT.known,
};
const OTHER_AREA = REVIEW_PENDING_COPY.otherArea;
const NO_CONCEPTS = REVIEW_PENDING_COPY.noConceptsToReview;
const KEY_STATE: Record<string, ReviewState> = { "1": "known", "2": "learning", "3": "new" };

/** Render the review tree into `root`, replacing its content: areas start collapsed with counts. */
export function renderReview(root: HTMLElement, rows: ReviewRow[], handlers: ReviewHandlers): void {
  root.replaceChildren();
  if (rows.length === 0) {
    root.append(el("p", NO_CONCEPTS));
    return;
  }
  const filter = { query: "", states: new Set<ReviewState>(), onlyPage: false };
  const tree = el("div", undefined, "review-tree");
  const total = el("p", undefined, "review-total");
  const areas = new Map<string, HTMLDetailsElement>();

  // Current states live here, so a redraw keeps saved changes without mutating the caller's rows.
  const states = new Map(rows.map((row) => [row.conceptId, row.state]));
  const stateOf = (row: ReviewRow): ReviewState | null => states.get(row.conceptId) ?? null;
  const saved: ReviewHandlers = {
    async onSet(conceptId, state) {
      await handlers.onSet(conceptId, state);
      states.set(conceptId, state);
    },
  };

  const matches = (row: ReviewRow): boolean => {
    const state = stateOf(row);
    if (filter.onlyPage && row.onPage !== true) return false;
    if (filter.states.size > 0 && (state === null || !filter.states.has(state))) return false;
    return row.label.toLowerCase().includes(filter.query.trim().toLowerCase());
  };

  const draw = (): void => {
    const visible = rows.filter(matches);
    const open = new Set([...areas].filter(([, details]) => details.open).map(([name]) => name));
    areas.clear();
    tree.replaceChildren();
    total.textContent = COUNT_LABEL.replace("N", String(visible.length)).replace("M", String(rows.length));
    const byArea = new Map<string, ReviewRow[]>();
    for (const row of visible) {
      const name = row.area ?? OTHER_AREA;
      byArea.set(name, [...(byArea.get(name) ?? []), row]);
    }
    for (const [name, areaRows] of byArea) {
      const details = el("details", undefined, "review-area");
      details.open = open.has(name);
      const counts = STATE_ORDER.map(
        (state) => `${STATE_TEXT[state]} ${areaRows.filter((r) => stateOf(r) === state).length}`,
      ).join(", ");
      details.append(el("summary", `${name} (${areaRows.length}) ${counts}`));
      const list = el("ul", undefined, "review");
      for (const row of areaRows) list.append(renderRow(row, stateOf(row), saved));
      details.append(list);
      areas.set(name, details);
      tree.append(details);
    }
  };

  const setAll = (open: boolean): void => {
    for (const details of areas.values()) details.open = open;
  };
  const collapse = el("button", COLLAPSE_LABEL, "collapse-all");
  collapse.type = "button";
  collapse.addEventListener("click", () => setAll(false));
  const expand = el("button", EXPAND_LABEL, "expand-all");
  expand.type = "button";
  expand.addEventListener("click", () => setAll(true));

  const search = el("input", undefined, "review-search");
  search.type = "search";
  search.placeholder = SEARCH_LABEL;
  search.setAttribute("aria-label", SEARCH_LABEL);
  search.addEventListener("input", () => {
    filter.query = search.value;
    draw();
  });

  const toolbar = el("div", undefined, "review-toolbar");
  toolbar.append(search, collapse, expand);
  for (const state of STATE_ORDER) {
    const button = el("button", STATE_TEXT[state], `filter-button filter-${state}`);
    button.type = "button";
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => {
      if (filter.states.has(state)) filter.states.delete(state);
      else filter.states.add(state);
      button.setAttribute("aria-pressed", String(filter.states.has(state)));
      draw();
    });
    toolbar.append(button);
  }
  const pageLabel = el("label", undefined, "only-page");
  const pageBox = el("input");
  pageBox.type = "checkbox";
  pageBox.addEventListener("change", () => {
    filter.onlyPage = pageBox.checked;
    draw();
  });
  pageLabel.append(pageBox, ONLY_PAGE_LABEL);
  toolbar.append(pageLabel);

  draw();
  root.append(toolbar, total, tree);
}

/** Move focus to the first button of the neighbouring row. */
function focusNeighbour(item: HTMLElement, step: -1 | 1): void {
  const sibling = step === 1 ? item.nextElementSibling : item.previousElementSibling;
  sibling?.querySelector("button")?.focus();
}

function renderRow(row: ReviewRow, state: ReviewState | null, handlers: ReviewHandlers): HTMLElement {
  const item = el("li", undefined, "review-row");
  item.append(el("span", row.label, "label"));
  let current = state;
  let saving = false;

  const choose = async (next: ReviewState): Promise<void> => {
    if (saving) return;
    saving = true;
    const buttons = [...item.querySelectorAll("button")];
    for (const button of buttons) button.disabled = true;
    try {
      await handlers.onSet(row.conceptId, next);
      current = next;
    } finally {
      saving = false;
      for (const button of buttons) {
        button.disabled = false;
        button.setAttribute("aria-pressed", String(button.classList.contains(`state-${current}`)));
      }
    }
  };

  const menu = renderStateMenu(current, choose);
  menu.setAttribute("aria-label", `State of ${row.label}`);
  item.append(menu);

  item.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      focusNeighbour(item, event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    const state = KEY_STATE[event.key];
    if (state !== undefined) {
      event.preventDefault();
      choose(state).catch((err: unknown) => {
        const note = item.querySelector(".note");
        if (note) note.textContent = err instanceof Error ? err.message : String(err);
      });
    }
  });
  return item;
}
