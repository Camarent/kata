import type { Backend } from "./backgroundBackend";
import { CoreHttpError } from "./coreClient";
import type { PanelMessage, PanelReply } from "./messages";

/** One panel message handler: the backend call for one message type, with its reply. */
type PanelHandler<T extends PanelMessage["type"]> = (
  backend: Backend,
  message: Extract<PanelMessage, { type: T }>,
) => Promise<PanelReply>;

/**
 * Runs a backend call that may refuse with a Core HTTP error; the refusal becomes the reply with
 * its status and code. A call that returns a value puts it in the reply as `data`.
 */
async function refusable(call: () => Promise<unknown>): Promise<PanelReply> {
  try {
    const data = await call();
    return data === undefined ? { ok: true } : { ok: true, data };
  } catch (err) {
    if (err instanceof CoreHttpError) return { ok: false, error: err.message, status: err.status, code: err.code };
    throw err;
  }
}

/** One handler per panel message type; its keys are the message types `isPanelMessage` accepts. */
const PANEL_HANDLERS: { [T in PanelMessage["type"]]: PanelHandler<T> } = {
  "panel:signIn": async (backend, message) => {
    await backend.signIn(message.input);
    return { ok: true };
  },
  "panel:disconnect": async (backend) => {
    await backend.disconnect();
    return { ok: true };
  },
  "panel:scan": async (backend) => ({ ok: true, data: await backend.scan() }),
  "panel:scanConcepts": async (backend) => ({ ok: true, data: await backend.scanConcepts() }),
  "panel:chooseConcept": async (backend, message) => {
    await backend.chooseConcept(message.topicId, message.word, message.conceptId);
    return { ok: true };
  },
  "panel:reassignConcept": async (backend, message) => {
    await backend.reassignConcept(message.topicId, message.word, message.fromConceptId, message.toConceptId);
    return { ok: true };
  },
  "panel:topicOverview": async (backend, message) => ({ ok: true, data: await backend.topicOverview(message.topicId) }),
  "panel:known": async (backend, message) => ({ ok: true, data: await backend.markKnown(message.topicId) }),
  "panel:review": async (backend) => ({ ok: true, data: await backend.review() }),
  "panel:setConcept": async (backend, message) => {
    await backend.setConcept(message.conceptId, message.state);
    return { ok: true };
  },
  "panel:pending": async (backend) => ({ ok: true, data: await backend.pendingCount() }),
  "panel:courses": async (backend) => ({ ok: true, data: await backend.courses() }),
  "panel:openCourse": async (backend, message) => {
    await backend.openCourse(message.courseId);
    return { ok: true };
  },
  "panel:deleteCourse": async (backend, message) => {
    await backend.deleteCourse(message.courseId);
    return { ok: true };
  },
  "panel:createCourse": (backend, message) => refusable(() => backend.createCourse(message.title)),
  "panel:regenerateCourse": (backend, message) => refusable(() => backend.regenerateCourse(message.courseId)),
  "panel:modelhost": async (backend, message) => ({ ok: true, data: await backend.modelhost(message.request) }),
  "panel:tracks": (backend, message) =>
    refusable(() => backend.tracks({ limit: message.limit, beforeId: message.beforeId })),
  "panel:getTrack": (backend, message) => refusable(() => backend.getTrack(message.trackId)),
  "panel:createTrack": (backend, message) => refusable(() => backend.createTrack(message.input)),
  "panel:patchTrack": (backend, message) => refusable(() => backend.patchTrack(message.trackId, message.patch)),
  "panel:deleteTrack": (backend, message) => refusable(() => backend.deleteTrack(message.trackId)),
  "panel:addDecisionPoint": (backend, message) =>
    refusable(() => backend.addDecisionPoint(message.trackId, message.input)),
  "panel:addQuizSource": (backend, message) => refusable(() => backend.addQuizSource(message.url)),
  "panel:importExamResult": (backend, message) => refusable(() => backend.importExamResult(message.payload)),
  "panel:confirmExamResult": (backend, message) =>
    refusable(() => backend.confirmExamResult(message.resultId, message.conceptIds)),
  "panel:dismissExamResult": (backend, message) => refusable(() => backend.dismissExamResult(message.resultId)),
  "panel:ignored": (backend) => refusable(() => backend.ignored()),
  "panel:ignoreConcept": (backend, message) => refusable(() => backend.ignoreConcept(message.conceptId)),
  // Image concepts need a vision model (D33, D16), not built: the image menu has no concepts to act on yet.
  "panel:imageAction": async () => ({ ok: false, error: "image concepts are not available yet" }),
  "panel:deleteConcept": (backend, message) => refusable(() => backend.deleteConcept(message.conceptId)),
  "panel:unignoreConcept": (backend, message) => refusable(() => backend.unignoreConcept(message.conceptId)),
  "panel:markConceptViewed": (backend, message) => refusable(() => backend.markConceptViewed(message.conceptId)),
  "panel:listConceptAliases": (backend, message) => refusable(() => backend.listConceptAliases(message.conceptId)),
  "panel:addConceptAlias": (backend, message) =>
    refusable(() => backend.addConceptAlias(message.conceptId, message.alias)),
  "panel:requestSummary": (backend, message) => refusable(() => backend.requestSummary(message.url, message.text)),
  "panel:cachedSummary": (backend, message) => refusable(() => backend.cachedSummary(message.url, message.textSha256)),
  "panel:nextJoke": (backend) => refusable(() => backend.nextJoke()),
  "panel:listJokeSources": (backend) => refusable(() => backend.listJokeSources()),
};

/** Routes one panel message to the backend and returns its reply. */
export async function handlePanelMessage(backend: Backend, message: PanelMessage): Promise<PanelReply> {
  const handler = PANEL_HANDLERS[message.type] as PanelHandler<PanelMessage["type"]>;
  return handler(backend, message);
}

/** True when `message` has one of the panel message shapes. */
export function isPanelMessage(message: unknown): message is PanelMessage {
  if (typeof message !== "object" || message === null) return false;
  const type = (message as { type?: unknown }).type;
  return typeof type === "string" && Object.keys(PANEL_HANDLERS).includes(type);
}
