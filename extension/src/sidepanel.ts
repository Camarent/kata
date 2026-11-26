import type { CourseLink, ModelhostRequest, ModelhostResult } from "./background";
import type { ScanTopic } from "./scanSession";
import type { MarkOutcome } from "./offlineQueue";
import type { Session } from "./types";
import { courseErrorText, type ModelhostEngine } from "./coreClient";
import { renderReview, type ReviewRow, type ReviewState } from "./reviewScreen";
import { el } from "./ui/dom";
import { renderConnection, type ConnectionDetailProps } from "./ui/panel/connection";
import type { QueuedMarkView } from "./ui/panel/offlineQueue";
import { routeScreen } from "./ui/panel/router";

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
  /** Course limit of the server; the Courses section shows "n of limit" when it is above 0. */
  courseLimit?: number;
  /** Courses counted against the limit; defaults to the number of listed courses. */
  courseTotal?: number;
  /** Server link and unsynced count; when set, the connection detail shows under the header. */
  link?: ConnectionDetailProps;
  /** Marks waiting in the offline queue; non-null means the Not synced marks screen. */
  queue?: QueuedMarkView[] | null;
}

import type { PanelHandlers, ServerFormInput, SignInInput } from "./types";
export type { PanelHandlers, ServerFormInput, SignInInput } from "./types";

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

/** Native button with an accessible label that names the course. */
function courseButton(text: string, label: string, hidden = false): HTMLButtonElement {
  const button = el("button", text);
  button.type = "button";
  button.setAttribute("aria-label", label);
  button.hidden = hidden;
  return button;
}

/**
 * Create-course form: a title input and a Create button. A blank title is not sent. The input clears
 * on click; a failed create shows its text (courseErrorText) in the note and the button is disabled while it runs.
 */
function renderCreateCourse(handlers: PanelHandlers): HTMLFormElement {
  const form = el("form", undefined, "create-course");
  const titleLabel = el("label", "New course title");
  const title = el("input");
  title.name = "courseTitle";
  title.type = "text";
  titleLabel.append(title);
  const submit = el("button", "Create course");
  submit.type = "submit";
  const note = el("p", undefined, "course-note");
  note.setAttribute("role", "alert");
  form.append(titleLabel, submit, note);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = title.value.trim();
    if (text === "") return;
    title.value = "";
    note.textContent = "";
    submit.disabled = true;
    try {
      await handlers.onCreateCourse(text);
    } catch (err) {
      note.textContent = courseErrorText(err);
    } finally {
      submit.disabled = false;
    }
  });
  return form;
}

/**
 * Courses section: per course an "Open course" button and a Delete button, then the create-course form.
 * Delete asks first: "Confirm delete" and "Cancel" replace it. A failed open or delete shows its error text in the note.
 */
function renderCourses(state: PanelState, handlers: PanelHandlers): HTMLElement {
  const courses = state.courses ?? [];
  const section = el("section", undefined, "courses");
  section.append(el("h2", "Courses"));
  if ((state.courseLimit ?? 0) > 0) {
    const total = state.courseTotal ?? courses.length;
    section.append(el("p", `${total} of ${state.courseLimit}`, "course-limit"));
  }
  const ul = el("ul");
  for (const course of courses) {
    const item = el("li", undefined, "course");
    const open = courseButton("Open course", `Open ${course.title}`);
    const remove = courseButton("Delete", `Delete ${course.title}`);
    const confirm = courseButton("Confirm delete", `Confirm delete of ${course.title}`, true);
    const cancel = courseButton("Cancel", `Cancel delete of ${course.title}`, true);
    const note = el("span", undefined, "note");
    const showDelete = (): void => {
      remove.hidden = false;
      confirm.hidden = true;
      cancel.hidden = true;
      confirm.disabled = false;
      cancel.disabled = false;
    };
    open.addEventListener("click", async () => {
      open.disabled = true;
      try {
        await handlers.onOpenCourse(course.id);
        note.textContent = "opened";
      } catch (err) {
        note.textContent = err instanceof Error ? err.message : String(err);
        open.disabled = false;
      }
    });
    remove.addEventListener("click", () => {
      note.textContent = "";
      remove.hidden = true;
      confirm.hidden = false;
      cancel.hidden = false;
    });
    cancel.addEventListener("click", showDelete);
    confirm.addEventListener("click", async () => {
      confirm.disabled = true;
      cancel.disabled = true;
      try {
        await handlers.onDeleteCourse(course.id);
      } catch (err) {
        note.textContent = err instanceof Error ? err.message : String(err);
        showDelete();
      }
    });
    item.append(el("span", course.title, "course-title"), open, remove, confirm, cancel, note);
    ul.append(item);
  }
  section.append(ul, renderCreateCourse(handlers));
  return section;
}

/** Engines the "Use engine" choice offers, in menu order. */
const MODELHOST_ENGINES: ModelhostEngine[] = ["ollama", "strata", "none"];

/** Text for one fit figure: yes, no, or unknown when the figure is null or absent. */
function fitText(figure: unknown): string {
  if (figure === true) return "fits";
  if (figure === false) return "does not fit";
  return "unknown";
}

/** One row per measured model from a capabilities document; absent or malformed entries show nothing. */
function renderModelFits(capabilities: Record<string, unknown> | undefined): HTMLElement {
  const list = el("ul", undefined, "models");
  const models = capabilities?.models;
  if (typeof models !== "object" || models === null) return list;
  for (const [name, entry] of Object.entries(models)) {
    const fields = typeof entry === "object" && entry !== null ? (entry as Record<string, unknown>) : {};
    const text = `${name}: alone ${fitText(fields.fits_alone)}, together ${fitText(fields.fits_together)}`;
    list.append(el("li", text, "model"));
  }
  return list;
}

/**
 * Local model section: Start, Measure, Status and Use engine (with its engine choice). Each button
 * runs one modelhost job and shows its text and the per-model fits; buttons wait while a job runs.
 */
function renderLocalModel(handlers: PanelHandlers): HTMLElement {
  const section = el("section", undefined, "local-model");
  section.append(el("h2", "Local model"));
  const text = el("p", undefined, "modelhost-text");
  const models = el("div", undefined, "modelhost-models");
  const engine = el("select", undefined, "modelhost-engine");
  engine.setAttribute("aria-label", "Engine");
  for (const choice of MODELHOST_ENGINES) engine.append(el("option", choice));
  const actions: HTMLButtonElement[] = [];
  const run = async (request: ModelhostRequest): Promise<void> => {
    for (const button of actions) button.disabled = true;
    text.textContent = "Working...";
    try {
      const result = await handlers.onModelhost(request);
      if (result === "pending") {
        text.textContent = "waiting for the PC worker";
        models.replaceChildren();
      } else {
        text.textContent = result.text;
        models.replaceChildren(renderModelFits(result.capabilities));
      }
    } catch (err) {
      text.textContent = err instanceof Error ? err.message : String(err);
      models.replaceChildren();
    } finally {
      for (const button of actions) button.disabled = false;
    }
  };
  const button = (label: string, className: string, request: () => ModelhostRequest): HTMLButtonElement => {
    const node = el("button", label, className);
    node.type = "button";
    node.addEventListener("click", () => void run(request()));
    actions.push(node);
    return node;
  };
  const useEngine = button("Use engine", "modelhost-use", () => ({
    action: "use",
    engine: engine.value as ModelhostEngine,
  }));
  section.append(
    button("Start", "modelhost-start", () => ({ action: "start" })),
    button("Measure", "modelhost-measure", () => ({ action: "measure" })),
    button("Status", "modelhost-status", () => ({ action: "status" })),
    engine,
    useEngine,
    text,
    models,
  );
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
    const prefill = state.session?.baseUrl ?? "";
    // Signed out after an error shows the signed-out notice; a first run shows the sign-in form.
    if (state.session === null && state.status.kind === "error") {
      root.append(routeScreen("signed-out", { prefill }, handlers));
    } else {
      root.append(routeScreen("signin", { prefill, canCancel: state.session !== null }, handlers));
    }
    if (state.status.kind === "error" || state.status.kind === "notice") {
      root.append(el("p", statusText(state.status), "status"));
    }
    return;
  }
  if (state.review != null) {
    root.append(renderReviewView(state.review, handlers));
    return;
  }
  if (state.queue != null) {
    root.append(routeScreen("offline-queue", { marks: state.queue }, handlers));
    return;
  }
  root.append(renderConnection(state.session, handlers));
  if (state.link !== undefined) root.append(routeScreen("conn-detail", state.link, handlers));
  const review = el("button", "Review concepts", "review-open");
  review.type = "button";
  review.addEventListener("click", () => void handlers.onReview());
  root.append(review);
  const scan = el("button", "Scan this page", "scan");
  scan.type = "button";
  // A scan in flight disables the button; the boot script also ignores a second call.
  scan.disabled = state.status.kind === "scanning";
  scan.addEventListener("click", () => void handlers.onScan());
  root.append(scan);
  root.append(el("p", statusText(state.status), "status"));
  root.append(renderCourses(state, handlers));
  root.append(renderLocalModel(handlers));
  if (state.rows.length === 0 && state.status.kind === "idle") {
    root.append(el("p", "Nothing scanned yet", "empty"));
    return;
  }
  root.append(renderGroups(state.rows, handlers));
}
