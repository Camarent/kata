import type { CoreClient, JobStatus as CoreJobStatus } from "./coreClient";

/** The part of `CoreClient` a scan needs; tests pass a fake with the same two methods. */
export type ScanClient = Pick<CoreClient, "enqueue" | "jobStatus">;

/** Topic of a tagged block, as returned by the service. */
export type ScanTopic = NonNullable<CoreJobStatus["topic"]>;

/** Outcome for one block. `topic` is null and `reason` set when the block failed or timed out. */
export interface ScanResult {
  blockId: string;
  topic: ScanTopic | null;
  known: boolean | null;
  reason?: string;
}

export interface ScanOptions {
  /** Delay between two `jobStatus` polls, in milliseconds. */
  pollMs: number;
  /** Time after which an unfinished job is reported as timed out, in milliseconds. */
  maxWaitMs: number;
  /** Called once per block as soon as its result is known. */
  onResult?: (result: ScanResult) => void;
}

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Enqueue every block text as a tagging job and poll each job until it is done,
 * failed or past `maxWaitMs`. A failing block never rejects the whole scan.
 * Results are returned in input order; `onResult` fires in completion order.
 */
export async function runScan(
  client: ScanClient,
  blocks: { id: string; text: string }[],
  opts: ScanOptions,
): Promise<ScanResult[]> {
  const scanOne = async (block: { id: string; text: string }): Promise<ScanResult> => {
    try {
      const jobId = await client.enqueue(block.text);
      const started = Date.now();
      for (;;) {
        const status = await client.jobStatus(jobId);
        if (status.status === "done") {
          if (status.topic === null) return { blockId: block.id, topic: null, known: null, reason: "no topic" };
          return { blockId: block.id, topic: status.topic, known: status.known };
        }
        if (status.status === "failed") {
          return { blockId: block.id, topic: null, known: null, reason: "job failed" };
        }
        if (Date.now() - started >= opts.maxWaitMs) {
          return { blockId: block.id, topic: null, known: null, reason: "timed out" };
        }
        await sleep(opts.pollMs);
      }
    } catch (err) {
      const reason = err instanceof Error ? err.message : String(err);
      return { blockId: block.id, topic: null, known: null, reason };
    }
  };

  const tasks = blocks.map(async (block) => {
    const result = await scanOne(block);
    opts.onResult?.(result);
    return result;
  });
  return Promise.all(tasks);
}
