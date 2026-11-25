import type {
  CoreClient,
  JobStatus,
  ScanBlockOutput,
  ScanClassification,
  ScanTopicCandidate,
} from "./coreClient";

/** The part of `CoreClient` the concept scan needs; tests pass a fake with the same methods. */
export type ConceptScanClient = Pick<
  CoreClient,
  "getClassification" | "scanClassify" | "scanExtract" | "jobStatus"
>;

/** A page to scan: its key (URL without fragment) and its text blocks in page order. */
export interface ConceptScanPage {
  pageKey: string;
  blocks: { id: string; text: string }[];
}

export interface ConceptScanOptions {
  /** Delay between two `jobStatus` polls, in milliseconds. */
  pollMs: number;
  /** Time after which an unfinished job is reported as timed out, in milliseconds. */
  maxWaitMs: number;
  /** Visible taxonomy the classifier prefers; empty when the caller has none. */
  taxonomy?: { area: string; topic: string }[];
}

/** Result of a concept scan: the page's topic and the extracted concepts per block. */
export interface ConceptScanResult {
  areaId: number;
  topicId: number;
  area: string;
  topic: string;
  blocks: ScanBlockOutput[];
}

/** A failed scan: `error` is the reason, never a thrown exception. */
export interface ConceptScanError {
  error: string;
}

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Poll one job until it is done and return its stored output.
 * Throws with the reason when the job failed, has no output or runs past `maxWaitMs`.
 */
async function waitForOutput(
  client: ConceptScanClient,
  jobId: number,
  opts: ConceptScanOptions,
): Promise<Record<string, unknown>> {
  const started = Date.now();
  for (;;) {
    const status: JobStatus = await client.jobStatus(jobId);
    if (status.status === "done") {
      if (!status.output) throw new Error("job has no output");
      return status.output;
    }
    if (status.status === "failed") throw new Error("job failed");
    if (Date.now() - started >= opts.maxWaitMs) throw new Error("timed out");
    await sleep(opts.pollMs);
  }
}

/** Read a classify output into a classification; a malformed field throws. */
function readClassification(out: Record<string, unknown>): ScanClassification {
  const { areaId, topicId, area, topic, candidates } = out;
  if (typeof areaId !== "number" || typeof topicId !== "number") throw new Error("bad classification ids");
  if (typeof area !== "string" || typeof topic !== "string") throw new Error("bad classification names");
  if (!Array.isArray(candidates)) throw new Error("bad classification candidates");
  const list: ScanTopicCandidate[] = candidates.map((c: unknown) => {
    const item = c as Partial<ScanTopicCandidate>;
    if (typeof item.topicId !== "number" || typeof item.area !== "string" || typeof item.topic !== "string") {
      throw new Error("bad classification candidate");
    }
    return { topicId: item.topicId, area: item.area, topic: item.topic };
  });
  return { areaId, topicId, area, topic, candidates: list };
}

/** Drop concepts flagged ignored (defensive: the core already filters them). */
function withoutIgnored(blocks: ScanBlockOutput[]): ScanBlockOutput[] {
  return blocks.map((block) => ({
    ...block,
    concepts: block.concepts.filter((item) => {
      const state: string = item.state;
      const flagged = (item as { ignored?: boolean }).ignored === true;
      return state !== "ignored" && !flagged;
    }),
  }));
}

/**
 * Scan one page: classify it (or reuse the stored classification), then extract the
 * concepts of its blocks. Never throws: a failing or timed-out step returns `{ error }`.
 */
export async function runConceptScan(
  client: ConceptScanClient,
  page: ConceptScanPage,
  opts: ConceptScanOptions,
): Promise<ConceptScanResult | ConceptScanError> {
  try {
    let classification = await client.getClassification(page.pageKey);
    if (classification === null) {
      const text = page.blocks.map((block) => block.text).join("\n");
      const taxonomy = JSON.stringify(opts.taxonomy ?? []);
      const jobId = await client.scanClassify(page.pageKey, text, taxonomy);
      classification = readClassification(await waitForOutput(client, jobId, opts));
    }
    if (typeof classification.areaId !== "number") throw new Error("classification has no area id");

    const jobId = await client.scanExtract({
      areaId: classification.areaId,
      topicId: classification.topicId,
      blocks: page.blocks.map((block) => ({ blockId: block.id, text: block.text })),
      area: classification.area,
      topic: classification.topic,
      known: [],
    });
    const out = await waitForOutput(client, jobId, opts);
    const blocks = out.blocks;
    if (!Array.isArray(blocks)) throw new Error("bad extraction output");

    return {
      areaId: classification.areaId,
      topicId: classification.topicId,
      area: classification.area,
      topic: classification.topic,
      blocks: withoutIgnored(blocks as ScanBlockOutput[]),
    };
  } catch (err) {
    return { error: err instanceof Error ? err.message : String(err) };
  }
}
