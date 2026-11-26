/**
 * Floating card, main screen: the page's concept counts and the card's actions.
 * Scan and Quiz are off while the server is down. Text comes from TEXT_CARD_MAIN.
 */
import { TEXT_CARD_MAIN } from "../strings";
import { button, el } from "../dom";

const [
  NEW,
  LEARNING,
  KNOWN,
  TOP_GAPS,
  NO_SCAN,
  SCAN,
  SUMMARY,
  QUIZ,
  FOCUS,
  OPEN_PANEL,
  COLLAPSE,
  SERVER_DOWN,
  PANEL_NOTE,
] = TEXT_CARD_MAIN;

/** Concept counts of the scanned page. */
export interface PageCounts {
  new: number;
  learning: number;
  known: number;
}

/** What the main card shows: counts are null before any scan. */
export interface CardMainState {
  counts: PageCounts | null;
  serverDown: boolean;
  focusOn: boolean;
}

/** Callbacks of the main card, one per button. */
export interface CardMainActions {
  onScan(): void;
  onSummary(): void;
  onQuiz(): void;
  onFocus(): void;
  onOpenPanel(): void;
  onCollapse(): void;
}

/** Builds the main card in the page; the caller attaches it. */
export function renderCardMain(state: CardMainState, actions: CardMainActions): HTMLElement {
  const card = el("div", undefined, "card card-main");
  card.append(el("h3", TOP_GAPS));
  if (state.counts === null) {
    card.append(el("p", NO_SCAN, "no-scan"));
  } else {
    const list = el("ul", undefined, "counts");
    for (const [label, n] of [
      [NEW, state.counts.new],
      [LEARNING, state.counts.learning],
      [KNOWN, state.counts.known],
    ] as const) {
      list.append(el("li", `${label}: ${n}`));
    }
    card.append(list);
  }
  if (state.serverDown) card.append(el("p", SERVER_DOWN, "server-down"));
  card.append(button(SCAN, actions.onScan, "scan", state.serverDown));
  card.append(button(SUMMARY, actions.onSummary, "summary"));
  card.append(button(QUIZ, actions.onQuiz, "quiz", state.serverDown));
  card.append(button(FOCUS, actions.onFocus, state.focusOn ? "focus on" : "focus"));
  card.append(button(OPEN_PANEL, actions.onOpenPanel, "open-panel"));
  card.append(button(COLLAPSE, actions.onCollapse, "x"));
  card.append(el("p", PANEL_NOTE, "panel-note"));
  return card;
}
