import { originOf, syncBridge } from "./bridgeRegister";
import { MAX_WAIT_MS, POLL_MS, REQUEST_TIMEOUT_MS } from "./config";
import { CoreAuthError, CoreClient, type ConceptMark, type TopicOverview } from "./coreClient";
import * as trackApi from "./coreClientTracks";
import type { DecisionPoint, ExamResult, ConceptAlias, IgnoredConcept, Joke, JokeSource, PointIn, SummaryReply, Track, TrackIn, TrackPage, TrackPatch } from "./coreClientTypes";
import type { ConceptScanError, ConceptScanResult } from "./conceptScan";
import { createConceptScanner, pageKeyOf } from "./backgroundRescan";
import { OfflineQueue, type FlushResult, type MarkOutcome } from "./offlineQueue";
import { createProgressBridge, type ProgressBridge } from "./progressBridge";
import { runScan, type ScanResult } from "./scanSession";
import type { ChromeLike, ScanResponse } from "./messages";
import { validateServerUrl } from "./serverUrl";
import { TokenStore, type StorageArea } from "./tokenStore";
import type { ModelhostRequest, ModelhostResult, SignInInput, Session } from "./types";

/**
 * Sign-in values from the panel: the enrolment code, the device label and the typed server URL.
 * The URL is optional in the type until the side panel sends it; an absent URL is refused as empty.
 */
export interface ServerSignIn extends SignInInput {
  baseUrl?: string;
}

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
  /** Area of the page scan the concept came from; absent for concepts not on the scanned page. */
  area?: string;
  /** True when the concept is on the last scanned page ("Only this page"). */
  onPage?: boolean;
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
  regenerateCourse(courseId: number): Promise<void>;
  /** One page of the caller's tracks, newest first; `beforeId` asks for the page before that track. */
  tracks(opts: { limit?: number; beforeId?: number }): Promise<TrackPage>;
  getTrack(trackId: number): Promise<Track>;
  createTrack(input: TrackIn): Promise<Track>;
  patchTrack(trackId: number, patch: TrackPatch): Promise<Track>;
  deleteTrack(trackId: number): Promise<void>;
  addDecisionPoint(trackId: number, input: PointIn): Promise<DecisionPoint>;
  /** Queues a quiz source from a URL; returns the job id. */
  addQuizSource(url: string): Promise<number>;
  /** Stores an exam result JSON as pending; changes no mark. */
  importExamResult(payload: string): Promise<ExamResult>;
  confirmExamResult(resultId: number, conceptIds: number[]): Promise<ExamResult>;
  dismissExamResult(resultId: number): Promise<ExamResult>;
  /** Concepts the caller ignores, for the ignored list. */
  ignored(): Promise<IgnoredConcept[]>;
  ignoreConcept(conceptId: number): Promise<void>;
  unignoreConcept(conceptId: number): Promise<void>;
  /** Stamps the last-viewed time of a concept. */
  markConceptViewed(conceptId: number): Promise<void>;
  /** Shared and own aliases of a concept. */
  listConceptAliases(conceptId: number): Promise<ConceptAlias[]>;
  /** Adds a private alias to a concept; refuses an alias that exists. */
  addConceptAlias(conceptId: number, alias: string): Promise<ConceptAlias>;
  /** Summary of a page: the cached one or a queued job id. */
  requestSummary(url: string, text: string): Promise<SummaryReply>;
  /** The cached summary of a page text, or null when none is cached. */
  cachedSummary(url: string, textSha256: string): Promise<string | null>;
  /** The next cached joke, or null when jokes are off or none is cached. */
  nextJoke(): Promise<Joke | null>;
  /** The enabled joke sources, in list order. */
  listJokeSources(): Promise<JokeSource[]>;
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
      if (!("error" in result)) {
        scanner.startRescan(tab.id, pageKey, result);
      }
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
      const pageIds = new Set<number>();
      // The watched page (last scan merged with rescans) counts only while the active tab still shows it.
      // Limit: areas come from that scan only; off-page concepts fall in "Other concepts" because
      // the core review tree carries no concept ids per area.
      const [tab] = await api.tabs.query({ active: true, currentWindow: true });
      const watched = scanner.current();
      const scan = tab?.url !== undefined && watched?.pageKey === pageKeyOf(tab.url) ? watched.result : null;
      for (const block of scan?.blocks ?? []) {
        for (const item of block.concepts) if (item.conceptId !== null) pageIds.add(item.conceptId);
      }
      return checks.map((check): ReviewRow => {
        const mark = markById.get(check.concept_id);
        const onPage = pageIds.has(check.concept_id);
        // A stored mark wins; with no mark, an abstaining check leaves the state null.
        let state: ReviewRow["state"] = null;
        if (mark) state = mark.state;
        else if (check.state !== "abstain") state = check.state;
        return {
          conceptId: check.concept_id,
          label: mark?.label ?? check.label,
          state,
          evidence: mark?.evidence ?? check.evidence,
          area: onPage && scan ? scan.area : undefined,
          onPage,
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

    async regenerateCourse(courseId) {
      const session = await requireSession();
      await clientFor(session).regenerateCourse(courseId);
    },

    async tracks(opts) {
      return trackApi.listTracks(clientFor(await requireSession()), opts);
    },

    async getTrack(trackId) {
      return trackApi.getTrack(clientFor(await requireSession()), trackId);
    },

    async createTrack(input) {
      return trackApi.createTrack(clientFor(await requireSession()), input);
    },

    async patchTrack(trackId, patch) {
      return trackApi.patchTrack(clientFor(await requireSession()), trackId, patch);
    },

    async deleteTrack(trackId) {
      await trackApi.deleteTrack(clientFor(await requireSession()), trackId);
    },

    async addDecisionPoint(trackId, input) {
      return trackApi.addDecisionPoint(clientFor(await requireSession()), trackId, input);
    },

    async addQuizSource(url) {
      return trackApi.addQuizSource(clientFor(await requireSession()), url);
    },

    async importExamResult(payload) {
      return trackApi.importExamResult(clientFor(await requireSession()), payload);
    },

    async confirmExamResult(resultId, conceptIds) {
      return trackApi.confirmExamResult(clientFor(await requireSession()), resultId, conceptIds);
    },

    async dismissExamResult(resultId) {
      return trackApi.dismissExamResult(clientFor(await requireSession()), resultId);
    },

    async ignored() {
      return clientFor(await requireSession()).listIgnored();
    },

    async ignoreConcept(conceptId) {
      await clientFor(await requireSession()).ignoreConcept(conceptId);
    },

    async unignoreConcept(conceptId) {
      await clientFor(await requireSession()).unignoreConcept(conceptId);
    },

    async markConceptViewed(conceptId) {
      await clientFor(await requireSession()).markConceptViewed(conceptId);
    },

    async listConceptAliases(conceptId) {
      return clientFor(await requireSession()).listConceptAliases(conceptId);
    },

    async addConceptAlias(conceptId, alias) {
      return clientFor(await requireSession()).addConceptAlias(conceptId, alias);
    },

    async requestSummary(url, text) {
      return clientFor(await requireSession()).requestSummary(url, text);
    },

    async cachedSummary(url, textSha256) {
      return clientFor(await requireSession()).cachedSummary(url, textSha256);
    },

    async nextJoke() {
      return clientFor(await requireSession()).nextJoke();
    },

    async listJokeSources() {
      return clientFor(await requireSession()).listJokeSources();
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
