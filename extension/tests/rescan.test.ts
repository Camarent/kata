import { describe, expect, it, vi } from "vitest";
import {
  createRescanner,
  mergeMarks,
  type RescanDeps,
  type ScanConceptItem,
} from "../src/rescan";

interface Item extends ScanConceptItem {
  word: string;
}

/** Fake clock: timers fire only when `advance` moves time past their due time. */
function fakeClock() {
  let now = 0;
  let nextId = 1;
  const timers = new Map<number, { due: number; fire: () => void }>();
  return {
    setTimer(fire: () => void, ms: number): unknown {
      const id = nextId++;
      timers.set(id, { due: now + ms, fire });
      return id;
    },
    clearTimer(handle: unknown): void {
      timers.delete(handle as number);
    },
    advance(ms: number): void {
      now += ms;
      for (const [id, timer] of [...timers]) {
        if (timer.due <= now && timers.delete(id)) timer.fire();
      }
    },
    pending: () => timers.size,
  };
}

/** Observer fake: `trigger` simulates one page mutation. */
function fakeObserver() {
  let callback: (() => void) | null = null;
  const stopped = vi.fn();
  return {
    observe(cb: () => void): () => void {
      callback = cb;
      return stopped;
    },
    trigger(): void {
      callback?.();
    },
    stopped,
  };
}

function setup(overrides: Partial<RescanDeps> = {}) {
  const clock = fakeClock();
  const observer = fakeObserver();
  const onRescan = vi.fn();
  const deps: RescanDeps = {
    observe: (cb) => observer.observe(cb),
    debounceMs: 100,
    setTimer: clock.setTimer,
    clearTimer: clock.clearTimer,
    onRescan,
    ...overrides,
  };
  const rescanner = createRescanner(deps);
  return { clock, observer, onRescan, rescanner };
}

describe("mergeMarks", () => {
  it("keeps the previous state for the same concept id, even when the word text changed", () => {
    const prev: Item[] = [{ conceptId: 7, state: "known", word: "old" }];
    const next: Item[] = [{ conceptId: 7, state: "unknown", word: "new" }];
    expect(mergeMarks(prev, next)).toEqual([{ conceptId: 7, state: "known", word: "new" }]);
  });

  it("drops previous items that are gone from the page", () => {
    const prev: ScanConceptItem[] = [
      { conceptId: 1, state: "known" },
      { conceptId: 2, state: "known" },
    ];
    const next: Item[] = [{ conceptId: 2, state: "unknown", word: "b" }];
    expect(mergeMarks(prev, next)).toEqual([{ conceptId: 2, state: "known", word: "b" }]);
  });

  it("keeps the server state for a concept unknown to the previous scan", () => {
    const prev: ScanConceptItem[] = [{ conceptId: 1, state: "known" }];
    const next: Item[] = [{ conceptId: 3, state: "abstain", word: "c" }];
    expect(mergeMarks(prev, next)).toEqual([{ conceptId: 3, state: "abstain", word: "c" }]);
  });

  it("does not merge items with a null concept id", () => {
    const prev: ScanConceptItem[] = [{ conceptId: null, state: "known" }];
    const next: Item[] = [{ conceptId: null, state: "unknown", word: "n" }];
    expect(mergeMarks(prev, next)).toEqual([{ conceptId: null, state: "unknown", word: "n" }]);
  });

  it("keeps a null previous state for a matched concept", () => {
    const prev: ScanConceptItem[] = [{ conceptId: 4, state: null }];
    const next: Item[] = [{ conceptId: 4, state: "known", word: "d" }];
    expect(mergeMarks(prev, next)).toEqual([{ conceptId: 4, state: null, word: "d" }]);
  });
});

describe("createRescanner", () => {
  it("collapses a burst of 5 mutations into one rescan after the last one", () => {
    const { clock, observer, onRescan } = setup();
    for (let i = 0; i < 5; i++) {
      observer.trigger();
      clock.advance(50);
    }
    expect(onRescan).not.toHaveBeenCalled();
    clock.advance(100);
    expect(onRescan).toHaveBeenCalledTimes(1);
    clock.advance(1000);
    expect(onRescan).toHaveBeenCalledTimes(1);
  });

  it("fires again for a mutation after the debounce window", () => {
    const { clock, observer, onRescan } = setup();
    observer.trigger();
    clock.advance(100);
    observer.trigger();
    clock.advance(100);
    expect(onRescan).toHaveBeenCalledTimes(2);
  });

  it("stop cancels the pending timer and the observer", () => {
    const { clock, observer, onRescan, rescanner } = setup();
    observer.trigger();
    rescanner.stop();
    expect(observer.stopped).toHaveBeenCalledTimes(1);
    expect(clock.pending()).toBe(0);
    clock.advance(1000);
    expect(onRescan).not.toHaveBeenCalled();
  });

  it("ignores mutations that arrive after stop", () => {
    const { clock, observer, onRescan, rescanner } = setup();
    rescanner.stop();
    observer.trigger();
    clock.advance(1000);
    expect(onRescan).not.toHaveBeenCalled();
    expect(clock.pending()).toBe(0);
  });

  it("stop is safe to call twice", () => {
    const { observer, rescanner } = setup();
    rescanner.stop();
    rescanner.stop();
    expect(observer.stopped).toHaveBeenCalledTimes(1);
  });
});
