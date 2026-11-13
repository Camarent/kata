// E2E driver: runs the real extension modules (scanner, scan session, core client,
// offline queue) against a live core. Bundled by esbuild and run with node by
// tests/e2e/test_driver.py. Input: one JSON object in argv[2]. Output: one JSON line on stdout.
import { JSDOM } from "jsdom";
import { scanBlocks } from "../../extension/src/scanner";
import { runScan, type ScanResult } from "../../extension/src/scanSession";
import { CoreClient } from "../../extension/src/coreClient";
import { OfflineQueue } from "../../extension/src/offlineQueue";
import type { StorageArea } from "../../extension/src/tokenStore";

interface DriverInput {
  baseUrl: string;
  code: string;
  html: string;
  pollMs: number;
  maxWaitMs: number;
}

function parseInput(raw: string | undefined): DriverInput {
  if (raw === undefined) throw new Error("missing JSON input in argv[2]");
  const value = JSON.parse(raw) as Partial<DriverInput>;
  if (typeof value.baseUrl !== "string") throw new Error("input.baseUrl must be a string");
  if (typeof value.code !== "string") throw new Error("input.code must be a string");
  if (typeof value.html !== "string") throw new Error("input.html must be a string");
  if (typeof value.pollMs !== "number") throw new Error("input.pollMs must be a number");
  if (typeof value.maxWaitMs !== "number") throw new Error("input.maxWaitMs must be a number");
  return value as DriverInput;
}

/** In-memory stand-in for chrome.storage.local, same shape as the extension's StorageArea. */
function memoryArea(): StorageArea {
  const data: Record<string, unknown> = {};
  return {
    async get(key) {
      return key in data ? { [key]: data[key] } : {};
    },
    async set(items) {
      Object.assign(data, items);
    },
    async remove(key) {
      delete data[key];
    },
  };
}

async function main(): Promise<void> {
  const input = parseInput(process.argv[2]);
  const dom = new JSDOM(input.html);
  // The scanner reads the browser global `Node` (Node.TEXT_NODE); expose jsdom's as in a page.
  Object.assign(globalThis, { Node: dom.window.Node });
  const blocks = scanBlocks(dom.window.document as unknown as Document);
  const client = new CoreClient({ baseUrl: input.baseUrl, timeoutMs: input.maxWaitMs });
  await client.enrol(input.code, "e2e-ext");

  const results: ScanResult[] = await runScan(
    client,
    blocks.map((b) => ({ id: b.id, text: b.text })),
    { pollMs: input.pollMs, maxWaitMs: input.maxWaitMs },
  );

  const first = results.find((r) => r.topic !== null);
  if (!first || first.topic === null) throw new Error("no block got a topic; nothing to mark");
  const queue = new OfflineQueue(memoryArea(), client);
  await queue.markKnown(first.topic.id);

  const marksAfterPress = await client.listMarks();
  const out = {
    blocks: blocks.map((b) => ({ id: b.id, text: b.text })),
    results,
    marksAfterPress,
  };
  process.stdout.write(`${JSON.stringify(out)}\n`);
}

main().catch((err: unknown) => {
  const message = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
  process.stderr.write(`${message}\n`);
  process.exit(1);
});
