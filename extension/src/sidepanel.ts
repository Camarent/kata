import type { CourseLink } from "./background";
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
  | { kind: "error"; reason: "timeout" | "auth" | "failed" }
  | { kind: "notice"; text: string };

/**
 * Everything the panel draws. `session` null means signed out. `changing` true shows the
 * sign-in form over a live session (change server). `review` non-null means the review screen.
 * `courses` empty means no Courses section.
 */
export interface PanelState {
  session: Session | null;
  rows: PanelRow[];
  status: PanelStatus;
  changing?: boolean;
  review?: ReviewRow[] | null;
  courses?: CourseLink[];
}

/** Values typed into the sign-in form: pairing code and device label. */
export interface SignInInput {
  code: string;
  deviceLabel: string;
}

/** Sign-in form values with the typed server URL. */
export interface ServerFormInput extends SignInInput {
  baseUrl: string;
}

/** User actions the panel reports back to the caller. */
export interface PanelHandlers {
  onSignIn: (input: ServerFormInput) => void | Promise<void>;
  onDisconnect: () => void | Promise<void>;
  onChangeServer: () => void;
  onCancelChange: () => void;
  onKnown: (topicId: number) => Promise<MarkOutcome>;
  onReview: () => Promise<void>;
  onSetConcept: (conceptId: number, state: ReviewState) => Promise<void>;
  onCloseReview: () => void;
  onOpenCourse: (courseId: number) => Promise<void>;
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

/** Sign-in form: server URL, pairing code and device label. `prefill` fills the URL; `canCancel` adds Cancel. */
function renderSignIn(handlers: PanelHandlers, prefill: string, canCancel: boolean): HTMLElement {
  const form = el("form", undefined, "signin");
  const serverLabel = el("label", "Server URL");
  const server = el("input");
  server.name = "baseUrl";
  server.type = "text";
  server.placeholder = "https://kata.example.org";
  server.value = prefill;
  serverLabel.append(server);
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
  const submit = el("button", "Connect");
  submit.type = "submit";
  const error = el("p", undefined, "error");
  error.setAttribute("role", "alert");
  form.append(serverLabel, codeLabel, deviceLabel, submit);
  if (canCancel) {
    const cancel = el("button", "Cancel");
    cancel.type = "button";
    cancel.addEventListener("click", () => handlers.onCancelChange());
    form.append(cancel);
  }
  form.append(error);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const input = { baseUrl: server.value.trim(), code: code.value.trim(), deviceLabel: device.value.trim() };
    if (input.code === "" || input.deviceLabel === "") {
      error.textContent = "Enter the code and a device label";
      return;
    }
    if (input.baseUrl === "") {
      error.textContent = "Enter the server URL";
      return;
    }
    error.textContent = "";
    void handlers.onSignIn(input);
  });
  return form;
}

/** Connected header: the session origin, with Change server and Disconnect. */
function renderConnection(session: Session, handlers: PanelHandlers): HTMLElement {
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
    case "notice":
      return status.text;
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

/** Courses section: one "Open course" button per ready course; a failed open shows its error text. */
function renderCourses(courses: CourseLink[], handlers: PanelHandlers): HTMLElement {
  const section = el("section", undefined, "courses");
  section.append(el("h2", "Courses"));
  const ul = el("ul");
  for (const course of courses) {
    const item = el("li", undefined, "course");
    const button = el("button", "Open course");
    button.type = "button";
    const note = el("span", undefined, "note");
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await handlers.onOpenCourse(course.id);
        note.textContent = "opened";
      } catch (err) {
        note.textContent = err instanceof Error ? err.message : String(err);
        button.disabled = false;
      }
    });
    item.append(el("span", course.title, "course-title"), button, note);
    ul.append(item);
  }
  section.append(ul);
  return section;
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
  if (state.session === null || state.changing) {
    root.append(renderSignIn(handlers, state.session?.baseUrl ?? "", state.session !== null));
    if (state.status.kind === "error" || state.status.kind === "notice") {
      root.append(el("p", statusText(state.status), "status"));
    }
    return;
  }
  if (state.review != null) {
    root.append(renderReviewView(state.review, handlers));
    return;
  }
  root.append(renderConnection(state.session, handlers));
  const review = el("button", "Review concepts", "review-open");
  review.type = "button";
  review.addEventListener("click", () => void handlers.onReview());
  root.append(review);
  root.append(el("p", statusText(state.status), "status"));
  if (state.courses && state.courses.length > 0) root.append(renderCourses(state.courses, handlers));
  if (state.rows.length === 0 && state.status.kind === "idle") {
    root.append(el("p", "Nothing scanned yet", "empty"));
    return;
  }
  root.append(renderGroups(state.rows, handlers));
}
