import { describe, expect, it, vi } from "vitest";
import type { KataConfig } from "../src/config";
import {
  MODELHOST_COMMAND_KINDS,
  payloadFor,
  resultMessage,
  runModelhostJob,
  USE_ENGINES,
  type ModelhostResult,
} from "../src/modelhost";

const cfg: KataConfig = { serverUrl: "http://kata.test", token: "tok-123", stopPatterns: [] };
const settings = { intervalMs: 5, maxPolls: 3 };
const noSleep = () => Promise.resolve();

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

// Serves the given answers in order; the last one repeats. Each answer is built per call, so a
// body is never read twice.
function fetchSequence(...answers: Array<() => Response>) {
  let i = 0;
  return vi.fn((_input: string, _init: RequestInit) => {
    const answer = answers[Math.min(i, answers.length - 1)];
    i++;
    return Promise.resolve(answer());
  });
}

const enqueued = (id: number) => () => json({ id });
const done = (ok: boolean, text: string) => () =>
  json({ status: "done", topic: null, known: null, output: { ok, text } });
const status = (value: string) => () => json({ status: value, topic: null, known: null, output: null });

describe("command to job kind", () => {
  it("maps each modelhost command to its job kind", () => {
    expect(MODELHOST_COMMAND_KINDS).toEqual({
      "kata.modelhostUp": "modelhost.up",
      "kata.modelhostUse": "modelhost.use",
      "kata.modelhostMeasure": "modelhost.measure",
      "kata.modelhostStatus": "modelhost.status",
    });
  });

  it("builds the payload core accepts: {} for three kinds, the engine for use", () => {
    expect(payloadFor("modelhost.up")).toBe("{}");
    expect(payloadFor("modelhost.measure")).toBe("{}");
    expect(payloadFor("modelhost.status")).toBe("{}");
    expect(payloadFor("modelhost.use", "strata")).toBe('{"engine":"strata"}');
    expect(USE_ENGINES).toEqual(["ollama", "strata", "none"]);
  });
});

describe("POST body per command", () => {
  it.each(Object.entries(MODELHOST_COMMAND_KINDS))(
    "%s enqueues its kind and payload with the bearer token",
    async (_command, kind) => {
      const fetchFn = fetchSequence(enqueued(7), done(true, "fine"));

      await runModelhostJob(cfg, kind, payloadFor(kind, "ollama"), fetchFn, noSleep, settings);

      const [url, init] = fetchFn.mock.calls[0];
      expect(url).toBe("http://kata.test/jobs");
      expect(init.method).toBe("POST");
      expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-123");
      expect(JSON.parse(String(init.body))).toEqual({ kind, payload: payloadFor(kind, "ollama") });
    },
  );

  it("polls GET /jobs/{id} with the same token", async () => {
    const fetchFn = fetchSequence(enqueued(42), done(true, "up"));

    await runModelhostJob(cfg, "modelhost.up", "{}", fetchFn, noSleep, settings);

    const [url, init] = fetchFn.mock.calls[1];
    expect(url).toBe("http://kata.test/jobs/42");
    expect(init.method).toBe("GET");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-123");
  });
});

describe("polling", () => {
  it("returns the worker text once the job is done", async () => {
    const fetchFn = fetchSequence(enqueued(1), status("leased"), done(true, "model is up"));
    const sleep = vi.fn(noSleep);

    const result = await runModelhostJob(cfg, "modelhost.up", "{}", fetchFn, sleep, settings);

    expect(result).toEqual({ status: "done", ok: true, text: "model is up" });
    expect(sleep).toHaveBeenCalledTimes(1);
    expect(sleep).toHaveBeenCalledWith(settings.intervalMs);
  });

  it("reports a failed job as an error", async () => {
    const fetchFn = fetchSequence(enqueued(1), status("failed"));

    const result = await runModelhostJob(cfg, "modelhost.status", "{}", fetchFn, noSleep, settings);

    expect(result).toEqual({ status: "error", reason: "job failed" });
  });

  it("gives up after maxPolls", async () => {
    const fetchFn = fetchSequence(enqueued(1), status("queued"));

    const result = await runModelhostJob(cfg, "modelhost.up", "{}", fetchFn, noSleep, settings);

    expect(result).toEqual({ status: "error", reason: `no answer after ${settings.maxPolls} polls` });
    expect(fetchFn).toHaveBeenCalledTimes(1 + settings.maxPolls);
  });

  it("rejects a done job whose output is not a modelhost answer", async () => {
    const fetchFn = fetchSequence(enqueued(1), () => json({ status: "done", output: { text: 3 } }));

    const result = await runModelhostJob(cfg, "modelhost.up", "{}", fetchFn, noSleep, settings);

    expect(result).toEqual({ status: "error", reason: "job output is not a modelhost answer" });
  });

  it("reports a refused enqueue with its HTTP status and queues nothing more", async () => {
    const fetchFn = fetchSequence(() => json({ detail: "bad" }, 422));

    const result = await runModelhostJob(cfg, "modelhost.use", '{"engine":"x"}', fetchFn, noSleep, settings);

    expect(result).toEqual({ status: "error", reason: "enqueue failed: HTTP 422" });
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it("reports a network failure as an error", async () => {
    const fetchFn = vi.fn((_input: string, _init: RequestInit) => Promise.reject(new Error("offline")));

    const result = await runModelhostJob(cfg, "modelhost.up", "{}", fetchFn, noSleep, settings);

    expect(result).toEqual({ status: "error", reason: "offline" });
  });
});

describe("result display", () => {
  it("shows the worker text for a successful job", () => {
    const result: ModelhostResult = { status: "done", ok: true, text: "model is up" };
    expect(resultMessage("modelhost.up", result)).toBe("Kata: modelhost.up ok: model is up");
  });

  it("shows the worker text for a job that answered not ok", () => {
    const result: ModelhostResult = { status: "done", ok: false, text: "no GPU" };
    expect(resultMessage("modelhost.measure", result)).toBe("Kata: modelhost.measure failed: no GPU");
  });

  it("shows the reason for an error", () => {
    const result: ModelhostResult = { status: "error", reason: "job failed" };
    expect(resultMessage("modelhost.status", result)).toBe("Kata: modelhost.status error: job failed");
  });
});
