import { describe, expect, it, vi } from "vitest";
import { runConceptScan, type ConceptScanClient, type ConceptScanPage } from "../src/conceptScan";
import type { JobStatus, ScanClassification } from "../src/coreClient";

const PAGE: ConceptScanPage = {
  pageKey: "https://ex.test/lesson",
  blocks: [
    { id: "b1", text: "The TCP handshake has three steps." },
    { id: "b2", text: "Call 555-0100." },
  ],
};
const OPTS = { pollMs: 0, maxWaitMs: 1000 };

const CACHED: ScanClassification = {
  areaId: 3,
  topicId: 7,
  area: "Networking",
  topic: "Transport",
  candidates: [],
};

const CLASSIFY_OUT = {
  areaId: 3,
  topicId: 7,
  area: "Networking",
  topic: "Transport",
  isNew: false,
  candidates: [{ topicId: 8, area: "Networking", topic: "Routing" }],
};

const EXTRACT_OUT = {
  areaId: 3,
  topicId: 7,
  blocks: [
    {
      blockId: "b1",
      concepts: [
        {
          word: "handshake",
          conceptId: 40,
          label: "Three-way handshake",
          definition: "SYN, SYN-ACK, ACK",
          state: "new",
          candidates: [],
        },
        {
          word: "steps",
          conceptId: 41,
          label: "Steps",
          definition: "ignored by the user",
          state: "ignored",
          candidates: [],
        },
      ],
    },
    {
      blockId: "b2",
      skipped: "not teachable",
      concepts: [],
    },
  ],
};

const done = (output: Record<string, unknown>): JobStatus => ({
  status: "done",
  topic: null,
  known: null,
  output,
});
const running: JobStatus = { status: "running", topic: null, known: null };
const failed: JobStatus = { status: "failed", topic: null, known: null };

interface FakeOptions {
  cached?: ScanClassification | null;
  classifyJob?: JobStatus[];
  extractJob?: JobStatus[];
  getClassificationError?: Error;
}

/**
 * Fake core: `classify` and `extract` jobs have their own status scripts; the last status repeats.
 * Job ids: 1 for classify, 2 for extract.
 */
function fakeClient(opts: FakeOptions = {}) {
  const scripts: Record<number, JobStatus[]> = {
    1: opts.classifyJob ?? [done(CLASSIFY_OUT)],
    2: opts.extractJob ?? [done(EXTRACT_OUT)],
  };
  const polls = new Map<number, number>();
  const client = {
    getClassification: vi.fn(async (_pageKey: string) => {
      if (opts.getClassificationError) throw opts.getClassificationError;
      return opts.cached === undefined ? null : opts.cached;
    }),
    scanClassify: vi.fn(async (_pageKey: string, _text: string, _taxonomy: string) => 1),
    scanExtract: vi.fn(async (_input: unknown) => 2),
    jobStatus: vi.fn(async (id: number) => {
      const script = scripts[id];
      const n = polls.get(id) ?? 0;
      polls.set(id, n + 1);
      return script[Math.min(n, script.length - 1)];
    }),
  };
  return client;
}

const asClient = (c: ReturnType<typeof fakeClient>): ConceptScanClient => c as unknown as ConceptScanClient;

describe("runConceptScan", () => {
  it("uses a cached classification and skips the classify job", async () => {
    const client = fakeClient({ cached: CACHED });
    const out = await runConceptScan(asClient(client), PAGE, OPTS);
    expect(client.scanClassify).not.toHaveBeenCalled();
    expect(client.scanExtract).toHaveBeenCalledTimes(1);
    expect(client.scanExtract.mock.calls[0][0]).toMatchObject({ areaId: 3, topicId: 7, area: "Networking", topic: "Transport" });
    expect(out).toMatchObject({ areaId: 3, topicId: 7, area: "Networking", topic: "Transport" });
  });

  it("classifies then extracts when there is no cached classification", async () => {
    const client = fakeClient({ cached: null });
    const out = await runConceptScan(asClient(client), PAGE, { ...OPTS, taxonomy: [{ area: "Networking", topic: "Transport" }] });
    expect(client.scanClassify).toHaveBeenCalledTimes(1);
    const [key, text, taxonomy] = client.scanClassify.mock.calls[0];
    expect(key).toBe(PAGE.pageKey);
    expect(text).toBe("The TCP handshake has three steps.\nCall 555-0100.");
    expect(JSON.parse(taxonomy)).toEqual([{ area: "Networking", topic: "Transport" }]);
    expect(client.scanExtract.mock.calls[0][0]).toMatchObject({ areaId: 3, topicId: 7, area: "Networking", topic: "Transport" });
    expect(out).toMatchObject({ areaId: 3, topicId: 7, area: "Networking", topic: "Transport" });
  });

  it("returns the blocks of the extract job, with ignored concepts removed", async () => {
    const client = fakeClient({ cached: CACHED });
    const out = await runConceptScan(asClient(client), PAGE, OPTS);
    if (!("blocks" in out)) throw new Error(`unexpected error ${out.error}`);
    expect(out.blocks).toHaveLength(2);
    expect(out.blocks[0].concepts.map((c) => c.word)).toEqual(["handshake"]);
    expect(out.blocks[1]).toEqual({ blockId: "b2", skipped: "not teachable", concepts: [] });
  });

  it("keeps a candidates item with conceptId null", async () => {
    const extract = {
      areaId: 3,
      topicId: 7,
      blocks: [
        {
          blockId: "b1",
          concepts: [
            { word: "sum", conceptId: null, label: "sum", definition: "", state: "new", candidates: [{ conceptId: 40, label: "Sum" }, { conceptId: 41, label: "Total" }] },
          ],
        },
      ],
    };
    const client = fakeClient({ cached: CACHED, extractJob: [done(extract)] });
    const out = await runConceptScan(asClient(client), PAGE, OPTS);
    if (!("blocks" in out)) throw new Error(`unexpected error ${out.error}`);
    expect(out.blocks[0].concepts).toHaveLength(1);
    expect(out.blocks[0].concepts[0].conceptId).toBeNull();
    expect(out.blocks[0].concepts[0].candidates).toHaveLength(2);
  });

  it("filters an item flagged ignored even when its state is not ignored", async () => {
    const extract = {
      areaId: 3,
      topicId: 7,
      blocks: [
        {
          blockId: "b1",
          concepts: [{ word: "flag", conceptId: 5, label: "Flag", definition: "", state: "known", candidates: [], ignored: true }],
        },
      ],
    };
    const client = fakeClient({ cached: CACHED, extractJob: [done(extract)] });
    const out = await runConceptScan(asClient(client), PAGE, OPTS);
    if (!("blocks" in out)) throw new Error(`unexpected error ${out.error}`);
    expect(out.blocks[0].concepts).toEqual([]);
  });

  it("returns an error when the extract job times out", async () => {
    const client = fakeClient({ cached: CACHED, extractJob: [running] });
    const out = await runConceptScan(asClient(client), PAGE, { pollMs: 0, maxWaitMs: 0 });
    expect(out).toEqual({ error: "timed out" });
  });

  it("returns an error when the classify job failed, and never extracts", async () => {
    const client = fakeClient({ cached: null, classifyJob: [failed] });
    const out = await runConceptScan(asClient(client), PAGE, OPTS);
    expect(out).toEqual({ error: "job failed" });
    expect(client.scanExtract).not.toHaveBeenCalled();
  });

  it("returns an error when the extract job failed", async () => {
    const client = fakeClient({ cached: CACHED, extractJob: [failed] });
    expect(await runConceptScan(asClient(client), PAGE, OPTS)).toEqual({ error: "job failed" });
  });

  it("returns an error instead of throwing when a core call throws", async () => {
    const client = fakeClient({ getClassificationError: new Error("core down") });
    expect(await runConceptScan(asClient(client), PAGE, OPTS)).toEqual({ error: "core down" });
  });

  it("returns an error when a cached classification has no area id", async () => {
    const client = fakeClient({ cached: { ...CACHED, areaId: undefined } });
    expect(await runConceptScan(asClient(client), PAGE, OPTS)).toEqual({ error: "classification has no area id" });
    expect(client.scanExtract).not.toHaveBeenCalled();
  });
});
