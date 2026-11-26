/** Timer source; injected so tests drive time by hand. */
export interface Clock {
  setTimeout(run: () => void, ms: number): number;
  clearTimeout(handle: number): void;
}

export const SYSTEM_CLOCK: Clock = {
  setTimeout: (run, ms) => window.setTimeout(run, ms),
  clearTimeout: (handle) => window.clearTimeout(handle),
};

export interface DeferredCommit {
  /** True until the commit has run or undo has been taken. */
  readonly pending: boolean;
  /** Cancels the commit and returns true the first time only; later calls return false. */
  undo(): boolean;
}

/**
 * Runs commit after windowMs unless undo() is called first. Commit runs at most once and undo
 * takes effect at most once.
 */
export function deferCommit(commit: () => void, windowMs: number, clock: Clock = SYSTEM_CLOCK): DeferredCommit {
  let pending = true;
  const handle = clock.setTimeout(() => {
    if (!pending) return;
    pending = false;
    commit();
  }, windowMs);
  return {
    get pending() {
      return pending;
    },
    undo(): boolean {
      if (!pending) return false;
      pending = false;
      clock.clearTimeout(handle);
      return true;
    },
  };
}
