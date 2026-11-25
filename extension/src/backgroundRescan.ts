import type { ChromeLike } from "./background";
import type { ScanResponse } from "./content";
import type { CoreClient } from "./coreClient";
import { runConceptScan, type ConceptScanError, type ConceptScanResult } from "./conceptScan";
import { createRescanner, mergeMarks, type Rescanner } from "./rescan";
import type { TokenStore } from "./tokenStore";
import type { Session } from "./types";

/** Quiet time after the last page change before the concept rescan runs, in milliseconds. */
export const RESCAN_DEBOUNCE_MS = 1500;

/** The page key: the URL without its fragment (the core keys classifications by it). */
export function pageKeyOf(url: string): string {
  const page = new URL(url);
  page.hash = "";
  return page.toString();
}

/** Merges a rescan into the previous result: concepts known before keep their state, the rest take the new one. */
export function mergeScanResult(prev: ConceptScanResult, next: ConceptScanResult): ConceptScanResult {
  const merged = mergeMarks(
    prev.blocks.flatMap((block) => block.concepts),
    next.blocks.flatMap((block) => block.concepts),
  );
  let at = 0;
  const blocks = next.blocks.map((block) => ({
    ...block,
    concepts: block.concepts.map(() => merged[at++]),
  }));
  return { ...next, blocks };
}

/** What the concept scan and its rescan need from the backend. */
export interface ConceptScannerDeps {
  api: ChromeLike;
  tokens: TokenStore;
  clientFor(session: Session): CoreClient;
  pollMs: number;
  maxWaitMs: number;
}

/** The concept scan of a page and the rescan that follows it. */
export interface ConceptScanner {
  /** Asks the page for its blocks and runs the concept scan over them. */
  scanPage(session: Session, tabId: number, pageKey: string): Promise<ConceptScanResult | ConceptScanError>;
  /** Watches the page of `tabId` and rescans it on change, keeping `first` as the last result. */
  startRescan(tabId: number, pageKey: string, first: ConceptScanResult): void;
  /** Stops the rescan in progress, if any. */
  stopRescan(): void;
  /** A watched page changed in the DOM: restarts the rescan debounce for that tab. */
  pageMutated(tabId: number): void;
  /** Stops the rescan when the watched tab navigates away. */
  tabNavigated(tabId: number): void;
}

/** Builds the concept scanner over the chrome tabs API, the token store and the core client factory. */
export function createConceptScanner(deps: ConceptScannerDeps): ConceptScanner {
  const { api, tokens, clientFor, pollMs, maxWaitMs } = deps;

  /** The rescan in progress: its tab, page key, last merged result and stop function. */
  let watched: { tabId: number; pageKey: string; last: ConceptScanResult; rescanner: Rescanner } | undefined;
  /** Mutation callbacks of the watched pages, by tab id. */
  const mutationHandlers = new Map<number, () => void>();

  const stopRescan = (): void => {
    watched?.rescanner.stop();
    watched = undefined;
  };

  const scanPage = async (session: Session, tabId: number, pageKey: string): Promise<ConceptScanResult | ConceptScanError> => {
    const page = (await api.tabs.sendMessage(tabId, { type: "scan" })) as ScanResponse;
    if (!page?.blocks) return { error: "page gave no blocks" };
    return runConceptScan(clientFor(session), { pageKey, blocks: page.blocks }, { pollMs, maxWaitMs });
  };

  /** One rescan: scans the watched page again and keeps the states known before. */
  const rescanOnce = async (tabId: number): Promise<void> => {
    const session = await tokens.loadSession();
    const current = watched;
    if (!session || !current || current.tabId !== tabId) return;
    const next = await scanPage(session, tabId, current.pageKey);
    if ("error" in next || watched !== current) return;
    current.last = mergeScanResult(current.last, next);
  };

  const startRescan = (tabId: number, pageKey: string, first: ConceptScanResult): void => {
    const rescanner = createRescanner({
      observe(onMutation) {
        mutationHandlers.set(tabId, onMutation);
        api.tabs.sendMessage(tabId, { type: "watch" }).catch(() => undefined);
        return () => {
          if (mutationHandlers.get(tabId) === onMutation) mutationHandlers.delete(tabId);
          api.tabs.sendMessage(tabId, { type: "unwatch" }).catch(() => undefined);
        };
      },
      debounceMs: RESCAN_DEBOUNCE_MS,
      setTimer: (fire, ms) => setTimeout(fire, ms),
      clearTimer: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
      onRescan: () => {
        rescanOnce(tabId).catch(() => undefined);
      },
    });
    watched = { tabId, pageKey, last: first, rescanner };
  };

  return {
    scanPage,
    startRescan,
    stopRescan,
    pageMutated(tabId) {
      mutationHandlers.get(tabId)?.();
    },
    tabNavigated(tabId) {
      if (watched?.tabId === tabId) stopRescan();
    },
  };
}
