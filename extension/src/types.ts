import type { ScriptingLike } from "./bridgeRegister";
import type { PanelOpenApi } from "./browser";
import type { ContentMessage, RuntimeLike } from "./content";
import type { ModelhostEngine, ModelhostOutput } from "./coreClient";
import type { MarkOutcome } from "./offlineQueue";

/** A readable block of page text, optionally bound to its DOM element. */
export interface Block {
  id: string;
  text: string;
  el?: HTMLElement;
}

/** Connection to the local kata service. */
export interface Session {
  baseUrl: string;
  token: string;
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

/** User actions on the review screen. */
export interface ReviewHandlers {
  onSet(conceptId: number, state: ReviewState): Promise<void>;
}

/** One local model host action from the panel: start, measure, status, or choose the engine. */
export type ModelhostRequest =
  | { action: "start" | "measure" | "status" }
  | { action: "use"; engine: ModelhostEngine };

/** Finished output of a modelhost job, or "pending" when the PC worker has not answered in time. */
export type ModelhostResult = ModelhostOutput | "pending";

/** Values typed into the sign-in form: pairing code and device label. */
export interface SignInInput {
  code: string;
  deviceLabel: string;
}

/** Sign-in form values with the typed server URL. */
export interface ServerFormInput extends SignInInput {
  baseUrl: string;
}

/** Tabs of the signed-in panel. Lists is a section inside the Courses tab (design note D10). */
export type PanelTab = "scan" | "review" | "courses" | "tracks" | "settings";

/** User actions the panel reports back to the caller. */
export interface PanelHandlers {
  /** The user chose a tab. */
  onTab: (tab: PanelTab) => void | Promise<void>;
  onSignIn: (input: ServerFormInput) => void | Promise<void>;
  onDisconnect: () => void | Promise<void>;
  onChangeServer: () => void;
  onCancelChange: () => void;
  onKnown: (topicId: number) => Promise<MarkOutcome>;
  onScan: () => Promise<void>;
  onReview: () => Promise<void>;
  onSetConcept: (conceptId: number, state: ReviewState) => Promise<void>;
  onCloseReview: () => void;
  onOpenCourse: (courseId: number) => Promise<void>;
  onDeleteCourse: (courseId: number) => Promise<void>;
  onCreateCourse: (title: string) => Promise<void>;
  onRegenerateCourse: (courseId: number) => Promise<void>;
  onModelhost: (request: ModelhostRequest) => Promise<ModelhostResult>;
  /** Retry now on the connection detail and the queue screen; the button is hidden without it. */
  onRetry?: () => Promise<void>;
  /** Show unsynced marks on the connection detail; the button is hidden without it. */
  onShowQueue?: () => void;
  /** Back on the Not synced marks screen; the button is hidden without it. */
  onCloseQueue?: () => void;
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
