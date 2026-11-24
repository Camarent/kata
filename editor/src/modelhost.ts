// Modelhost commands: queue one modelhost.* job on core (POST /jobs), poll it (GET /jobs/{id})
// until it ends, and turn the worker's answer into one line for the user. Same server URL and
// bearer token as the poster; the answer is `{ok, text}` (core/kata_core/modelhost/job_kinds.py).
import type { KataConfig } from "./config";
import type { FetchFn } from "./poster";

export const UP_KIND = "modelhost.up";
export const USE_KIND = "modelhost.use";
export const MEASURE_KIND = "modelhost.measure";
export const STATUS_KIND = "modelhost.status";

// Command id -> job kind. The command ids are registered in extension.ts and package.json.
export const MODELHOST_COMMAND_KINDS: Readonly<Record<string, string>> = {
  "kata.modelhostUp": UP_KIND,
  "kata.modelhostUse": USE_KIND,
  "kata.modelhostMeasure": MEASURE_KIND,
  "kata.modelhostStatus": STATUS_KIND,
};

// Engines accepted by modelhost.use (core/kata_core/modelhost/spec.py ENGINES).
export const USE_ENGINES: readonly string[] = ["ollama", "strata", "none"];

export const POLL_INTERVAL_MS = 1000;
export const MAX_POLLS = 120;

export type Sleep = (ms: number) => Promise<void>;

export interface PollSettings {
  intervalMs: number;
  maxPolls: number;
}

export type ModelhostResult =
  | { status: "done"; ok: boolean; text: string }
  | { status: "error"; reason: string };

// The payload core expects for `kind`. modelhost.use needs the engine; the other kinds take `{}`.
export function payloadFor(kind: string, engine?: string): string {
  if (kind === USE_KIND) {
    return JSON.stringify({ engine });
  }
  return "{}";
}

// Queues the job, then polls it until it is done or failed. Never throws: every failure is a
// status "error" with a reason.
export async function runModelhostJob(
  cfg: KataConfig,
  kind: string,
  payload: string,
  fetchFn: FetchFn,
  sleep: Sleep,
  settings: PollSettings,
): Promise<ModelhostResult> {
  const headers = { "Content-Type": "application/json", Authorization: `Bearer ${cfg.token}` };
  let enqueued: Response;
  try {
    enqueued = await fetchFn(`${cfg.serverUrl}/jobs`, {
      method: "POST",
      headers,
      body: JSON.stringify({ kind, payload }),
    });
  } catch (err) {
    return { status: "error", reason: err instanceof Error ? err.message : String(err) };
  }
  if (enqueued.status !== 200) {
    return { status: "error", reason: `enqueue failed: HTTP ${enqueued.status}` };
  }
  const id = (await readJson(enqueued)) as { id?: unknown } | undefined;
  if (typeof id?.id !== "number") {
    return { status: "error", reason: "enqueue answer has no job id" };
  }
  for (let poll = 0; poll < settings.maxPolls; poll++) {
    let answer: Response;
    try {
      answer = await fetchFn(`${cfg.serverUrl}/jobs/${id.id}`, { method: "GET", headers });
    } catch (err) {
      return { status: "error", reason: err instanceof Error ? err.message : String(err) };
    }
    if (answer.status !== 200) {
      return { status: "error", reason: `job status failed: HTTP ${answer.status}` };
    }
    const job = (await readJson(answer)) as { status?: unknown; output?: unknown } | undefined;
    if (job?.status === "done") {
      return outputResult(job.output);
    }
    if (job?.status === "failed") {
      return { status: "error", reason: "job failed" };
    }
    await sleep(settings.intervalMs);
  }
  return { status: "error", reason: `no answer after ${settings.maxPolls} polls` };
}

// Reads a JSON body; undefined when the body is not JSON.
async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

function outputResult(output: unknown): ModelhostResult {
  const out = output as { ok?: unknown; text?: unknown } | null | undefined;
  if (typeof out?.ok !== "boolean" || typeof out?.text !== "string") {
    return { status: "error", reason: "job output is not a modelhost answer" };
  }
  return { status: "done", ok: out.ok, text: out.text };
}

// The one line shown to the user for a finished or failed command.
export function resultMessage(kind: string, result: ModelhostResult): string {
  if (result.status === "error") {
    return `Kata: ${kind} error: ${result.reason}`;
  }
  return `Kata: ${kind} ${result.ok ? "ok" : "failed"}: ${result.text}`;
}
