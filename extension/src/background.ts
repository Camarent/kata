import type { ContentMessage, PageMutatedMessage, RuntimeLike, ScanResponse } from "./content";
import type { BridgeMessage } from "./bridge";
import { originOf, syncBridge, wireBridgeRegistration, type ScriptingLike } from "./bridgeRegister";
import { openPanel, type PanelOpenApi } from "./browser";
import { MAX_WAIT_MS, POLL_MS, REQUEST_TIMEOUT_MS } from "./config";
import {
  CoreAuthError,
  CoreClient,
  CoreHttpError,
  type ConceptMark,
  type ModelhostEngine,
  type ModelhostOutput,
  type ProgressDoc,
  type TopicOverview,
} from "./coreClient";
import type { ConceptScanError, ConceptScanResult } from "./conceptScan";
import { createConceptScanner, pageKeyOf } from "./backgroundRescan";
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
    query(query: { active: boolean; currentWindow: boolean }): Promise<{ id?: number; url?: string }[]>;
    sendMessage(tabId: number, message: ContentMessage): Promise<unknown>;
    create(properties: { url: string }): Promise<unknown>;
    onUpdated: { addListener(listener: (tabId: number, changes: { url?: string }) => void): void };
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
  | { type: "panel:scanConcepts" }
  | { type: "panel:chooseConcept"; topicId: number; word: string; conceptId: number }
  | { type: "panel:reassignConcept"; topicId: number; word: string; fromConceptId: number; toConceptId: number }
  | { type: "panel:topicOverview"; topicId: number }
  | { type: "panel:known"; topicId: number }
  | { type: "panel:review" }
  | { type: "panel:setConcept"; conceptId: number; state: ConceptMark["state"] }
  | { type: "panel:pending" }
  | { type: "panel:courses" }
  | { type: "panel:openCourse"; courseId: number }
  | { type: "panel:deleteCourse"; courseId: number }
  | { type: "panel:createCourse"; title: string }
  | { type: "panel:modelhost"; request: ModelhostRequest };
/** One local model host action from the panel: start, measure, status, or choose the engine. */
export type ModelhostRequest =
  | { action: "start" | "measure" | "status" }
  | { action: "use"; engine: ModelhostEngine };
/** Finished output of a modelhost job, or "pending" when the PC worker has not answered in time. */
export type ModelhostResult = ModelhostOutput | "pending";

/** Reply to a panel message: the result, or the error text. */
/** A refused panel message; `status` and `code` are set when the core refused it (CoreHttpError). */
export type PanelReply = { ok: true; data?: unknown } | { ok: false; error: string; status?: number; code?: string };

/** A ready course the panel can open: its id and title only. */
export interface CourseLink {
  id: number;
  title: string;
}

/** The Courses list: the ready courses, the course limit and the count against it. */
export interface CourseList {
  items: CourseLink[];
  limit: number;
  total: number;
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
  /** Concept scan of the active page; starts the rescan of that page when it succeeds. */
  scanConcepts(): Promise<ConceptScanResult | ConceptScanError>;
  /** Remembers the concept the caller picked for a written word in a topic. */
  chooseConcept(topicId: number, word: string, conceptId: number): Promise<void>;
  /** Moves a written word from one concept to another and teaches the alias. */
  reassignConcept(topicId: number, word: string, fromConceptId: number, toConceptId: number): Promise<void>;
  /** Concept counts and concept list of one topic. */
  topicOverview(topicId: number): Promise<TopicOverview>;
  /** A watched page changed in the DOM: restarts the rescan debounce for that tab. */
  pageMutated(tabId: number): void;
  /** A tab navigated: the rescan of that tab stops. */
  tabNavigated(tabId: number): void;
  markKnown(topicId: number): Promise<MarkOutcome>;
  flush(): Promise<FlushResult | null>;
  review(): Promise<ReviewRow[]>;
  /** Sets one concept mark; offline it is queued (see OfflineQueue), not an error. */
  setConcept(conceptId: number, state: ConceptMark["state"]): Promise<void>;
  /** Marks waiting in the offline queue; the panel shows them in its connection indicator. */
  pendingCount(): Promise<number>;
  /** The caller's ready courses (id and title only) with the course limit and total count. */
  courses(): Promise<CourseList>;
  /** Opens a ready course in a new tab; the URL must stay on the core origin. */
  openCourse(courseId: number): Promise<void>;
  /** Deletes a course; a course already gone (404) counts as deleted. */
  deleteCourse(courseId: number): Promise<void>;
  /** Queues a new course with the given title; a refusal from the core rejects with CoreHttpError. */
  createCourse(title: string): Promise<void>;
  /** Queues a modelhost job and waits up to MAX_WAIT_MS; "pending" when the worker has not answered by then. */
  modelhost(request: ModelhostRequest): Promise<ModelhostResult>;
  /** Whole-document progress load and save for the course pages (see bridge.ts). */
  progress: ProgressBridge;
}

/** Queues the modelhost job for each action that takes no payload. */
const MODELHOST_QUEUE: Record<"start" | "measure" | "status", (client: CoreClient) => Promise<number>> = {
  start: (client) => client.modelhostUp(),
  measure: (client) => client.modelhostMeasure(),
  status: (client) => client.modelhostStatus(),
};

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

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

  const scanner = createConceptScanner({ api, tokens, clientFor, pollMs: POLL_MS, maxWaitMs: MAX_WAIT_MS });

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
      scanner.stopRescan();
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

    async scanConcepts() {
      const session = await requireSession();
      // A new scan replaces the rescan of the page before it.
      scanner.stopRescan();
      const [tab] = await api.tabs.query({ active: true, currentWindow: true });
      if (tab?.id === undefined) throw new Error("no active tab");
      if (tab.url === undefined) throw new Error("page has no URL");
      const pageKey = pageKeyOf(tab.url);
      const result = await scanner.scanPage(session, tab.id, pageKey);
      if (!("error" in result)) scanner.startRescan(tab.id, pageKey, result);
      return result;
    },

    async chooseConcept(topicId, word, conceptId) {
      const session = await requireSession();
      await clientFor(session).chooseConcept(topicId, word, conceptId);
    },

    async reassignConcept(topicId, word, fromConceptId, toConceptId) {
      const session = await requireSession();
      await clientFor(session).reassignConcept(topicId, word, fromConceptId, toConceptId);
    },

    async topicOverview(topicId) {
      const session = await requireSession();
      return clientFor(session).topicOverview(topicId);
    },

    pageMutated(tabId) {
      scanner.pageMutated(tabId);
    },

    tabNavigated(tabId) {
      scanner.tabNavigated(tabId);
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
      await new OfflineQueue(area, clientFor(session)).markConcept(conceptId, state);
    },

    async pendingCount() {
      const session = await tokens.loadSession();
      if (!session) return 0;
      return new OfflineQueue(area, clientFor(session)).count();
    },

    async courses() {
      const session = await requireSession();
      const list = await clientFor(session).listCoursesMeta();
      return {
        items: list.items.map((course) => ({ id: course.id, title: course.title })),
        limit: list.limit,
        total: list.total,
      };
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

    async deleteCourse(courseId) {
      const session = await requireSession();
      // deleteCourse resolves false on 404: the course is already gone, which is the state asked for.
      await clientFor(session).deleteCourse(courseId);
    },

    async createCourse(title) {
      const session = await requireSession();
      await clientFor(session).createCourse(title);
    },

    async modelhost(request) {
      const session = await requireSession();
      const client = clientFor(session);
      const id =
        request.action === "use"
          ? await client.modelhostUse(request.engine)
          : await MODELHOST_QUEUE[request.action](client);
      const deadline = Date.now() + MAX_WAIT_MS;
      for (;;) {
        const result = await client.modelhostResult(id);
        if (result !== "pending" || Date.now() >= deadline) return result;
        await sleep(POLL_MS);
      }
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
    case "panel:scanConcepts":
      return { ok: true, data: await backend.scanConcepts() };
    case "panel:chooseConcept":
      await backend.chooseConcept(message.topicId, message.word, message.conceptId);
      return { ok: true };
    case "panel:reassignConcept":
      await backend.reassignConcept(message.topicId, message.word, message.fromConceptId, message.toConceptId);
      return { ok: true };
    case "panel:topicOverview":
      return { ok: true, data: await backend.topicOverview(message.topicId) };
    case "panel:known":
      return { ok: true, data: await backend.markKnown(message.topicId) };
    case "panel:review":
      return { ok: true, data: await backend.review() };
    case "panel:setConcept":
      await backend.setConcept(message.conceptId, message.state);
      return { ok: true };
    case "panel:pending":
      return { ok: true, data: await backend.pendingCount() };
    case "panel:courses":
      return { ok: true, data: await backend.courses() };
    case "panel:openCourse":
      await backend.openCourse(message.courseId);
      return { ok: true };
    case "panel:deleteCourse":
      await backend.deleteCourse(message.courseId);
      return { ok: true };
    case "panel:createCourse":
      try {
        await backend.createCourse(message.title);
        return { ok: true };
      } catch (err) {
        if (err instanceof CoreHttpError) return { ok: false, error: err.message, status: err.status, code: err.code };
        throw err;
      }
    case "panel:modelhost":
      return { ok: true, data: await backend.modelhost(message.request) };
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
    type === "panel:scanConcepts" ||
    type === "panel:chooseConcept" ||
    type === "panel:reassignConcept" ||
    type === "panel:topicOverview" ||
    type === "panel:known" ||
    type === "panel:review" ||
    type === "panel:setConcept" ||
    type === "panel:pending" ||
    type === "panel:courses" ||
    type === "panel:openCourse" ||
    type === "panel:deleteCourse" ||
    type === "panel:createCourse" ||
    type === "panel:modelhost"
  );
}

/** True when `message` is the content script's report of a DOM change on a watched page. */
function isPageMutatedMessage(message: unknown): message is PageMutatedMessage {
  return typeof message === "object" && message !== null && (message as { type?: unknown }).type === "page:mutated";
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

  api.tabs.onUpdated.addListener((tabId, changes) => {
    if (changes.url !== undefined) backend.tabNavigated(tabId);
  });

  api.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (isPageMutatedMessage(message)) {
      const tabId = (sender as { tab?: { id?: number } }).tab?.id;
      if (tabId !== undefined) backend.pageMutated(tabId);
      return false;
    }
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
