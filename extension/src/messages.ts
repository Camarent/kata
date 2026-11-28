import type { PanelOpenApi } from "./browser";
import type { ScriptingLike } from "./bridgeRegister";
import type { HighlightResult } from "./highlight";
import type { ServerSignIn } from "./backgroundBackend";
import type { ModelhostEngine, ModelhostOutput } from "./coreClient";
import type { ConceptMark, PointIn, TrackIn, TrackPatch } from "./coreClientTypes";

/** Message the side panel sends to the page through the background script. */
export type ContentMessage =
  | { type: "scan" }
  | { type: "highlight"; results: HighlightResult[] }
  | { type: "clear" }
  | { type: "watch" }
  | { type: "unwatch" };

/** Sent by the page to the background script after a DOM change while watched. */
export interface PageMutatedMessage {
  type: "page:mutated";
}

/** Answer to `scan`: the page blocks, id and text only (no DOM references). */
export interface ScanResponse {
  blocks: { id: string; text: string }[];
}

/** Minimal shape of the `chrome.runtime` messaging API used here. */
export interface RuntimeLike {
  onMessage: {
    addListener(listener: (message: unknown, sender: unknown, sendResponse: (response: unknown) => void) => boolean | void): void;
  };
  sendMessage(message: PageMutatedMessage | PanelMessage): Promise<unknown>;
}

/** Reply to a panel message: the result, or the error text; `status` and `code` are set when the core refused it (CoreHttpError). */
export type PanelReply = { ok: true; data?: unknown } | { ok: false; error: string; status?: number; code?: string };

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

/** Review state of one concept: known, learning or new. */
export type ReviewState = "known" | "learning" | "new";

/** One concept on the review screen; `state` is null when the core abstains and no mark exists. */
export interface ReviewRow {
  conceptId: number;
  label: string;
  state: ReviewState | null;
  evidence: string;
  /** Area the concept belongs to; rows without one go to a shared group. */
  area?: string;
  /** True when the concept is on the scanned page ("Only this page"). */
  onPage?: boolean;
}

/** A ready course the panel can open: its id, title and version. */
export interface CourseLink {
  id: number;
  title: string;
  version: number;
}

/** The Courses list: the ready courses, the course limit and the count against it. */
export interface CourseList {
  items: CourseLink[];
  limit: number;
  total: number;
}

/** One local model host action from the panel: start, measure, status, or choose the engine. */
export type ModelhostRequest =
  | { action: "start" | "measure" | "status" }
  | { action: "use"; engine: ModelhostEngine };

/** Finished output of a modelhost job, or "pending" when the PC worker has not answered in time. */
export type ModelhostResult = ModelhostOutput | "pending";

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
  | { type: "panel:regenerateCourse"; courseId: number }
  | { type: "panel:modelhost"; request: ModelhostRequest }
  | { type: "panel:tracks"; limit?: number; beforeId?: number }
  | { type: "panel:getTrack"; trackId: number }
  | { type: "panel:createTrack"; input: TrackIn }
  | { type: "panel:patchTrack"; trackId: number; patch: TrackPatch }
  | { type: "panel:deleteTrack"; trackId: number }
  | { type: "panel:addDecisionPoint"; trackId: number; input: PointIn }
  | { type: "panel:addQuizSource"; url: string }
  | { type: "panel:importExamResult"; payload: string }
  | { type: "panel:confirmExamResult"; resultId: number; conceptIds: number[] }
  | { type: "panel:dismissExamResult"; resultId: number }
  | { type: "panel:ignored" }
  | { type: "panel:ignoreConcept"; conceptId: number }
  | { type: "panel:unignoreConcept"; conceptId: number }
  | { type: "panel:markConceptViewed"; conceptId: number }
  | { type: "panel:listConceptAliases"; conceptId: number }
  | { type: "panel:addConceptAlias"; conceptId: number; alias: string }
  | { type: "panel:requestSummary"; url: string; text: string }
  | { type: "panel:cachedSummary"; url: string; textSha256: string }
  | { type: "panel:nextJoke" }
  | { type: "panel:listJokeSources" };
