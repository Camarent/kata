import type { ScanTopic } from "./scanSession";
import type { MarkOutcome } from "./offlineQueue";
import type { Session } from "./types";
import { renderReview, type ReviewRow, type ReviewState } from "./reviewScreen";

/** Group heading for rows whose block has no topic. */
const UNTAGGED = "untagged";

/** One scanned block: its topic when tagged, and whether the user already knows it. */
export interface PanelRow {
  blockId: string;
  topic: ScanTopic | null;
  known: boolean | null;
  reason?: string;
}

/** Status line shown above the results. */
type PanelStatus =
  | { kind: "idle" }
  | { kind: "scanning" }
  | { kind: "partial"; done: number; total: number }
  | { kind: "error"; reason: "timeout" | "auth" | "failed" };

/** Everything the panel draws. `session` null means signed out. `review` non-null means the review screen. */
export interface PanelState {
  session: Session | null;
  rows: PanelRow[];
  status: PanelStatus;
  review?: ReviewRow[] | null;
}

/** Values typed into the sign-in form. */
export interface SignInInput {
  code: string;
  deviceLabel: string;
}

/** User actions the panel reports back to the caller. */
export interface PanelHandlers {
  onSignIn: (input: SignInInput) => void | Promise<void>;
  onKnown: (topicId: number) => Promise<MarkOutcome>;
  onReview: () => Promise<void>;
  onSetConcept: (conceptId: number, state: ReviewState) => Promise<void>;
  onCloseReview: () => void;
}

/** Creates an element with text content; never parses markup. */
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

/** Sign-in form: pairing code and device label. */
function renderSignIn(handlers: PanelHandlers): HTMLElement {
  const form = el("form", undefined, "signin");
  const codeLabel = el("label", "Code");
  const code = el("input");
  code.name = "code";
  code.type = "text";
  codeLabel.append(code);
  const deviceLabel = el("label", "Device label");
  const device = el("input");
  device.name = "deviceLabel";
  device.type = "text";
  deviceLabel.append(device);
  const submit = el("button", "Sign in");
  submit.type = "submit";
  const error = el("p", undefined, "error");
  error.setAttribute("role", "alert");
  form.append(codeLabel, deviceLabel, submit, error);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const input = { code: code.value.trim(), deviceLabel: device.value.trim() };
    if (input.code === "" || input.deviceLabel === "") {
      error.textContent = "Enter the code and a device label";
      return;
    }
    error.textContent = "";
    void handlers.onSignIn(input);
  });
  return form;
}

/** User-facing text for each error reason. */
const ERROR_TEXT: Record<"timeout" | "auth" | "failed", string> = {
  timeout: "Core did not answer in time",
  auth: "Sign-in failed or expired",
  failed: "Something went wrong",
};

/** Status line text; errors name the cause in plain words. */
function statusText(status: PanelStatus): string {
  switch (status.kind) {
    case "idle":
      return "";
    case "scanning":
      return "scanning";
    case "partial":
      return `partial: ${status.done} of ${status.total}`;
    case "error":
      return ERROR_TEXT[status.reason];
  }
}

/** One result row: topic label, known/new badge, and the "I know this" button. */
function renderRow(row: PanelRow, handlers: PanelHandlers): HTMLElement {
  const item = el("li", undefined, "row");
  if (row.topic === null) {
    item.append(el("span", row.reason ?? "no topic", "reason"));
    return item;
  }
  const topic = row.topic;
  item.append(el("span", topic.label, "label"));
  item.append(el("span", row.known === true ? "known" : "new", "badge"));
  const button = el("button", "I know this");
  button.hidden = row.known === true;
  const note = el("span", undefined, "note");
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      const outcome = await handlers.onKnown(topic.id);
      note.textContent = outcome === "saved" ? "saved" : "queued (offline)";
    } catch {
      note.textContent = "failed";
      button.disabled = false;
    }
  });
  item.append(button, note);
  return item;
}

/** Results grouped by category, in first-seen order; untagged rows last. */
function renderGroups(rows: PanelRow[], handlers: PanelHandlers): HTMLElement {
  const groups = new Map<string, PanelRow[]>();
  const untagged: PanelRow[] = [];
  for (const row of rows) {
    if (row.topic === null) {
      untagged.push(row);
      continue;
    }
    const list = groups.get(row.topic.category) ?? [];
    list.push(row);
    groups.set(row.topic.category, list);
  }
  const root = el("div", undefined, "groups");
  const sections: [string, PanelRow[]][] = [...groups.entries()];
  if (untagged.length > 0) sections.push([UNTAGGED, untagged]);
  for (const [category, list] of sections) {
    const section = el("section", undefined, "group");
    section.append(el("h2", category));
    const ul = el("ul");
    for (const row of list) ul.append(renderRow(row, handlers));
    section.append(ul);
    root.append(section);
  }
  return root;
}

/** Review screen: a Back button to the scan view, then one row per concept. */
function renderReviewView(rows: ReviewRow[], handlers: PanelHandlers): HTMLElement {
  const view = el("div", undefined, "review-view");
  const back = el("button", "Back", "back");
  back.type = "button";
  back.addEventListener("click", () => handlers.onCloseReview());
  const list = el("div");
  renderReview(list, rows, { onSet: handlers.onSetConcept });
  view.append(back, list);
  return view;
}

/** Draws the panel into root: sign-in form when signed out, else status and grouped results. */
export function renderPanel(root: HTMLElement, state: PanelState, handlers: PanelHandlers): void {
  root.replaceChildren();
  if (state.session === null) {
    root.append(renderSignIn(handlers));
    if (state.status.kind === "error") root.append(el("p", statusText(state.status), "status"));
    return;
  }
  if (state.review != null) {
    root.append(renderReviewView(state.review, handlers));
    return;
  }
  const review = el("button", "Review concepts", "review-open");
  review.type = "button";
  review.addEventListener("click", () => void handlers.onReview());
  root.append(review);
  root.append(el("p", statusText(state.status), "status"));
  if (state.rows.length === 0 && state.status.kind === "idle") {
    root.append(el("p", "Nothing scanned yet", "empty"));
    return;
  }
  root.append(renderGroups(state.rows, handlers));
}
