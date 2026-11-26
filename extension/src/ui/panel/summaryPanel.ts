import { el } from "../dom";
import { TEXT_CONN_DETAIL, TEXT_SUMMARY_PANEL } from "../strings";

const [TITLE, PAGE_SUMMARY, TOPICS, PER_TOPIC, EMPTY, LOADING, ERROR, BACK, ADD_TOPIC] = TEXT_SUMMARY_PANEL;
/** Offline text: the summary has no offline line of its own, so it reuses the connection line. */
const [, , SERVER_DOWN] = TEXT_CONN_DETAIL;

/** Screen state: empty (page not scanned), loading, error, offline, or ready with topics. */
export type SummaryPanelStatus = "empty" | "loading" | "error" | "offline" | "ready";

/** One topic of the page with its concept count. */
export interface SummaryTopicView {
  name: string;
  conceptCount: number;
}

/** Props of the summary panel: the state, the topics, and the optional Back and Add-topic actions. */
export interface SummaryPanelProps {
  status: SummaryPanelStatus;
  topics: SummaryTopicView[];
  onBack?: () => void;
  onAddTopic?: (topic: string) => void;
}

/**
 * Knowledge summary: the title, the page text summary heading, then one body per state. Ready shows
 * each topic with its concept count and an Add all concepts of topic button when onAddTopic is present.
 */
export function renderSummaryPanel(props: SummaryPanelProps): HTMLElement {
  const screen = el("section", undefined, "summary-panel");
  screen.append(el("h2", TITLE));
  if (props.onBack) {
    const back = el("button", BACK, "back");
    back.type = "button";
    back.addEventListener("click", () => props.onBack?.());
    screen.append(back);
  }
  screen.append(el("h3", PAGE_SUMMARY));
  if (props.status === "empty") {
    screen.append(el("p", EMPTY, "empty"));
  } else if (props.status === "loading") {
    screen.append(el("p", LOADING, "loading"));
  } else if (props.status === "error") {
    screen.append(el("p", ERROR, "banner err"));
  } else if (props.status === "offline") {
    screen.append(el("p", SERVER_DOWN, "banner warn"));
  } else {
    screen.append(el("h3", TOPICS), el("p", PER_TOPIC, "note"));
    const list = el("ul", undefined, "rows");
    for (const topic of props.topics) {
      const item = el("li", undefined, "rrow");
      item.append(el("span", topic.name, "nm clamp2"), el("span", String(topic.conceptCount), "cnt"));
      if (props.onAddTopic) {
        const add = el("button", ADD_TOPIC, "add-topic");
        add.type = "button";
        add.addEventListener("click", () => props.onAddTopic?.(topic.name));
        item.append(add);
      }
      list.append(item);
    }
    screen.append(list);
  }
  return screen;
}
