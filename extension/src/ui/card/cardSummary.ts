/**
 * Floating card, summary screen: the knowledge summary of the page (topics and the page
 * text summary). Text comes from TEXT_CARD_SUMMARY.
 */
import { TEXT_CARD_SUMMARY } from "../strings";
import { button, el } from "../dom";

const [
  TITLE,
  PAGE_TEXT,
  TOPICS,
  NEEDS_SCAN,
  LOADING,
  ERROR,
  OPEN_IN_PANEL,
  BACK,
] = TEXT_CARD_SUMMARY;

/** Where the summary stands. `ready` carries the page text summary and the topics found. */
export type SummaryStatus =
  | { kind: "needsScan" }
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "ready"; text: string; topics: string[] };

/** Callbacks of the summary card. */
export interface CardSummaryActions {
  onOpenInPanel(): void;
  onBack(): void;
}

/** Builds the summary card in the page; the caller attaches it. */
export function renderCardSummary(status: SummaryStatus, actions: CardSummaryActions): HTMLElement {
  const card = el("div", undefined, "card card-summary");
  card.append(el("h2", TITLE));
  if (status.kind === "needsScan") {
    card.append(el("p", NEEDS_SCAN, "needs-scan"));
  } else if (status.kind === "loading") {
    card.append(el("p", LOADING, "loading"));
  } else if (status.kind === "error") {
    card.append(el("p", ERROR, "error"));
  } else {
    card.append(el("h3", PAGE_TEXT));
    card.append(el("p", status.text, "page-text"));
    card.append(el("h3", TOPICS));
    const list = el("ul", undefined, "topics");
    for (const topic of status.topics) list.append(el("li", topic));
    card.append(list);
  }
  card.append(button(OPEN_IN_PANEL, actions.onOpenInPanel, "open-in-panel"));
  card.append(button(BACK, actions.onBack, "back"));
  return card;
}
