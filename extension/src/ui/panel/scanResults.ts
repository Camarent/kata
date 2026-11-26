import type { PanelHandlers } from "../../types";
import { el } from "../dom";
import { TEXT_SCAN_RESULTS } from "../strings";

const [
  TITLE,
  SCAN_PAGE,
  ,
  ,
  ,
  ,
  ,
  ,
  ,
  ,
  ,
  ,
  ,
  ,
  ,
  KNOWN,
  LEARNING,
  NEW,
  ,
  ,
  ,
  ,
  ,
  ,
  ,
  ,
  ,
  EMPTY,
  SCANNING,
  ERROR,
  OFFLINE,
] = TEXT_SCAN_RESULTS;

/** Concept state shown as a badge on a scan-result row. */
export type ScanResultState = "new" | "learning" | "known";

/** One concept row: its label and state. Long labels clamp to two lines. */
export interface ScanResultRow {
  label: string;
  state: ScanResultState;
}

/** Screen state: empty (no scan yet), loading, error, offline, or ready with rows. */
export type ScanResultsStatus = "empty" | "loading" | "error" | "offline" | "ready";

/** Props of the scan-results screen. */
export interface ScanResultsProps {
  status: ScanResultsStatus;
  rows: ScanResultRow[];
}

const BADGE: Record<ScanResultState, string> = { new: NEW, learning: LEARNING, known: KNOWN };

/**
 * Scan results: the title and Scan page button, then one body per state. Ready rows show the
 * concept label (clamped to two lines) and its state badge. Scan page always shows and calls onScan.
 */
export function renderScanResults(props: ScanResultsProps, handlers: PanelHandlers): HTMLElement {
  const screen = el("section", undefined, "scan-results");
  screen.append(el("h2", TITLE));
  const scan = el("button", SCAN_PAGE, "scan-page");
  scan.type = "button";
  scan.addEventListener("click", () => void handlers.onScan());
  screen.append(scan);
  if (props.status === "empty") {
    screen.append(el("p", EMPTY, "empty"));
  } else if (props.status === "loading") {
    screen.append(el("p", SCANNING, "loading"));
  } else if (props.status === "error") {
    screen.append(el("p", ERROR, "banner err"));
  } else if (props.status === "offline") {
    screen.append(el("p", OFFLINE, "banner warn"));
  } else {
    const list = el("ul", undefined, "rows");
    for (const row of props.rows) {
      const item = el("li", undefined, "rrow");
      item.append(el("span", row.label, "nm clamp2"), el("span", BADGE[row.state], `badge sg ${row.state}`));
      list.append(item);
    }
    screen.append(list);
  }
  return screen;
}
