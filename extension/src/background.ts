import type { ContentMessage, RuntimeLike, ScanResponse } from "./content";
import type { BridgeMessage } from "./bridge";
import { wireBridgeRegistration } from "./bridgeRegister";
import { openPanel, type PanelOpenApi } from "./browser";
import { DEFAULT_BASE_URL, MAX_WAIT_MS, POLL_MS, REQUEST_TIMEOUT_MS } from "./config";
import { CoreAuthError, CoreClient, type ConceptMark, type ProgressDoc } from "./coreClient";
import { OfflineQueue, type FlushResult, type MarkOutcome } from "./offlineQueue";
import { createProgressBridge, type ProgressBridge } from "./progressBridge";
import { runScan, type ScanResult } from "./scanSession";
import type { SignInInput } from "./sidepanel";
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
  };
  runtime: RuntimeLike;
}

/** Messages the side panel page sends to the background script. */
export type PanelMessage =
  | { type: "panel:signIn"; input: SignInInput }
  | { type: "panel:scan" }
  | { type: "panel:known"; topicId: number }
  | { type: "panel:review" }
  | { type: "panel:setConcept"; conceptId: number; state: ConceptMark["state"] };

/** Reply to a panel message: the result, or the error text. */
export type PanelReply = { ok: true; data?: unknown } | { ok: false; error: string };

/** One concept on the review screen; `state` is null when the core abstains and no mark exists. */
export interface ReviewRow {
  conceptId: number;
  label: string;
  state: ConceptMark["state"] | null;
  evidence: string;
}

/** Business logic behind the side panel; each call talks to the core. */
export interface Backend {
  signIn(input: SignInInput): Promise<void>;
  scan(): Promise<ScanResult[]>;
  markKnown(topicId: number): Promise<MarkOutcome>;
  flush(): Promise<FlushResult | null>;
  review(): Promise<ReviewRow[]>;
  setConcept(conceptId: number, state: ConceptMark["state"]): Promise<void>;
  /** Whole-document progress load and save for the course pages (see bridge.ts). */
  progress: ProgressBridge;
}

/** Builds the backend over the chrome tabs API and the extension storage area. */
export function createBackend(api: ChromeLike, area: StorageArea, fetchImpl?: typeof fetch): Backend {
  const tokens = new TokenStore(area);
  const clientFor = (session: Session | null): CoreClient =>
    new CoreClient({
      baseUrl: session?.baseUrl ?? DEFAULT_BASE_URL,
      token: session?.token,
      timeoutMs: REQUEST_TIMEOUT_MS,
      fetchImpl,
    });
  const requireSession = async (): Promise<Session> => {
    const session = await tokens.loadSession();
    if (!session) throw new CoreAuthError("not signed in");
    return session;
  };

  return {
    progress: createProgressBridge(clientFor, tokens),

    async signIn(input) {
      const client = clientFor(null);
      const token = await client.enrol(input.code, input.deviceLabel);
      await tokens.saveSession({ baseUrl: DEFAULT_BASE_URL, token });
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
  };
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
    case "panel:scan":
      return { ok: true, data: await backend.scan() };
    case "panel:known":
      return { ok: true, data: await backend.markKnown(message.topicId) };
    case "panel:review":
      return { ok: true, data: await backend.review() };
    case "panel:setConcept":
      await backend.setConcept(message.conceptId, message.state);
      return { ok: true };
  }
}

/** True when `message` has one of the panel message shapes. */
function isPanelMessage(message: unknown): message is PanelMessage {
  if (typeof message !== "object" || message === null) return false;
  const type = (message as { type?: unknown }).type;
  return (
    type === "panel:signIn" ||
    type === "panel:scan" ||
    type === "panel:known" ||
    type === "panel:review" ||
    type === "panel:setConcept"
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
  wireBridgeRegistration(chrome.runtime, chrome.scripting);
}
