import { CoreAuthError, CoreHttpError, CoreOfflineError, CoreTimeoutError } from "./coreClient";
import type { StorageArea } from "./tokenStore";
import type { ConceptMark } from "./coreClientTypes";

/** Storage key holding the ordered queue of pending marks. */
const QUEUE_KEY = "kata.markQueue";

/** Legacy storage key: pending topic ids as one number array (read once, then removed). */
const LEGACY_KEY = "kata.pending";

/** The part of CoreClient the queue needs; injected so tests can fake it. */
export interface MarkSink {
  setKnown(topicId: number): Promise<unknown>;
  setConceptMark(conceptId: number, state: ConceptMark["state"]): Promise<unknown>;
}

/** Outcome of `markKnown` / `markConcept`: sent now, or kept for a later `flush`. */
export type MarkOutcome = "saved" | "queued";

/** One pending mark. A topic mark is always state "known". */
export interface QueuedMark {
  kind: "topic" | "concept";
  id: number;
  state: ConceptMark["state"];
}

/** Counts from one `flush` run. */
export interface FlushResult {
  /** Sent to the core now. */
  sent: number;
  /** Dropped because the core answered 404 (topic or concept gone). */
  dropped: number;
  /** Still pending after the run (core unreachable). */
  kept: number;
}

/** True when value is one queued mark. Invalid entries are skipped, not fatal. */
function isMark(value: unknown): value is QueuedMark {
  if (typeof value !== "object" || value === null) return false;
  const m = value as Partial<Record<keyof QueuedMark, unknown>>;
  return (
    (m.kind === "topic" || m.kind === "concept") &&
    typeof m.id === "number" &&
    typeof m.state === "string"
  );
}

/** Returns queue without any mark of the same kind and id, then appends mark (last mark wins). */
function withMark(queue: QueuedMark[], mark: QueuedMark): QueuedMark[] {
  return [...queue.filter((m) => !sameMark(m, mark)), mark];
}

/** Same item (kind and id), any state. */
function sameMark(a: QueuedMark, b: QueuedMark): boolean {
  return a.kind === b.kind && a.id === b.id;
}

/** Same item and same state. */
function sameState(a: QueuedMark, b: QueuedMark): boolean {
  return sameMark(a, b) && a.state === b.state;
}

/** Mark writes that survive a dropped connection: failures wait in storage. */
export class OfflineQueue {
  constructor(
    private readonly area: StorageArea,
    private readonly client: MarkSink,
  ) {}

  /** Pending marks, oldest first. Converts the legacy topic-id list on first read. */
  async pending(): Promise<QueuedMark[]> {
    const items = await this.area.get(QUEUE_KEY);
    const value = items[QUEUE_KEY];
    const queue = Array.isArray(value) ? value.filter(isMark) : [];
    return this.migrateLegacy(queue);
  }

  /** Number of pending marks. */
  async count(): Promise<number> {
    return (await this.pending()).length;
  }

  /**
   * Marks a topic as known. Sends now when the core answers; when the core is
   * unreachable or too slow, queues it (last mark wins). Auth errors are rethrown, not queued.
   */
  async markKnown(topicId: number): Promise<MarkOutcome> {
    return this.mark({ kind: "topic", id: topicId, state: "known" });
  }

  /** Sets a concept mark. Same send-or-queue rules as `markKnown`. */
  async markConcept(conceptId: number, state: ConceptMark["state"]): Promise<MarkOutcome> {
    return this.mark({ kind: "concept", id: conceptId, state });
  }

  /**
   * Retries every pending mark, in order. Sent ones leave the queue; a 404 drops the item
   * (the topic or concept is gone); failures stay queued. An auth error stops the run and is
   * rethrown; the queue is saved first so nothing already sent comes back.
   */
  async flush(): Promise<FlushResult> {
    const result: FlushResult = { sent: 0, dropped: 0, kept: 0 };
    const queue = await this.pending();
    const remaining: QueuedMark[] = [];
    try {
      for (let i = 0; i < queue.length; i++) {
        const mark = queue[i];
        try {
          await this.send(mark);
          result.sent++;
        } catch (err) {
          if (err instanceof CoreHttpError && err.status === 404) {
            result.dropped++;
          } else if (err instanceof CoreAuthError) {
            remaining.push(...queue.slice(i));
            throw err;
          } else {
            // Timeout, offline or another HTTP error: keep it for the next flush.
            remaining.push(mark);
            result.kept++;
          }
        }
      }
    } finally {
      await this.saveAfterFlush(queue, remaining);
    }
    return result;
  }

  private async mark(mark: QueuedMark): Promise<MarkOutcome> {
    try {
      await this.send(mark);
      // Sent now: an older queued mark for the same item would overwrite it later, so drop it.
      await this.dequeue(mark);
      return "saved";
    } catch (err) {
      if (err instanceof CoreTimeoutError || err instanceof CoreOfflineError) {
        await this.enqueue(mark);
        return "queued";
      }
      throw err;
    }
  }

  private async send(mark: QueuedMark): Promise<void> {
    if (mark.kind === "topic") {
      await this.client.setKnown(mark.id);
    } else {
      await this.client.setConceptMark(mark.id, mark.state);
    }
  }

  /** Stores mark in place of any queued mark for the same item. */
  private async enqueue(mark: QueuedMark): Promise<void> {
    const queue = await this.pending();
    await this.save(withMark(queue, mark));
  }

  /** Removes the queued mark for the same item, if any. */
  private async dequeue(mark: QueuedMark): Promise<void> {
    const queue = await this.pending();
    const rest = queue.filter((m) => !sameMark(m, mark));
    if (rest.length !== queue.length) await this.save(rest);
  }

  /**
   * Rebuilds the stored queue after a flush. Marks queued while the flush awaited the network
   * are kept (they are newer); kept marks that a newer send or enqueue removed or replaced are dropped.
   */
  private async saveAfterFlush(snapshot: QueuedMark[], remaining: QueuedMark[]): Promise<void> {
    const current = await this.pending();
    const fresh = current.filter((c) => !snapshot.some((s) => sameState(s, c)));
    const kept = remaining.filter(
      (r) => current.some((c) => sameMark(c, r)) && !fresh.some((f) => sameMark(f, r)),
    );
    await this.save([...kept, ...fresh]);
  }

  /**
   * Moves the legacy topic-id list into the queue, then removes the legacy key so it is read
   * only once. Legacy marks go first: they are older than anything already queued, and a queued
   * mark for the same topic wins over the legacy one.
   */
  private async migrateLegacy(queue: QueuedMark[]): Promise<QueuedMark[]> {
    const items = await this.area.get(LEGACY_KEY);
    if (!(LEGACY_KEY in items)) return queue;
    const legacy = items[LEGACY_KEY];
    let legacyMarks: QueuedMark[] = [];
    if (Array.isArray(legacy)) {
      for (const id of legacy) {
        if (typeof id !== "number") continue;
        legacyMarks = withMark(legacyMarks, { kind: "topic", id, state: "known" });
      }
    }
    const merged = [...legacyMarks.filter((l) => !queue.some((q) => sameMark(q, l))), ...queue];
    await this.save(merged);
    await this.area.remove(LEGACY_KEY);
    return merged;
  }

  private async save(marks: QueuedMark[]): Promise<void> {
    await this.area.set({ [QUEUE_KEY]: marks });
  }
}
