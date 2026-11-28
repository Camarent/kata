/**
 * Registry of every panel tab and settings page screen in the screen inventory. Each entry
 * draws one screen from its props and its actions (ctx); the props and ctx types come from the
 * render function itself, so a render signature change reaches this file at compile time.
 */
import type { ReviewRow } from "../../messages";
import type { ReviewHandlers } from "../../types";
import { renderReview } from "./review";
import { renderConnectionDetail } from "./connection";
import { renderSignIn, renderSignedOut } from "./signin";
import { renderOfflineQueue } from "./offlineQueue";
import { renderScanResults } from "./scanResults";
import { renderSummaryPanel } from "./summaryPanel";
import { renderCourseDetail, renderCourseRegenerate } from "./courseDetail";
import { renderCourseGenerate } from "./courseGenerate";
import { renderCoursesTab } from "./coursesTab";
import { renderExamEntry } from "./examEntry";
import { renderExamProposals } from "./examProposals";
import { renderExamResult } from "./examResult";
import { renderIgnoredList } from "./ignoredList";
import { renderListDelete } from "./listDelete";
import { renderListDetail } from "./listDetail";
import { renderListEdit } from "./listEdit";
import { renderQuizEnd } from "./quizEnd";
import { renderQuizRun } from "./quizRun";
import { renderSettingsHome } from "./settingsHome";
import {
  renderSettingsAllowlist,
  renderSettingsAppearance,
  renderSettingsConnection,
  renderSettingsJokes,
  renderSettingsSites,
  renderSignOutConfirm,
} from "./settingsPages";
import { renderSourceAdd } from "./sourceAdd";
import { renderSourceConfirm } from "./sourceConfirm";
import { renderTrackCreate } from "./trackCreate";
import { renderTrackDetail } from "./trackDetail";
import { renderTracksTab } from "./tracksTab";

/** Parameter `N` of render function `F`: the props or the ctx argument. */
type Arg<F extends (...args: never[]) => unknown, N extends 0 | 1 | 2> = Parameters<F>[N];

/** Props and actions each inventory screen id takes. */
export interface ScreenArgs {
  signin: { props: Arg<typeof renderSignIn, 1>; ctx: Arg<typeof renderSignIn, 0> };
  "signed-out": { props: Arg<typeof renderSignedOut, 0>; ctx: Arg<typeof renderSignedOut, 1> };
  "conn-detail": { props: Arg<typeof renderConnectionDetail, 0>; ctx: Arg<typeof renderConnectionDetail, 1> };
  "offline-queue": { props: Arg<typeof renderOfflineQueue, 0>; ctx: Arg<typeof renderOfflineQueue, 1> };
  "scan-results": { props: Arg<typeof renderScanResults, 0>; ctx: Arg<typeof renderScanResults, 1> };
  "summary-panel": { props: Arg<typeof renderSummaryPanel, 0>; ctx: undefined };
  review: { props: ReviewRow[]; ctx: ReviewHandlers };
  "courses-tab": { props: Arg<typeof renderCoursesTab, 1>; ctx: Arg<typeof renderCoursesTab, 0> };
  "list-detail": { props: Arg<typeof renderListDetail, 0>; ctx: Arg<typeof renderListDetail, 1> };
  "list-edit": { props: Arg<typeof renderListEdit, 0>; ctx: Arg<typeof renderListEdit, 1> };
  "list-delete": { props: Arg<typeof renderListDelete, 0>; ctx: Arg<typeof renderListDelete, 1> };
  "course-generate": { props: Arg<typeof renderCourseGenerate, 1>; ctx: Arg<typeof renderCourseGenerate, 0> };
  "course-detail": { props: Arg<typeof renderCourseDetail, 1>; ctx: Arg<typeof renderCourseDetail, 0> };
  "course-regenerate": { props: Arg<typeof renderCourseRegenerate, 1>; ctx: Arg<typeof renderCourseRegenerate, 0> };
  "quiz-run": { props: Arg<typeof renderQuizRun, 0>; ctx: Arg<typeof renderQuizRun, 1> };
  "quiz-end": { props: Arg<typeof renderQuizEnd, 0>; ctx: Arg<typeof renderQuizEnd, 1> };
  "tracks-tab": { props: Arg<typeof renderTracksTab, 0>; ctx: Arg<typeof renderTracksTab, 1> };
  "track-create": { props: Arg<typeof renderTrackCreate, 0>; ctx: Arg<typeof renderTrackCreate, 1> };
  "track-detail": { props: Arg<typeof renderTrackDetail, 0>; ctx: Arg<typeof renderTrackDetail, 1> };
  "source-add": { props: Arg<typeof renderSourceAdd, 0>; ctx: Arg<typeof renderSourceAdd, 1> };
  "source-confirm-tree": { props: Arg<typeof renderSourceConfirm, 0>; ctx: Arg<typeof renderSourceConfirm, 1> };
  "exam-result-entry": { props: Arg<typeof renderExamEntry, 0>; ctx: Arg<typeof renderExamEntry, 1> };
  "exam-result-proposals": { props: Arg<typeof renderExamProposals, 0>; ctx: Arg<typeof renderExamProposals, 1> };
  "exam-result": { props: Arg<typeof renderExamResult, 0>; ctx: Arg<typeof renderExamResult, 1> };
  "settings-home": { props: undefined; ctx: Arg<typeof renderSettingsHome, 0> };
  "settings-connection": { props: Arg<typeof renderSettingsConnection, 0>; ctx: Arg<typeof renderSettingsConnection, 1> };
  "signout-confirm": { props: Arg<typeof renderSignOutConfirm, 0>; ctx: Arg<typeof renderSignOutConfirm, 1> };
  "settings-sites": { props: Arg<typeof renderSettingsSites, 0>; ctx: Arg<typeof renderSettingsSites, 1> };
  "settings-jokes": { props: Arg<typeof renderSettingsJokes, 0>; ctx: Arg<typeof renderSettingsJokes, 1> };
  "settings-appearance": { props: Arg<typeof renderSettingsAppearance, 0>; ctx: Arg<typeof renderSettingsAppearance, 1> };
  "settings-allowlist": { props: Arg<typeof renderSettingsAllowlist, 0>; ctx: Arg<typeof renderSettingsAllowlist, 1> };
  "ignored-list": { props: Arg<typeof renderIgnoredList, 0>; ctx: Arg<typeof renderIgnoredList, 1> };
}

/** Id of an inventory screen the registry must draw. */
export type InventoryScreenId = keyof ScreenArgs;

/** Screen id to render function: one entry for every inventory screen id. */
export type InventoryRegistry = {
  [K in InventoryScreenId]: (props: ScreenArgs[K]["props"], ctx: ScreenArgs[K]["ctx"]) => HTMLElement;
};

/** Every panel tab and settings page screen, keyed by its inventory id. */
export const SCREENS: InventoryRegistry = {
  signin: (props, handlers) => renderSignIn(handlers, props),
  "signed-out": (props, handlers) => renderSignedOut(props, handlers),
  "conn-detail": (props, handlers) => renderConnectionDetail(props, handlers),
  "offline-queue": (props, handlers) => renderOfflineQueue(props, handlers),
  "scan-results": (props, handlers) => renderScanResults(props, handlers),
  "summary-panel": (props) => renderSummaryPanel(props),
  review: (rows, handlers) => {
    // renderReview fills a root element rather than returning one: draw into a fresh div.
    const root = document.createElement("div");
    renderReview(root, rows, handlers);
    return root;
  },
  "courses-tab": (props, handlers) => renderCoursesTab(handlers, props),
  "list-detail": (props, actions) => renderListDetail(props, actions),
  "list-edit": (props, actions) => renderListEdit(props, actions),
  "list-delete": (props, actions) => renderListDelete(props, actions),
  "course-generate": (props, handlers) => renderCourseGenerate(handlers, props),
  "course-detail": (props, handlers) => renderCourseDetail(handlers, props),
  "course-regenerate": (props, handlers) => renderCourseRegenerate(handlers, props),
  "quiz-run": (props, actions) => renderQuizRun(props, actions),
  "quiz-end": (props, actions) => renderQuizEnd(props, actions),
  "tracks-tab": (props, handlers) => renderTracksTab(props, handlers),
  "track-create": (props, handlers) => renderTrackCreate(props, handlers),
  "track-detail": (props, handlers) => renderTrackDetail(props, handlers),
  "source-add": (props, handlers) => renderSourceAdd(props, handlers),
  "source-confirm-tree": (props, handlers) => renderSourceConfirm(props, handlers),
  "exam-result-entry": (props, handlers) => renderExamEntry(props, handlers),
  "exam-result-proposals": (props, handlers) => renderExamProposals(props, handlers),
  "exam-result": (props, handlers) => renderExamResult(props, handlers),
  "settings-home": (_props, handlers) => renderSettingsHome(handlers),
  "settings-connection": (props, handlers) => renderSettingsConnection(props, handlers),
  "signout-confirm": (props, handlers) => renderSignOutConfirm(props, handlers),
  "settings-sites": (props, handlers) => renderSettingsSites(props, handlers),
  "settings-jokes": (props, handlers) => renderSettingsJokes(props, handlers),
  "settings-appearance": (props, handlers) => renderSettingsAppearance(props, handlers),
  "settings-allowlist": (props, handlers) => renderSettingsAllowlist(props, handlers),
  "ignored-list": (props, handlers) => renderIgnoredList(props, handlers),
};

/** Draws the inventory screen `id` from its props and ctx; returns the element to append. */
export function drawScreen<K extends InventoryScreenId>(
  id: K,
  props: ScreenArgs[K]["props"],
  ctx: ScreenArgs[K]["ctx"],
): HTMLElement {
  return SCREENS[id](props, ctx);
}
