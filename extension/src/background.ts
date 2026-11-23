import type { ContentMessage, RuntimeLike, ScanResponse } from "./content";
import type { BridgeMessage } from "./bridge";
import { originOf, syncBridge, wireBridgeRegistration, type ScriptingLike } from "./bridgeRegister";
import { openPanel, type PanelOpenApi } from "./browser";
import { MAX_WAIT_MS, POLL_MS, REQUEST_TIMEOUT_MS } from "./config";
import { CoreAuthError, CoreClient, type ConceptMark, type ProgressDoc } from "./coreClient";
import { OfflineQueue, type FlushResult, type MarkOutcome } from "./offlineQueue";
import { createProgressBridge, type ProgressBridge } from "./progressBridge";
import { runScan, type ScanResult } from "./scanSession";
import type { SignInInput } from "./sidepanel";
import { validateServerUrl } from "./serverUrl";
import { TokenStore, type StorageArea } from "./tokenStore";
import type { Session } from "./types";

/** The part of `chrome` the background script uses; tests pass a fake with these members. */
export interface ChromeLike extends PanelOpenApi {
  action: {
    onClicked: { addListener(listener: (tab: { windowId?: number }) => void): void };
  };
  tabs: {
    query(query: { active: boolean; currentWindow: boolean }): Promise<{ id?: number }[]>;
    sendMessage(tabId: number, message: ContentMessage): Promise<unknown>;
    create(properties: { url: string }): Promise<unknown>;
  };
  runtime: RuntimeLike;
  scripting: ScriptingLike;
}

/**
 * Sign-in values from the panel: the enrolment code, the device label and the typed server URL.
 * The URL is optional in the type until the side panel sends it; an absent URL is refused as empty.
 */
export interface ServerSignIn extends SignInInput {
  baseUrl?: string;
}

/** Messages the side panel page sends to the background script. */
export type PanelMessage =
  | { type: "panel:signIn"; input: ServerSignIn }
  | { type: "panel:disconnect" }
  | { type: "panel:scan" }
  | { type: "panel:known"; topicId: number }
  | { type: "panel:review" }
  | { type: "panel:setConcept"; conceptId: number; state: ConceptMark["state"] }
  | { type: "panel:courses" }
  | { type: "panel:openCourse"; courseId: number };

/** Reply to a panel message: the result, or the error text. */
export type PanelReply = { ok: true; data?: unknown } | { ok: false; error: string };

/** A ready course the panel can open: its id and title only. */
export interface CourseLink {
  id: number;
  title: string;
}

/** One concept on the review screen; `state` is null when the core abstains and no mark exists. */
export interface ReviewRow {
  conceptId: number;
  label: string;
  state: ConceptMark["state"] | null;
  evidence: string;
}

/** Business logic behind the side panel; each call talks to the core. */
export interface Backend {
  /** Checks the server, redeems the code and saves the session; the bridge follows the new origin. */
  signIn(input: ServerSignIn): Promise<void>;
  /** Clears the session and the bridge; the offline mark queue is kept. */
  disconnect(): Promise<void>;
  scan(): Promise<ScanResult[]>;
  markKnown(topicId: number): Promise<MarkOutcome>;
  flush(): Promise<FlushResult | null>;
  review(): Promise<ReviewRow[]>;
  setConcept(conceptId: number, state: ConceptMark["state"]): Promise<void>;
  /** The caller's ready courses, id and title only. */
  courses(): Promise<CourseLink[]>;
  /** Opens a ready course in a new tab; the URL must stay on the core origin. */
  openCourse(courseId: number): Promise<void>;
  /** Whole-document progress load and save for the course pages (see bridge.ts). */
  progress: ProgressBridge;
}

/** Builds the backend over the chrome tabs API and the extension storage area. */
export function createBackend(api: ChromeLike, area: StorageArea, fetchImpl?: typeof fetch): Backend {
  const tokens = new TokenStore(area);
  const clientAt = (baseUrl: string, token?: string): CoreClient =>
    new CoreClient({ baseUrl, token, timeoutMs: REQUEST_TIMEOUT_MS, fetchImpl });
  const clientFor = (session: Session): CoreClient => clientAt(session.baseUrl, session.token);
  const requireSession = async (): Promise<Session> => {
    const session = await tokens.loadSession();
    if (!session) throw new CoreAuthError("not signed in");
    return session;
  };

  return {
    progress: createProgressBridge(clientFor, tokens),

    async signIn(input) {
      const server = validateServerUrl(input.baseUrl ?? "");
      if (!server.ok) throw new Error(server.reason);
      // Probe first: an unreachable address or a non-kata server fails with its own error text.
      const client = clientAt(server.baseUrl);
      await client.probe();
      // The code is redeemed here and never stored; only the resulting token is saved.
      const token = await client.enrol(input.code, input.deviceLabel);
      await tokens.saveSession({ baseUrl: server.baseUrl, token });
      await syncBridge(api.scripting, tokens);
    },

    async disconnect() {
      await tokens.clearSession();
      await syncBridge(api.scripting, tokens);
    },

    async scan() {
      const session = await requireSession();
      const [tab] = await api.tabs.query({ active: true, currentWindow: true });
      if (tab?.id === undefined) throw new Error("no active tab");
      const page = (await api.tabs.sendMessage(tab.id, { type: "scan" })) as ScanResponse;
      if (!page?.blocks) throw new Error("page gave no blocks");
      return runScan(clientFor(session), page.blocks, { pollMs: POLL_MS, maxWaitMs: MAX_WAIT_MS });
    },

    async markKnown(topicId) {
      const session = await requireSession();
      return new OfflineQueue(area, clientFor(session)).markKnown(topicId);
    },

    async flush() {
      const session = await tokens.loadSession();
      if (!session) return null;
      return new OfflineQueue(area, clientFor(session)).flush();
    },

    async review() {
      const session = await requireSession();
      const client = clientFor(session);
      const marks = await client.listConceptMarks();
      if (marks.length === 0) return [];
      const checks = await client.lessonCheck(marks.map((mark) => mark.concept_id));
      const markById = new Map(marks.map((mark) => [mark.concept_id, mark]));
      return checks.map((check): ReviewRow => {
        const mark = markById.get(check.concept_id);
        // A stored mark wins; with no mark, an abstaining check leaves the state null.
        let state: ReviewRow["state"] = null;
        if (mark) state = mark.state;
        else if (check.state !== "abstain") state = check.state;
        return {
          conceptId: check.concept_id,
          label: mark?.label ?? check.label,
          state,
          evidence: mark?.evidence ?? check.evidence,
        };
      });
    },

    async setConcept(conceptId, state) {
      const session = await requireSession();
      await clientFor(session).setConceptMark(conceptId, state);
    },

    async courses() {
      const session = await requireSession();
      const courses = await clientFor(session).listCourses();
      return courses.map((course) => ({ id: course.id, title: course.title }));
    },

    async openCourse(courseId) {
      const session = await requireSession();
      const client = clientFor(session);
      if (!(await client.listCourses()).some((course) => course.id === courseId)) {
        throw new Error("course is not ready");
      }
      const url = await client.openCourse(courseId);
      if (!isCoreUrl(url, session.baseUrl)) throw new Error("course link is outside the core");
      await api.tabs.create({ url });
    },
  };
}

/** True when `url` parses and has the origin (scheme, host, port) of the session's base URL; else refused. */
function isCoreUrl(url: string, baseUrl: string): boolean {
  try {
    return new URL(url).origin === originOf(baseUrl);
  } catch {
    return false;
  }
}

/**
 * Routes one content-bridge message to the progress service. Its reply is the document or
 * the short error text only; the session token never leaves this service.
 */
async function handleBridgeMessage(progress: ProgressBridge, message: BridgeMessage): Promise<PanelReply> {
  if (!Number.isInteger(message.courseId) || message.courseId < 1) throw new Error("bad course id");
  if (message.type === "bridge:load") return { ok: true, data: await progress.load(message.courseId) };
  if (typeof message.doc !== "object" || message.doc === null) throw new Error("bad progress document");
  return { ok: true, data: await progress.save(message.courseId, message.doc as ProgressDoc) };
}

/** Routes one panel message to the backend and returns its reply. */
async function handlePanelMessage(backend: Backend, message: PanelMessage): Promise<PanelReply> {
  switch (message.type) {
    case "panel:signIn":
      await backend.signIn(message.input);
      return { ok: true };
    case "panel:disconnect":
      await backend.disconnect();
      return { ok: true };
    case "panel:scan":
      return { ok: true, data: await backend.scan() };
    case "panel:known":
      return { ok: true, data: await backend.markKnown(message.topicId) };
    case "panel:review":
      return { ok: true, data: await backend.review() };
    case "panel:setConcept":
      await backend.setConcept(message.conceptId, message.state);
      return { ok: true };
    case "panel:courses":
      return { ok: true, data: await backend.courses() };
    case "panel:openCourse":
      await backend.openCourse(message.courseId);
      return { ok: true };
  }
}

/** True when `message` has one of the panel message shapes. */
function isPanelMessage(message: unknown): message is PanelMessage {
  if (typeof message !== "object" || message === null) return false;
  const type = (message as { type?: unknown }).type;
  return (
    type === "panel:signIn" ||
    type === "panel:disconnect" ||
    type === "panel:scan" ||
    type === "panel:known" ||
    type === "panel:review" ||
    type === "panel:setConcept" ||
    type === "panel:courses" ||
    type === "panel:openCourse"
  );
}

/** True when `message` is one of the content-bridge message shapes. */
function isBridgeMessage(message: unknown): message is BridgeMessage {
  if (typeof message !== "object" || message === null) return false;
  const type = (message as { type?: unknown }).type;
  return type === "bridge:load" || type === "bridge:save";
}

/**
 * Registers the background listeners: the toolbar button opens the side panel and
 * flushes the offline mark queue; panel messages go to the backend; bridge messages
 * from the course pages go to the progress service.
 */
export function wireBackground(api: ChromeLike, backend: Backend): void {
  api.action.onClicked.addListener((tab) => {
    if (tab.windowId === undefined) return;
    openPanel(api, tab.windowId).catch((err: unknown) => console.error(err));
    // A failed flush stays queued; the next panel open retries it.
    backend.flush().catch(() => undefined);
  });

  api.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    const route = isPanelMessage(message)
      ? handlePanelMessage(backend, message)
      : isBridgeMessage(message)
        ? handleBridgeMessage(backend.progress, message)
        : undefined;
    if (route === undefined) return false;
    route.then(
      (reply) => sendResponse(reply),
      (err: unknown) => sendResponse({ ok: false, error: err instanceof Error ? err.message : String(err) }),
    );
    return true;
  });
}

// Service worker entry: runs only where the extension runtime exists (not under tests).
if (typeof chrome !== "undefined" && chrome.action) {
  wireBackground(chrome, createBackend(chrome, chrome.storage.local));
  wireBridgeRegistration(chrome.runtime, chrome.scripting, chrome.permissions, new TokenStore(chrome.storage.local));
}
