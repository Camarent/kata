import type { CourseLink, PanelMessage, PanelReply } from "./background";
import { renderPanel, type PanelHandlers, type PanelState, type SignInInput } from "./sidepanel";
import { TokenStore, type StorageArea } from "./tokenStore";
import type { MarkOutcome } from "./offlineQueue";
import type { ReviewRow, ReviewState } from "./reviewScreen";

/** The part of `chrome` the side panel page uses; tests pass a fake with these members. */
export interface PanelChromeLike {
  runtime: { sendMessage(message: PanelMessage): Promise<PanelReply> };
  storage: { local: StorageArea };
}

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

  /** Ready courses for the Courses section; a refused list leaves the section out. */
  const loadCourses = async (): Promise<CourseLink[]> => {
    const reply = await api.runtime.sendMessage({ type: "panel:courses" });
    return reply.ok && Array.isArray(reply.data) ? (reply.data as CourseLink[]) : [];
  };
  if (state.session !== null) state.courses = await loadCourses();

  const handlers: PanelHandlers = {
    async onSignIn(input: SignInInput) {
      const reply = await api.runtime.sendMessage({ type: "panel:signIn", input });
      if (reply.ok) {
        state.session = await tokens.loadSession();
        state.status = { kind: "idle" };
        state.courses = await loadCourses();
      } else {
        state.status = { kind: "error", reason: "auth" };
      }
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
  };

  draw();
}

// Side panel page entry: runs only where the extension runtime exists (not under tests).
if (typeof chrome !== "undefined" && chrome.runtime) {
  const root = document.getElementById("panel");
  if (root) {
    void bootPanel(root, {
      runtime: { sendMessage: (message) => chrome.runtime.sendMessage<PanelMessage, PanelReply>(message) },
      storage: { local: chrome.storage.local },
    });
  }
}
