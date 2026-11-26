import type { Session } from "../../types";
import type { PanelHandlers } from "../../sidepanel";
import { el } from "../dom";
import { TEXT_CONN_DETAIL } from "../strings";

const [CONNECTED, , SERVER_DOWN, RETRY_NOW, SHOW_UNSYNCED, , SCAN_OFF] = TEXT_CONN_DETAIL;

/** Link state of the connection screen: whether the server answers and how many marks wait to sync. */
export interface ConnectionDetailProps {
  serverUp: boolean;
  unsynced: number;
}

/** Connected header: the session origin, with Change server and Disconnect. */
export function renderConnection(session: Session, handlers: PanelHandlers): HTMLElement {
  const box = el("div", undefined, "connection");
  box.append(el("p", session.baseUrl, "origin"));
  const change = el("button", "Change server", "change-server");
  change.type = "button";
  change.addEventListener("click", () => handlers.onChangeServer());
  const disconnect = el("button", "Disconnect", "disconnect");
  disconnect.type = "button";
  disconnect.addEventListener("click", () => void handlers.onDisconnect());
  box.append(change, disconnect);
  return box;
}

/**
 * Connection detail: "Connected" or "Server down" (with "Server down, n not synced" when marks wait).
 * Server down adds the note that Scan, Quiz and Generate course are off, and Retry now. Show unsynced
 * marks appears when marks wait. Retry now and Show unsynced marks are hidden when their handler is absent.
 */
export function renderConnectionDetail(props: ConnectionDetailProps, handlers: PanelHandlers): HTMLElement {
  const box = el("div", undefined, "conn-detail");
  if (props.serverUp) {
    box.append(el("p", CONNECTED, "conn-state"));
  } else if (props.unsynced > 0) {
    box.append(el("p", `Server down, ${props.unsynced} not synced`, "conn-state"));
    box.append(el("p", SCAN_OFF, "conn-note"));
  } else {
    box.append(el("p", SERVER_DOWN, "conn-state"));
    box.append(el("p", SCAN_OFF, "conn-note"));
  }
  if (!props.serverUp && handlers.onRetry) {
    const retry = el("button", RETRY_NOW, "retry-now");
    retry.type = "button";
    retry.addEventListener("click", () => void handlers.onRetry?.());
    box.append(retry);
  }
  if (props.unsynced > 0 && handlers.onShowQueue) {
    const show = el("button", SHOW_UNSYNCED, "show-queue");
    show.type = "button";
    show.addEventListener("click", () => handlers.onShowQueue?.());
    box.append(show);
  }
  return box;
}
