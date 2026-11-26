import type { ConceptMark } from "../../coreClientTypes";
import type { PanelHandlers } from "../../types";
import { el } from "../dom";
import { TEXT_OFFLINE_QUEUE } from "../strings";

const [TITLE, EMPTY, NOT_SYNCED, SYNCED, KEPT_NOTE, WINS_NOTE, RETRY_NOW, BACK] = TEXT_OFFLINE_QUEUE;

/** One mark on the queue screen: its concept label, state, time text and whether the core has it. */
export interface QueuedMarkView {
  label: string;
  state: ConceptMark["state"];
  time: string;
  synced: boolean;
}

/** Props of the offline-queue screen: the marks in send order. */
export interface OfflineQueueProps {
  marks: QueuedMarkView[];
}

/**
 * Not synced marks: "Nothing waiting to sync." when the queue is empty, else one row per mark with
 * its Not synced or Synced badge. Retry now and Back appear when their handler is present.
 */
export function renderOfflineQueue(props: OfflineQueueProps, handlers: PanelHandlers): HTMLElement {
  const screen = el("section", undefined, "offline-queue");
  screen.append(el("h2", TITLE));
  if (props.marks.length === 0) {
    screen.append(el("p", EMPTY, "empty"));
  } else {
    const list = el("ul");
    for (const mark of props.marks) {
      const item = el("li", undefined, "queued-mark");
      item.append(
        el("span", mark.label, "label"),
        el("span", mark.state, "state"),
        el("span", mark.time, "time"),
        el("span", mark.synced ? SYNCED : NOT_SYNCED, "badge"),
      );
      list.append(item);
    }
    screen.append(list);
  }
  screen.append(el("p", KEPT_NOTE, "note"), el("p", WINS_NOTE, "note"));
  if (handlers.onRetry) {
    const retry = el("button", RETRY_NOW, "retry-now");
    retry.type = "button";
    retry.addEventListener("click", () => void handlers.onRetry?.());
    screen.append(retry);
  }
  if (handlers.onCloseQueue) {
    const back = el("button", BACK, "back");
    back.type = "button";
    back.addEventListener("click", () => handlers.onCloseQueue?.());
    screen.append(back);
  }
  return screen;
}
