import type { CourseLink, ModelhostRequest, ModelhostResult, ReviewRow } from "./messages";
import type { ScanTopic } from "./scanSession";
import type { MarkOutcome } from "./offlineQueue";
import type { ModelhostEngine } from "./coreClient";
import type { Session } from "./types";
import { button, el } from "./ui/dom";
import { SCAN_RESULTS_TEXT } from "./ui/strings";
import { renderConnection, type ConnectionDetailProps } from "./ui/panel/connection";
import type { IgnoredRowView } from "./ui/panel/ignoredList";
import type { QueuedMarkView } from "./ui/panel/offlineQueue";
import type { SettingsPage } from "./ui/panel/settingsHome";
import type { TrackSortKey, TracksTabProps } from "./ui/panel/tracksTab";
import { routeScreen } from "./ui/panel/router";
import type { ScanResultsStatus } from "./ui/panel/scanResults";
import { ERROR_TEXT, SCANNING_TEXT, partialText } from "./ui/panel/statusText";

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

/** A track screen the Tracks tab opened: the detail of one track, or the create form. */
export type TrackScreen = { kind: "detail"; trackId: number } | { kind: "create" };

/**
 * Everything the panel draws. `session` null means signed out. `changing` true shows the
 * sign-in form over a live session (change server). `tab` is the current tab (default scan);
 * `review` non-null shows the Review tab with those rows.
 */
export interface PanelState {
  session: Session | null;
  rows: PanelRow[];
  status: PanelStatus;
  changing?: boolean;
  tab?: PanelTab;
  review?: ReviewRow[] | null;
  courses?: CourseLink[];
  /** True when the courses could not be loaded; the Courses tab then shows its could-not-load text. */
  coursesFailed?: boolean;
  /** Course limit of the server; the Courses tab shows "n of limit" when it is above 0. */
  courseLimit?: number;
  /** Courses counted against the limit; defaults to the number of listed courses. */
  courseTotal?: number;
  /** Server link and unsynced count; when set, the connection detail shows under the header. */
  link?: ConnectionDetailProps;
  /** Marks waiting in the offline queue; non-null means the Not synced marks screen. */
  queue?: QueuedMarkView[] | null;
  /** Tracks tab state and rows; unset means still loading. */
  tracks?: TracksTabProps;
  /** Track screen the Tracks tab opened: one track's detail, or the create form; null or unset shows the list. */
  trackScreen?: TrackScreen | null;
  /** Settings page drawn in place of the settings home; null or unset shows the home. */
  settingsPage?: SettingsPage | null;
  /** Ignored concepts for the ignored list page. */
  ignored?: IgnoredRowView[];
}

import type { PanelHandlers, PanelTab, ServerFormInput, SignInInput } from "./types";
export type { PanelHandlers, PanelTab, ServerFormInput, SignInInput } from "./types";

/** Status line text; errors name the cause in plain words. */
function statusText(status: PanelStatus): string {
  switch (status.kind) {
    case "idle":
      return "";
    case "scanning":
      return SCANNING_TEXT;
    case "partial":
      return partialText(status.done, status.total);
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

/** Tabs in bar order, with the label each shows (labels come from the Scan results inventory text). */
const TABS: [PanelTab, string][] = [
  ["scan", SCAN_RESULTS_TEXT.scan],
  ["review", SCAN_RESULTS_TEXT.review],
  ["courses", SCAN_RESULTS_TEXT.courses],
  ["tracks", SCAN_RESULTS_TEXT.tracks],
  ["settings", SCAN_RESULTS_TEXT.settings],
];

/** Tab bar: one button per tab; the current one carries aria-current. */
function renderTabBar(current: PanelTab, handlers: PanelHandlers): HTMLElement {
  const bar = el("nav", undefined, "tabs");
  for (const [tab, label] of TABS) {
    const item = button(label, () => void handlers.onTab(tab), `tab tab-${tab}`);
    if (tab === current) item.setAttribute("aria-current", "page");
    bar.append(item);
  }
  return bar;
}

/** Scan tab: the scan-results screen, the status line, then the grouped rows with "I know this". */
function renderScanTab(state: PanelState, handlers: PanelHandlers): HTMLElement {
  const tab = el("div", undefined, "scan-tab");
  const scanning = state.status.kind === "scanning";
  const empty = state.rows.length === 0 && state.status.kind === "idle";
  const status: ScanResultsStatus = scanning ? "loading" : empty ? "empty" : "ready";
  const screen = routeScreen("scan-results", { status, rows: [] }, handlers);
  // A scan in flight disables the button; the boot script also ignores a second call.
  const scanButton = screen.querySelector<HTMLButtonElement>("button.scan-page");
  if (scanButton !== null) scanButton.disabled = scanning;
  tab.append(screen, el("p", statusText(state.status), "status"));
  if (!empty) tab.append(renderGroups(state.rows, handlers));
  return tab;
}

/** Courses tab: the ready courses with Open course and Delete; Generate course is fed by the courses task. */
function renderCoursesView(state: PanelState, handlers: PanelHandlers): HTMLElement {
  const props = {
    courses: state.courses ?? [],
    courseLimit: state.courseLimit,
    courseTotal: state.courseTotal,
    loadFailed: state.coursesFailed === true,
    serverDown: state.link?.serverUp === false,
    onGenerate: () => {},
  };
  return routeScreen("courses-tab", props, handlers);
}

/** Tracks tab: the state the panel holds (loading until the panel:tracks reply arrives), with its rows. */
function renderTracksView(state: PanelState, handlers: PanelHandlers): HTMLElement {
  if (state.trackScreen?.kind === "detail" && handlers.trackDetail !== undefined) {
    // The track data is not loaded yet, so the detail stays in its loading state.
    return routeScreen("track-detail", { state: "loading", track: null }, handlers.trackDetail);
  }
  if (state.trackScreen?.kind === "create" && handlers.trackCreate !== undefined) {
    return routeScreen("track-create", { state: "form" }, handlers.trackCreate);
  }
  const props: TracksTabProps = state.tracks ?? { state: "loading", rows: [], sort: "name" };
  const actions = {
    onOpen: (trackId: number) => handlers.onOpenTrack?.(trackId),
    onNew: () => handlers.onNewTrack?.(),
    onSort: (sort: TrackSortKey) => handlers.onSortTracks?.(sort),
  };
  return routeScreen("tracks-tab", props, actions);
}

/** Settings tab: the ignored list when its page is open, else the settings home then the local model section. */
function renderSettingsView(state: PanelState, handlers: PanelHandlers): HTMLElement {
  const tab = el("div", undefined, "settings-tab");
  if (state.settingsPage === "ignored" && handlers.ignoredList !== undefined) {
    tab.append(routeScreen("ignored-list", { rows: state.ignored ?? [] }, handlers.ignoredList));
    return tab;
  }
  const open = (page: SettingsPage) => {
    void handlers.onOpenSettingsPage?.(page);
  };
  tab.append(routeScreen("settings-home", undefined, { onOpen: open }), renderLocalModel(handlers));
  return tab;
}

/** Tab the panel shows: the review rows win over the stored tab. */
function currentTab(state: PanelState): PanelTab {
  return state.review != null ? "review" : (state.tab ?? "scan");
}

/** Draws the panel into root: sign-in form when signed out, else the tab bar and the current tab's screen. */
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
  if (state.queue != null) {
    root.append(routeScreen("offline-queue", { marks: state.queue }, handlers));
    return;
  }
  const tab = currentTab(state);
  root.append(renderConnection(state.session, handlers));
  if (state.link !== undefined) root.append(routeScreen("conn-detail", state.link, handlers));
  root.append(renderTabBar(tab, handlers));
  if (tab === "review") {
    root.append(routeScreen("review", state.review ?? [], { onSet: handlers.onSetConcept }));
  } else if (tab === "courses") {
    root.append(renderCoursesView(state, handlers));
  } else if (tab === "tracks") {
    root.append(renderTracksView(state, handlers));
  } else if (tab === "settings") {
    root.append(renderSettingsView(state, handlers));
  } else {
    root.append(renderScanTab(state, handlers));
  }
}
