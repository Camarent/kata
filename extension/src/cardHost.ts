import { renderCardMain, type PageCounts } from "./ui/card/cardMain";
import { renderCardScan, type ScanStatus } from "./ui/card/cardScan";
import { renderCardSummary, type SummaryStatus } from "./ui/card/cardSummary";
import { renderPageChanged } from "./ui/overlay/pageChanged";
import type { ConceptScanError, ConceptScanResult } from "./conceptScan";
import type { PanelReply } from "./background";

/** The part of `chrome.runtime` the card needs: send one message to the background script. */
export interface CardRuntime {
  sendMessage(message: unknown): Promise<unknown>;
}

/** Actions that need the browser side panel or a backend call not wired yet; default to no-ops. */
export interface CardHostOptions {
  onOpenPanel?: () => void;
  onQuiz?: () => void;
  onFocus?: () => void;
  /** Runs after each scan that found concepts; the page script starts watching for page changes. */
  onScanned?: () => void;
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
  const onFocus = options.onFocus ?? ((): void => undefined);

  let counts: PageCounts | null = null;
  let prompt: HTMLElement | null = null;
  let current: HTMLElement | null = null;

  const draw = (card: HTMLElement | null): void => {
    current = card;
    root.replaceChildren(...(card ? [card] : []), ...(prompt ? [prompt] : []));
  };
  const showMain = (): void => {
    draw(
      renderCardMain(
        { counts, serverDown: false, focusOn: false },
        { onScan: () => void scan(), onSummary: showSummary, onQuiz, onFocus, onOpenPanel, onCollapse: host.close },
      ),
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
    // The page summary has no backend call yet: before a scan the card asks for one, after it reports an error.
    const status: SummaryStatus = counts === null ? { kind: "needsScan" } : { kind: "error" };
    draw(renderCardSummary(status, { onOpenInPanel: onOpenPanel, onBack: showMain }));
  };
  const scan = async (): Promise<void> => {
    showScan({ kind: "scanning" });
    const status = await requestScan(runtime);
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
