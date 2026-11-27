import { renderCardMain, type PageCounts } from "./ui/card/cardMain";
import { renderCardScan, type ScanStatus } from "./ui/card/cardScan";
import { renderCardSummary, type SummaryStatus } from "./ui/card/cardSummary";
import { renderFocusConfirm, isFocusOn } from "./ui/card/focus";
import { renderJokeCloud } from "./ui/card/jokeCloud";
import { renderPageChanged } from "./ui/overlay/pageChanged";
import { scanBlocks } from "./scanner";
import type { ConceptScanError, ConceptScanResult } from "./conceptScan";
import type { Joke, SummaryReply } from "./coreClientTypes";
import type { PanelReply } from "./messages";

/** The part of `chrome.runtime` the card needs: send one message to the background script. */
export interface CardRuntime {
  sendMessage(message: unknown): Promise<unknown>;
}

/** Actions that need the browser side panel or a backend call not wired yet; default to no-ops. */
export interface CardHostOptions {
  onOpenPanel?: () => void;
  onQuiz?: () => void;
  /** Runs after each scan that found concepts; the page script starts watching for page changes. */
  onScanned?: () => void;
  /** Called when an undoable action happens (`undo` reverts it) or is gone (`null`). */
  onUndoable?: (undo: (() => void) | null) => void;
}

export interface CardHost {
  /** Container the cards and the page-changed prompt are drawn into. */
  readonly element: HTMLElement;
  /** Shows the main card. */
  open(): void;
  /** Hides the card (the page-changed prompt stays). */
  close(): void;
  /** Shows the page-changed prompt; its action rescans, Back dismisses it. */
  pageChanged(): void;
  /** Removes the container. */
  dispose(): void;
}

/** Counts concepts of a scan result by state; a concept with no id is counted once per mention. */
export function countConcepts(result: ConceptScanResult): PageCounts {
  const counts: PageCounts = { new: 0, learning: 0, known: 0 };
  for (const block of result.blocks) {
    if (block.skipped) continue;
    for (const concept of block.concepts) counts[concept.state] += 1;
  }
  return counts;
}

/** Runs the concept scan through the background script and maps its reply to a card status. */
export async function requestScan(runtime: CardRuntime): Promise<ScanStatus & { counts?: PageCounts }> {
  let reply: PanelReply;
  try {
    reply = (await runtime.sendMessage({ type: "panel:scanConcepts" })) as PanelReply;
  } catch {
    return { kind: "serverDown" };
  }
  if (!reply || !reply.ok || reply.data == null) return { kind: "error" };
  const data = reply.data as ConceptScanResult | ConceptScanError;
  if ("error" in data) return { kind: "error" };
  const counts = countConcepts(data);
  if (counts.new + counts.learning + counts.known === 0) return { kind: "empty" };
  return { kind: "done", counts };
}

/**
 * Asks the background script for the page summary (`panel:requestSummary`) and maps the reply to a
 * card status. A queued job (`{ id }`) shows the loading text: the card does not poll the job, so the
 * user opens the summary again to get the result.
 */
export async function requestSummary(runtime: CardRuntime, url: string, text: string): Promise<SummaryStatus> {
  let reply: PanelReply;
  try {
    reply = (await runtime.sendMessage({ type: "panel:requestSummary", url, text })) as PanelReply;
  } catch {
    return { kind: "error" };
  }
  if (!reply || !reply.ok || reply.data == null) return { kind: "error" };
  const data = reply.data as SummaryReply;
  if ("id" in data) return { kind: "queued" };
  return { kind: "ready", text: data.summary, topics: [] };
}

/**
 * Mounts the page cards (main, scan, summary) and the page-changed prompt into `parent`.
 * Scan data comes from the background script (`panel:scanConcepts`); the cards redraw on each step.
 */
export function mountCardHost(
  doc: Document,
  parent: HTMLElement,
  runtime: CardRuntime,
  options: CardHostOptions = {},
): CardHost {
  const root = doc.createElement("div");
  root.className = "card-host";
  parent.append(root);
  const onOpenPanel = options.onOpenPanel ?? ((): void => undefined);
  const onQuiz = options.onQuiz ?? ((): void => undefined);

  let counts: PageCounts | null = null;
  let serverDown = false;
  /** End time of focus mode (epoch ms), null when focus was never turned on. */
  let focusEnds: number | null = null;
  let prompt: HTMLElement | null = null;
  let current: HTMLElement | null = null;

  const draw = (card: HTMLElement | null): void => {
    current = card;
    root.replaceChildren(...(card ? [card] : []), ...(prompt ? [prompt] : []));
  };
  const showMain = (): void => {
    draw(
      renderCardMain(
        { counts, serverDown, focusOn: isFocusOn(focusEnds, Date.now) },
        { onScan: () => void scan(), onSummary: showSummary, onQuiz, onFocus: showFocus, onOpenPanel, onCollapse: host.close },
      ),
    );
  };
  const showFocus = (): void => {
    draw(
      renderFocusConfirm(focusEnds, Date.now, {
        onTurnOn: (endsAt) => {
          const before = focusEnds;
          focusEnds = endsAt;
          // Turning focus on can be undone from the pin's mini-menu.
          options.onUndoable?.(() => {
            focusEnds = before;
            options.onUndoable?.(null);
            if (current) showMain();
          });
          showMain();
        },
        onTurnOff: () => {
          focusEnds = null;
          options.onUndoable?.(null);
          showMain();
        },
        onCancel: showMain,
      }),
    );
  };
  const showScan = (status: ScanStatus): void => {
    draw(
      renderCardScan(
        { status, focusOn: false },
        { onShowInPanel: onOpenPanel, onScanAgain: () => void scan(), onBack: showMain },
      ),
    );
  };
  const showSummary = (): void => {
    const actions = { onOpenInPanel: onOpenPanel, onBack: showMain };
    // The summary needs a scan first; the page text is the scanned blocks.
    if (counts === null) {
      draw(renderCardSummary({ kind: "needsScan" }, actions));
      return;
    }
    const loading = renderCardSummary({ kind: "loading" }, actions);
    draw(loading);
    const text = scanBlocks(doc).map((block) => block.text).join("\n");
    void requestSummary(runtime, doc.location.href, text).then((status) => {
      // The user closed the card or went back while waiting: drop the reply.
      if (current === loading) draw(renderCardSummary(status, actions));
    });
  };
  /** Adds a joke cloud beside the card; a refused or empty joke shows nothing. */
  const showJoke = async (stillScanning: () => boolean): Promise<void> => {
    try {
      const reply = (await runtime.sendMessage({ type: "panel:nextJoke" })) as PanelReply;
      const joke = reply && reply.ok ? (reply.data as Joke | null) : null;
      // A late joke must not land on the result card.
      if (!joke || !stillScanning()) return;
      const cloud = renderJokeCloud(joke.text, () => cloud.remove());
      root.append(cloud);
    } catch {
      // No joke is fine: the scan goes on.
    }
  };
  const scan = async (): Promise<void> => {
    showScan({ kind: "scanning" });
    const card = current;
    // A joke keeps the wait short, but never while focus mode is on.
    if (!isFocusOn(focusEnds, Date.now)) void showJoke(() => current === card);
    const status = await requestScan(runtime);
    serverDown = status.kind === "serverDown";
    if (status.kind === "done") {
      counts = status.counts;
      options.onScanned?.();
    }
    showScan(status);
  };

  const host: CardHost = {
    element: root,
    open: showMain,
    close(): void {
      draw(null);
    },
    pageChanged(): void {
      prompt = renderPageChanged(doc, {
        onAction: () => {
          prompt = null;
          void scan();
        },
        onBack: () => {
          prompt = null;
          draw(current);
        },
      });
      draw(current);
    },
    dispose(): void {
      root.remove();
    },
  };
  return host;
}
