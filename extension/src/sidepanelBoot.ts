import type { CourseList, PanelMessage, PanelReply } from "./background";
import { renderPanel, type PanelHandlers, type PanelState, type ServerFormInput } from "./sidepanel";
import { TokenStore, type StorageArea } from "./tokenStore";
import { CoreHttpError } from "./coreClient";
import type { MarkOutcome } from "./offlineQueue";
import type { ReviewRow, ReviewState } from "./reviewScreen";
import { validateServerUrl } from "./serverUrl";
import type { Session } from "./types";

/** Origin permission request or removal: the host pattern `<origin>/*`. */
export interface OriginsRequest {
  origins: string[];
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
    courses: [],
  };
  const draw = (): void => renderPanel(root, state, handlers);

  /** Ready courses, limit and total for the Courses section; a refused list leaves the section out. */
  const loadCourses = async (): Promise<void> => {
    const reply = await api.runtime.sendMessage({ type: "panel:courses" });
    const list = reply.ok ? (reply.data as CourseList | undefined) : undefined;
    state.courses = list && Array.isArray(list.items) ? list.items : [];
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
    state.courseLimit = undefined;
    state.courseTotal = undefined;
    state.status = { kind: "idle" };
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

    async onKnown(topicId: number): Promise<MarkOutcome> {
      const reply = await api.runtime.sendMessage({ type: "panel:known", topicId });
      if (!reply.ok) throw new Error(reply.error);
      return reply.data as MarkOutcome;
    },

    async onReview() {
      const reply = await api.runtime.sendMessage({ type: "panel:review" });
      if (reply.ok) {
        state.review = reply.data as ReviewRow[];
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
      draw();
    },

    async onOpenCourse(courseId: number) {
      const reply = await api.runtime.sendMessage({ type: "panel:openCourse", courseId });
      if (!reply.ok) throw new Error(reply.error);
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
    async onDeleteCourse(courseId: number) {
      const reply = await api.runtime.sendMessage({ type: "panel:deleteCourse", courseId });
      if (!reply.ok) throw new Error(reply.error);
      // The list and the "n of limit" count come from the core again, so the deleted course leaves the panel.
      await loadCourses();
      draw();
    },
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

/** Host pattern of a stored session's server, or null when there is no usable session. */
function originPattern(session: Session | null): string | null {
  if (session === null) return null;
  const parsed = validateServerUrl(session.baseUrl);
  return parsed.ok ? parsed.pattern : null;
}

// Side panel page entry: runs only where the extension runtime exists (not under tests).
if (typeof chrome !== "undefined" && chrome.runtime) {
  const root = document.getElementById("panel");
  if (root) {
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
