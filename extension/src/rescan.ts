/**
 * Rescan on page change. Pure helpers: the page observer and the timers are
 * injected, so tests drive them with a fake clock.
 */

/** The part of a scan result item the rescan needs (kept local to avoid a dependency). */
export interface ScanConceptItem {
  conceptId: number | null;
  state: string | null;
}

/**
 * Returns `next` (the items now on the page) with each state kept from `prev`
 * for the same non-null concept id. Items missing from `next` are dropped.
 * Concepts unknown to `prev` and items with a null concept id keep `next`'s state.
 */
export function mergeMarks<T extends ScanConceptItem>(
  prev: ScanConceptItem[],
  next: T[],
): T[] {
  const prevState = new Map<number, string | null>();
  for (const item of prev) {
    if (item.conceptId !== null) prevState.set(item.conceptId, item.state);
  }
  return next.map((item) => {
    if (item.conceptId === null || !prevState.has(item.conceptId)) return item;
    return { ...item, state: prevState.get(item.conceptId) ?? null };
  });
}

/** Timer handle as returned by the injected `setTimer`. */
export type TimerHandle = unknown;

/** Injected page observer and timers; `observe` returns the function that stops it. */
export interface RescanDeps {
  observe(onMutation: () => void): () => void;
  debounceMs: number;
  setTimer(fire: () => void, ms: number): TimerHandle;
  clearTimer(handle: TimerHandle): void;
  onRescan(): void;
}

/** A running rescanner; `stop` cancels the pending timer and the observer. */
export interface Rescanner {
  stop(): void;
}

/**
 * Starts observing the page. Every mutation restarts one debounce timer, so a
 * burst of mutations fires `onRescan` once, `debounceMs` after the last one.
 * After `stop`, no timer fires and no mutation is counted.
 */
export function createRescanner(deps: RescanDeps): Rescanner {
  let pending: TimerHandle | undefined;
  let stopped = false;

  const cancelPending = (): void => {
    if (pending !== undefined) deps.clearTimer(pending);
    pending = undefined;
  };

  const stopObserver = deps.observe(() => {
    if (stopped) return;
    cancelPending();
    pending = deps.setTimer(() => {
      pending = undefined;
      if (!stopped) deps.onRescan();
    }, deps.debounceMs);
  });

  return {
    stop() {
      if (stopped) return;
      stopped = true;
      cancelPending();
      stopObserver();
    },
  };
}
