import type { CourseList, ModelhostRequest, ModelhostResult, PanelMessage, PanelReply, ReviewRow, ReviewState } from "./messages";
import { renderPanel, type PanelHandlers, type PanelRow, type PanelTab, type PanelState, type ServerFormInput } from "./sidepanel";
import { TokenStore, type StorageArea } from "./tokenStore";
import { CoreHttpError } from "./coreClient";
import type {
  ConceptAlias,
  DecisionPoint,
  ExamResult,
  IgnoredConcept,
  Joke,
  JokeSource,
  SummaryReply,
  Track,
  TrackPage,
} from "./coreClientTypes";
import type { MarkOutcome } from "./offlineQueue";
import { validateServerUrl } from "./serverUrl";
import { ignoredClientHandlers, type IgnoredClient, type IgnoredRowView } from "./ui/panel/ignoredList";
import type { SettingsPage } from "./ui/panel/settingsHome";
import type { TrackDetailView } from "./ui/panel/trackDetail";
import type { TrackRowView, TrackSortKey } from "./ui/panel/tracksTab";
import { PANEL_CSS } from "./ui/panelCss";
import type { Session } from "./types";

/** Origin permission request or removal: the host pattern `<origin>/*`. */
export interface OriginsRequest {
  origins: string[];
}

/** One track as the Tracks tab draws it. The core sends no progress or pace, so the status stands in for progress. */
function trackRowView(track: Track): TrackRowView {
  return { id: track.id, name: track.name, progress: track.status, tooSlow: false };
}

/**
 * One track as the detail screen draws it. The core Track has no goal, progress, velocity or pace flags,
 * so those take neutral empty values (open work in docs/roadmap.md); the items stand in for the sources.
 */
function trackDetailView(track: Track): TrackDetailView {
  return {
    name: track.name,
    goal: "",
    deadline: track.deadline,
    progress: "",
    velocity: "",
    finishEarly: false,
    tooSlow: false,
    dropReason: null,
    sources: track.items.map((item) => item.label),
  };
}

/** Rows in the order the sort key asks for; only the name sort reorders, the others keep the core order. */
function sortTrackRows(rows: TrackRowView[], sort: TrackSortKey): TrackRowView[] {
  return sort === "name" ? [...rows].sort((a, b) => a.name.localeCompare(b.name)) : rows;
}

/** The part of `chrome` the side panel page uses; tests pass a fake with these members. */
export interface PanelChromeLike {
  runtime: { sendMessage(message: PanelMessage): Promise<PanelReply> };
  storage: { local: StorageArea };
  permissions: {
    request(request: OriginsRequest): Promise<boolean>;
    remove(request: OriginsRequest): Promise<boolean>;
    onRemoved: { addListener(listener: (removed: { origins?: string[] }) => void): void };
  };
}

/** Shown when the user refuses the origin permission; nothing is stored or sent. */
const DENIED_TEXT = "Permission for this server was not granted. Nothing was saved.";

/**
 * Mounts the side panel into root: loads the stored session, draws it, and sends
 * each user action to the background script as a panel message.
 */
export async function bootPanel(root: HTMLElement, api: PanelChromeLike): Promise<void> {
  const tokens = new TokenStore(api.storage.local);
  const state: PanelState = {
    session: await tokens.loadSession(),
    rows: [],
    status: { kind: "idle" },
    review: null,
    tab: "scan",
    courses: [],
  };
  const draw = (): void => renderPanel(root, state, handlers);

  /** Ready courses for the Courses tab; a refused list leaves it empty and marks the load as failed. */
  const loadCourses = async (): Promise<void> => {
    const reply = await api.runtime.sendMessage({ type: "panel:courses" });
    const list = reply.ok ? (reply.data as CourseList | undefined) : undefined;
    state.courses = list && Array.isArray(list.items) ? list.items : [];
    state.coursesFailed = !reply.ok;
    state.courseLimit = list?.limit;
    state.courseTotal = list?.total;
  };
  if (state.session !== null) await loadCourses();

  /** Shows a sign-in or server message on the status line. */
  const notice = (text: string): void => {
    state.status = { kind: "notice", text };
    draw();
  };

  /** Drops the panel's view of the session: first-run form, no rows, no courses. */
  const clearSession = (): void => {
    state.session = null;
    state.changing = false;
    state.rows = [];
    state.review = null;
    state.courses = [];
    state.coursesFailed = false;
    state.coursePage = null;
    state.tracks = undefined;
    state.trackViews = undefined;
    state.settingsPage = null;
    state.tab = "scan";
    state.status = { kind: "idle" };
  };

  /** Sends one panel message and returns its data; a core refusal keeps its status and code. */
  const send = async <T>(message: PanelMessage): Promise<T> => {
    const reply = await api.runtime.sendMessage(message);
    if (!reply.ok) {
      if (reply.status !== undefined) throw new CoreHttpError(reply.status, reply.code);
      throw new Error(reply.error);
    }
    return reply.data as T;
  };

  /** Tracks for the Tracks tab from the panel:tracks reply; a refused list shows the could-not-load state. */
  const loadTracks = async (): Promise<void> => {
    const sort = state.tracks?.sort ?? "name";
    state.tracks = { state: "loading", rows: [], sort };
    draw();
    try {
      const page = await send<TrackPage>({ type: "panel:tracks" });
      const rows = page.items.map(trackRowView);
      state.trackViews = Object.fromEntries(page.items.map((track) => [track.id, trackDetailView(track)]));
      state.tracks = { state: rows.length === 0 ? "empty" : "ready", rows: sortTrackRows(rows, sort), sort };
    } catch {
      state.tracks = { state: "error", rows: [], sort };
    }
    draw();
  };

  /** Ignored concepts for the ignored list page, from the panel:ignored reply. */
  const loadIgnored = async (): Promise<void> => {
    const list = await send<IgnoredConcept[]>({ type: "panel:ignored" });
    state.ignored = list.map((concept): IgnoredRowView => ({ conceptId: concept.concept_id, label: concept.label }));
  };

  /** The two ignored calls the ignored list makes, each as one panel message. */
  const ignoredClient: IgnoredClient = {
    ignoreConcept: (conceptId) => send<void>({ type: "panel:ignoreConcept", conceptId }),
    unignoreConcept: (conceptId) => send<void>({ type: "panel:unignoreConcept", conceptId }),
  };

  /** After Restore or Undo the ignored list page reloads its rows from the core. */
  const refreshIgnored = async (): Promise<void> => {
    await loadIgnored();
    draw();
  };

  /** Back from a track screen to the Tracks list. */
  const backFromTrack = (): void => {
    state.trackScreen = null;
    draw();
  };

  /** Track the detail, add-source or quiz screen belongs to; undefined when no such screen is open. */
  const shownTrackId = (): number | undefined => {
    const screen = state.trackScreen;
    return screen === undefined || screen === null || screen.kind === "create" ? undefined : screen.trackId;
  };

  /** Opens the add-source or quiz screen for the track the detail shows. */
  const openFromDetail = (kind: "source-add" | "quiz"): void => {
    const trackId = shownTrackId();
    if (trackId === undefined) return;
    state.trackScreen = { kind, trackId };
    draw();
  };

  /** Back from the add-source or quiz screen to the detail of the same track. */
  const backToDetail = (): void => {
    const trackId = shownTrackId();
    state.trackScreen = trackId === undefined ? null : { kind: "detail", trackId };
    draw();
  };

  /** Back from the ignored list page to the settings home. */
  const backToSettings = (): void => {
    state.settingsPage = null;
    draw();
  };

  /** Back from an exam screen to the settings home. */
  const closeExam = (): void => {
    state.examScreen = null;
    draw();
  };

  const handlers: PanelHandlers = {
    async onSignIn(input: ServerFormInput) {
      const server = validateServerUrl(input.baseUrl);
      if (!server.ok) {
        notice(server.reason);
        return;
      }
      // First awaited call: the permission request stays inside the user's Connect click.
      const granted = await api.permissions.request({ origins: [server.pattern] });
      if (!granted) {
        notice(DENIED_TEXT);
        return;
      }
      const previous = originPattern(state.session);
      const reply = await api.runtime.sendMessage({
        type: "panel:signIn",
        input: { baseUrl: server.baseUrl, code: input.code, deviceLabel: input.deviceLabel },
      });
      if (!reply.ok) {
        // Release the new origin unless it is the current session's origin.
        if (server.pattern !== previous) await api.permissions.remove({ origins: [server.pattern] });
        notice(reply.error);
        return;
      }
      state.session = await tokens.loadSession();
      state.changing = false;
      state.status = { kind: "idle" };
      // Change server: the old origin goes once the new session is saved.
      if (previous !== null && previous !== server.pattern) await api.permissions.remove({ origins: [previous] });
      await loadCourses();
      draw();
    },

    async onDisconnect() {
      const pattern = originPattern(state.session);
      if (pattern !== null) await api.permissions.remove({ origins: [pattern] });
      const reply = await api.runtime.sendMessage({ type: "panel:disconnect" });
      if (!reply.ok) {
        notice(reply.error);
        return;
      }
      clearSession();
      draw();
    },

    onChangeServer() {
      state.changing = true;
      state.status = { kind: "idle" };
      draw();
    },

    onCancelChange() {
      state.changing = false;
      state.status = { kind: "idle" };
      draw();
    },

    async onScan() {
      // A scan already in flight: the second click sends nothing.
      if (state.status.kind === "scanning") return;
      state.status = { kind: "scanning" };
      draw();
      try {
        const reply = await api.runtime.sendMessage({ type: "panel:scan" });
        if (reply.ok) {
          state.rows = reply.data as PanelRow[];
          state.status = { kind: "idle" };
        } else {
          state.status = { kind: "error", reason: scanErrorReason(reply) };
        }
      } catch {
        state.status = { kind: "error", reason: "failed" };
      }
      draw();
    },

    async onKnown(topicId: number): Promise<MarkOutcome> {
      const reply = await api.runtime.sendMessage({ type: "panel:known", topicId });
      if (!reply.ok) throw new Error(reply.error);
      return reply.data as MarkOutcome;
    },

    async onTab(tab: PanelTab) {
      if (tab === "review") {
        await handlers.onReview();
        return;
      }
      state.review = null;
      state.tab = tab;
      state.settingsPage = null;
      state.examScreen = null;
      if (tab === "tracks") {
        await loadTracks();
        return;
      }
      draw();
    },

    onSortTracks(sort: TrackSortKey) {
      if (state.tracks === undefined) return;
      state.tracks = { ...state.tracks, sort, rows: sortTrackRows(state.tracks.rows, sort) };
      draw();
    },

    async onOpenSettingsPage(page: SettingsPage) {
      // Only the ignored list page has a screen so far; the other settings pages keep the home.
      if (page !== "ignored") return;
      try {
        await loadIgnored();
      } catch {
        // The list did not load: the settings home stays drawn.
        return;
      }
      state.settingsPage = "ignored";
      draw();
    },

    onOpenExamEntry() {
      state.examScreen = { kind: "entry", failed: false };
      draw();
    },

    examEntry: {
      async onSave(input) {
        // The score field is a percentage from 0 to 100 ("85"); the core takes a fraction from 0 to 1.
        // A blank score is refused: Number("") is 0, which would store a 0% result.
        const trimmed = input.score.trim();
        const percent = trimmed === "" ? Number.NaN : Number(trimmed);
        if (!Number.isFinite(percent) || percent < 0 || percent > 100 || input.date === "") {
          throw new Error("invalid exam result");
        }
        const payload = JSON.stringify({
          origin: "page",
          taken_at: `${input.date}T00:00:00Z`,
          passed: input.passed,
          score: percent / 100,
          concepts: [],
        });
        const result = await send<ExamResult>({ type: "panel:importExamResult", payload });
        state.examScreen = { kind: "result", result };
        draw();
      },
      onCancel: closeExam,
    },

    examResult: {
      onConfirm(conceptIds) {
        const shown = state.examScreen;
        if (shown?.kind !== "result") return;
        // A refused confirm keeps the result screen with an error line; Done can be pressed again.
        void send<ExamResult>({ type: "panel:confirmExamResult", resultId: shown.result.id, conceptIds }).then(
          closeExam,
          () => {
            state.examScreen = { kind: "result", result: shown.result, confirmFailed: true };
            draw();
          },
        );
      },
    },

    onOpenTrack(trackId: number) {
      state.trackScreen = { kind: "detail", trackId };
      draw();
    },

    onNewTrack() {
      state.trackScreen = { kind: "create" };
      draw();
    },

    async onReview() {
      const reply = await api.runtime.sendMessage({ type: "panel:review" });
      if (reply.ok) {
        state.review = reply.data as ReviewRow[];
        state.tab = "review";
      } else {
        state.status = { kind: "error", reason: "failed" };
      }
      draw();
    },

    async onSetConcept(conceptId: number, conceptState: ReviewState) {
      const reply = await api.runtime.sendMessage({ type: "panel:setConcept", conceptId, state: conceptState });
      if (!reply.ok) throw new Error(reply.error);
    },

    onCloseReview() {
      state.review = null;
      state.tab = "scan";
      draw();
    },

    async onOpenCourse(courseId: number) {
      const reply = await api.runtime.sendMessage({ type: "panel:openCourse", courseId });
      if (!reply.ok) throw new Error(reply.error);
      const course = state.courses?.find((listed) => listed.id === courseId);
      if (course === undefined) return;
      state.coursePage = { title: course.title, version: course.version };
      draw();
    },
    onCloseCourse() {
      state.coursePage = null;
      draw();
    },
    async onCreateCourse(title: string) {
      const reply = await api.runtime.sendMessage({ type: "panel:createCourse", title });
      // A core refusal keeps its status and code so the panel can show the matching text.
      if (!reply.ok) {
        if (reply.status !== undefined) throw new CoreHttpError(reply.status, reply.code);
        throw new Error(reply.error);
      }
      await loadCourses();
      draw();
    },
    async onRegenerateCourse(courseId: number) {
      const reply = await api.runtime.sendMessage({ type: "panel:regenerateCourse", courseId });
      if (!reply.ok) {
        if (reply.status !== undefined) throw new CoreHttpError(reply.status, reply.code);
        throw new Error(reply.error);
      }
      await loadCourses();
      draw();
    },
    async onDeleteCourse(courseId: number) {
      const reply = await api.runtime.sendMessage({ type: "panel:deleteCourse", courseId });
      if (!reply.ok) throw new Error(reply.error);
      // The list and the "n of limit" count come from the core again, so the deleted course leaves the panel.
      await loadCourses();
      draw();
    },

    async onModelhost(request: ModelhostRequest) {
      const reply = await api.runtime.sendMessage({ type: "panel:modelhost", request });
      if (!reply.ok) throw new Error(reply.error);
      return reply.data as ModelhostResult;
    },

    onLoadTracks: (opts) => send<TrackPage>({ type: "panel:tracks", limit: opts?.limit, beforeId: opts?.beforeId }),
    onGetTrack: (trackId) => send<Track>({ type: "panel:getTrack", trackId }),
    onCreateTrack: (input) => send<Track>({ type: "panel:createTrack", input }),
    onPatchTrack: (trackId, patch) => send<Track>({ type: "panel:patchTrack", trackId, patch }),
    onDeleteTrack: (trackId) => send<void>({ type: "panel:deleteTrack", trackId }),
    onAddDecisionPoint: (trackId, input) => send<DecisionPoint>({ type: "panel:addDecisionPoint", trackId, input }),
    onAddQuizSource: (url) => send<number>({ type: "panel:addQuizSource", url }),
    onImportExamResult: (payload) => send<ExamResult>({ type: "panel:importExamResult", payload }),
    onConfirmExamResult: (resultId, conceptIds) =>
      send<ExamResult>({ type: "panel:confirmExamResult", resultId, conceptIds }),
    onDismissExamResult: (resultId) => send<ExamResult>({ type: "panel:dismissExamResult", resultId }),
    onLoadIgnored: () => send<IgnoredConcept[]>({ type: "panel:ignored" }),
    onIgnoreConcept: (conceptId) => send<void>({ type: "panel:ignoreConcept", conceptId }),
    onUnignoreConcept: (conceptId) => send<void>({ type: "panel:unignoreConcept", conceptId }),
    ignoredList: ignoredClientHandlers(ignoredClient, refreshIgnored, backToSettings),
    trackDetail: {
      onBack: backFromTrack,
      onAddSource: () => openFromDetail("source-add"),
      onQuiz: () => openFromDetail("quiz"),
    },
    sourceAdd: {
      // Paste, file, page, course and the submit are not wired yet: the screen only routes here.
      onPasteText: () => {},
      onChooseFile: () => {},
      onUsePage: () => {},
      onUseCourse: () => {},
      onAddSource: () => {},
      onCancel: backToDetail,
    },
    quizRun: {
      // Next is not wired yet: the run shows no questions until the quiz loads.
      onNext: () => {},
      onFinish: backToDetail,
      onStop: backToDetail,
    },
    trackCreate: {
      // A refused save rejects: the form shows its error line and stays open. The core takes only a name and deadline.
      async onCreate(input) {
        await send<Track>({ type: "panel:createTrack", input: { name: input.name, deadline: input.deadline } });
        state.trackScreen = null;
        await loadTracks();
      },
      onCancel: backFromTrack,
    },
    onListConceptAliases: (conceptId) => send<ConceptAlias[]>({ type: "panel:listConceptAliases", conceptId }),
    onAddConceptAlias: (conceptId, alias) => send<ConceptAlias>({ type: "panel:addConceptAlias", conceptId, alias }),
    onMarkConceptViewed: (conceptId) => send<void>({ type: "panel:markConceptViewed", conceptId }),
    onRequestSummary: (url, text) => send<SummaryReply>({ type: "panel:requestSummary", url, text }),
    onCachedSummary: (url, textSha256) => send<string | null>({ type: "panel:cachedSummary", url, textSha256 }),
    onNextJoke: () => send<Joke | null>({ type: "panel:nextJoke" }),
    onListJokeSources: () => send<JokeSource[]>({ type: "panel:listJokeSources" }),
  };

  // The origin permission was removed (here or in the browser UI): fall back to first-run.
  api.permissions.onRemoved.addListener((removed) => {
    const pattern = originPattern(state.session);
    if (pattern === null || !removed.origins?.includes(pattern)) return;
    clearSession();
    draw();
  });

  draw();
}

/** HTTP statuses the core answers when the stored sign-in is missing or expired. */
const AUTH_STATUSES = [401, 403];

/** Error reason of a refused scan: timeout or auth when the reply says so, else failed. */
function scanErrorReason(reply: { status?: number; code?: string }): "timeout" | "auth" | "failed" {
  if (reply.code === "timeout") return "timeout";
  if (reply.status !== undefined && AUTH_STATUSES.includes(reply.status)) return "auth";
  return "failed";
}

/** Host pattern of a stored session's server, or null when there is no usable session. */
function originPattern(session: Session | null): string | null {
  if (session === null) return null;
  const parsed = validateServerUrl(session.baseUrl);
  return parsed.ok ? parsed.pattern : null;
}

/** Injects the panel stylesheet (panelCss.ts, the same tokens the card stylesheet uses) into `doc`. */
export function mountPanelStyle(doc: Document): HTMLStyleElement {
  const style = doc.createElement("style");
  style.textContent = PANEL_CSS;
  doc.head.append(style);
  return style;
}

// Side panel page entry: runs only where the extension runtime exists (not under tests).
if (typeof chrome !== "undefined" && chrome.runtime) {
  const root = document.getElementById("panel");
  if (root) {
    mountPanelStyle(document);
    void bootPanel(root, {
      runtime: { sendMessage: (message) => chrome.runtime.sendMessage<PanelMessage, PanelReply>(message) },
      storage: { local: chrome.storage.local },
      permissions: {
        request: (request) => chrome.permissions.request(request),
        remove: (request) => chrome.permissions.remove(request),
        onRemoved: chrome.permissions.onRemoved,
      },
    });
  }
}
