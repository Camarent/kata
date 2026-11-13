import { CoreAuthError, CoreHttpError, CoreOfflineError, CoreTimeoutError } from "./coreClient";
import type { StorageArea } from "./tokenStore";

/** Storage key holding the pending topic ids as one array. */
const PENDING_KEY = "kata.pending";

/** The part of CoreClient the queue needs; injected so tests can fake it. */
export interface MarkSink {
  setKnown(topicId: number): Promise<void>;
}

/** Outcome of `markKnown`: sent now, or kept for a later `flush`. */
export type MarkOutcome = "saved" | "queued";

/** Counts from one `flush` run. */
export interface FlushResult {
  /** Sent to the core now. */
  sent: number;
  /** Dropped because the core answered 404 (topic gone). */
  dropped: number;
  /** Still pending after the run (core unreachable). */
  kept: number;
}

/** True when value is an array of numbers (the stored pending list). */
function isIdList(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((v) => typeof v === "number");
}

/** Mark-known writes that survive a dropped connection: failures wait in storage. */
export class OfflineQueue {
  constructor(
    private readonly area: StorageArea,
    private readonly client: MarkSink,
  ) {}

  /** Topic ids waiting to be sent, oldest first. */
  async pending(): Promise<number[]> {
    const items = await this.area.get(PENDING_KEY);
    const value = items[PENDING_KEY];
    return isIdList(value) ? value : [];
  }

  /**
   * Marks a topic as known. Sends now when the core answers; when the core is
   * unreachable or too slow, queues it (once). Auth errors are rethrown, not queued.
   */
  async markKnown(topicId: number): Promise<MarkOutcome> {
    try {
      await this.client.setKnown(topicId);
      return "saved";
    } catch (err) {
      if (err instanceof CoreTimeoutError || err instanceof CoreOfflineError) {
        await this.enqueue(topicId);
        return "queued";
      }
      throw err;
    }
  }

  /**
   * Retries every pending mark. Sent ones leave the queue; a 404 drops the item
   * (the topic is gone); failures stay queued. An auth error stops the run and is
   * rethrown; the queue is saved first so nothing already sent comes back.
   */
  async flush(): Promise<FlushResult> {
    const result: FlushResult = { sent: 0, dropped: 0, kept: 0 };
    const queue = await this.pending();
    const remaining: number[] = [];
    try {
      for (let i = 0; i < queue.length; i++) {
        const topicId = queue[i];
        try {
          await this.client.setKnown(topicId);
          result.sent++;
        } catch (err) {
          if (err instanceof CoreHttpError && err.status === 404) {
            result.dropped++;
          } else if (err instanceof CoreAuthError) {
            remaining.push(...queue.slice(i));
            throw err;
          } else {
            // Timeout, offline or another HTTP error: keep it for the next flush.
            remaining.push(topicId);
            result.kept++;
          }
        }
      }
    } finally {
      await this.save(remaining);
    }
    return result;
  }

  /** Appends topicId unless it is already pending. */
  private async enqueue(topicId: number): Promise<void> {
    const queue = await this.pending();
    if (queue.includes(topicId)) return;
    await this.save([...queue, topicId]);
  }

  private async save(ids: number[]): Promise<void> {
    await this.area.set({ [PENDING_KEY]: ids });
  }
}
