/**
 * Floating card, scan screen: the result of scanning the page. Results show only in the
 * panel while focus mode is on. Text comes from TEXT_CARD_SCAN.
 */
import { TEXT_CARD_SCAN } from "../strings";
import { button, el } from "../dom";
import type { PageCounts } from "./cardMain";

const [
  SCANNING,
  FOUND, // template: example numbers are replaced by the counts in foundLine
  EMPTY,
  ERROR,
  SHOW_IN_PANEL,
  SCAN_AGAIN,
  BACK,
  FOCUS_ON,
  SERVER_DOWN,
] = TEXT_CARD_SCAN;

/** Where the scan stands. */
export type ScanStatus =
  | { kind: "scanning" }
  | { kind: "done"; counts: PageCounts }
  | { kind: "empty" }
  | { kind: "error" }
  | { kind: "serverDown" };

/** What the scan card shows. */
export interface CardScanState {
  status: ScanStatus;
  focusOn: boolean;
}

/** Callbacks of the scan card. */
export interface CardScanActions {
  onShowInPanel(): void;
  onScanAgain(): void;
  onBack(): void;
}

/** The found-concepts line: the approved inventory text with its example numbers swapped for the counts. */
function foundLine(counts: PageCounts): string {
  const total = counts.new + counts.learning + counts.known;
  const values = [total, counts.new, counts.learning, counts.known];
  let next = 0;
  return FOUND.replace(/\d+/g, () => String(values[next++]));
}

/** The status line of the card for each scan state. */
function statusText(status: ScanStatus): string {
  switch (status.kind) {
    case "scanning":
      return SCANNING;
    case "done":
      return foundLine(status.counts);
    case "empty":
      return EMPTY;
    case "error":
      return ERROR;
    case "serverDown":
      return SERVER_DOWN;
  }
}

/** Builds the scan card in the page; the caller attaches it. */
export function renderCardScan(state: CardScanState, actions: CardScanActions): HTMLElement {
  const card = el("div", undefined, "card card-scan");
  card.append(el("p", statusText(state.status), `status ${state.status.kind}`));
  if (state.focusOn) card.append(el("p", FOCUS_ON, "focus-note"));
  card.append(button(SHOW_IN_PANEL, actions.onShowInPanel, "show-in-panel"));
  const scanning = state.status.kind === "scanning";
  const serverDown = state.status.kind === "serverDown";
  if (!scanning) {
    card.append(button(SCAN_AGAIN, actions.onScanAgain, "scan-again", serverDown));
  }
  card.append(button(BACK, actions.onBack, "back"));
  return card;
}
