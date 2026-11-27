import type { ModelhostRequest, ModelhostResult, ReviewState } from "./messages";
import type {
  ConceptAlias,
  DecisionPoint,
  ExamResult,
  IgnoredConcept,
  Joke,
  JokeSource,
  PointIn,
  SummaryReply,
  Track,
  TrackIn,
  TrackPage,
  TrackPatch,
} from "./coreClientTypes";
import type { MarkOutcome } from "./offlineQueue";
import type { IgnoredListHandlers } from "./ui/panel/ignoredList";
import type { SettingsPage } from "./ui/panel/settingsHome";
import type { TrackSortKey } from "./ui/panel/tracksTab";
import type { TrackDetailHandlers } from "./ui/panel/trackDetail";
import type { TrackCreateHandlers } from "./ui/panel/trackCreate";

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

/** User actions on the review screen. */
export interface ReviewHandlers {
  onSet(conceptId: number, state: ReviewState): Promise<void>;
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
  /** Tracks, exam results and ignored concepts: each sends one panel message and returns the reply data. */
  onLoadTracks?: (opts?: { limit?: number; beforeId?: number }) => Promise<TrackPage>;
  onGetTrack?: (trackId: number) => Promise<Track>;
  onCreateTrack?: (input: TrackIn) => Promise<Track>;
  onPatchTrack?: (trackId: number, patch: TrackPatch) => Promise<Track>;
  onDeleteTrack?: (trackId: number) => Promise<void>;
  onAddDecisionPoint?: (trackId: number, input: PointIn) => Promise<DecisionPoint>;
  onAddQuizSource?: (url: string) => Promise<number>;
  onImportExamResult?: (payload: string) => Promise<ExamResult>;
  onConfirmExamResult?: (resultId: number, conceptIds: number[]) => Promise<ExamResult>;
  onDismissExamResult?: (resultId: number) => Promise<ExamResult>;
  onLoadIgnored?: () => Promise<IgnoredConcept[]>;
  onIgnoreConcept?: (conceptId: number) => Promise<void>;
  onUnignoreConcept?: (conceptId: number) => Promise<void>;
  /** Restore and Undo of the ignored list; each calls the panel messages for ignore and unignore. */
  ignoredList?: IgnoredListHandlers;
  /** Track detail screen: back, add source and quiz; the panel draws it when the Tracks tab opened a track. */
  trackDetail?: TrackDetailHandlers;
  /** Create-track form: save and cancel; the panel draws it when the Tracks tab chose New track. */
  trackCreate?: TrackCreateHandlers;
  /** Tracks tab: the user changed the sort key; the panel re-sorts the rows it holds. */
  onSortTracks?: (sort: TrackSortKey) => void;
  /** Tracks tab: the user opened one track; the panel draws its detail screen when it has one. */
  onOpenTrack?: (trackId: number) => void;
  /** Tracks tab: the user chose New track; the panel draws the create screen when it has one. */
  onNewTrack?: () => void;
  /** Settings home: the user opened one settings page; the panel draws it when it has a screen for it. */
  onOpenSettingsPage?: (page: SettingsPage) => void | Promise<void>;
  /** Feed tabs: aliases, page summary, jokes and concept views; each sends one panel message. */
  onListConceptAliases?: (conceptId: number) => Promise<ConceptAlias[]>;
  onAddConceptAlias?: (conceptId: number, alias: string) => Promise<ConceptAlias>;
  onMarkConceptViewed?: (conceptId: number) => Promise<void>;
  onRequestSummary?: (url: string, text: string) => Promise<SummaryReply>;
  onCachedSummary?: (url: string, textSha256: string) => Promise<string | null>;
  onNextJoke?: () => Promise<Joke | null>;
  onListJokeSources?: () => Promise<JokeSource[]>;
}
