import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { activate, deactivate, INSTALL_COMMAND } from "../src/extension";
import { INFO_VIEW_ID } from "../src/infoView";
import { QUIET_MARK_MESSAGE } from "../src/diagnostics";
import { MODELHOST_COMMAND_KINDS } from "../src/modelhost";
import { host, resetHost } from "./mocks/vscode";

const SERVER = "http://kata.test";
const MODELHOST_IDS = Object.keys(MODELHOST_COMMAND_KINDS);
const uri = { toString: () => "file:///doc.ts", fsPath: "/doc.ts" };

// Answers POST /jobs with id 5 and GET /jobs/5 with a done job carrying `{ok, text}`.
function modelhostFetch(ok: boolean, text: string) {
  return vi.fn((input: string, init: RequestInit) => {
    const body =
      init.method === "POST"
        ? { id: 5 }
        : { status: "done", topic: null, known: null, output: { ok, text } };
    return Promise.resolve(jsonResponse(body));
  });
}

function document(text: string) {
  return { uri, languageId: "typescript", getText: () => text };
}

function context() {
  return { subscriptions: [] as { dispose(): void }[] };
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

beforeEach(() => {
  resetHost();
  host.settings = {
    "kata.serverUrl": SERVER,
    "kata.token": "tok-123",
    "kata.stopPatterns": ["secret"],
  };
});

afterEach(() => {
  vi.unstubAllGlobals();
  resetHost();
});

describe("activate", () => {
  it("registers the install command, the info view, a diagnostic collection and the save listener", () => {
    const ctx = context();

    activate(ctx);

    expect([...host.commands.keys()]).toEqual([INSTALL_COMMAND, ...MODELHOST_IDS]);
    expect([...host.webviewProviders.keys()]).toEqual([INFO_VIEW_ID]);
    expect(host.diagnosticCollections).toEqual(["kata"]);
    expect(host.saveListeners).toHaveLength(1);
    expect(ctx.subscriptions).toHaveLength(4 + MODELHOST_IDS.length);
  });

  it("registers the four modelhost commands exactly as package.json contributes them", () => {
    const manifest = JSON.parse(readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf8")) as {
      contributes: { commands: { command: string }[] };
      activationEvents: string[];
    };
    const contributed = manifest.contributes.commands.map((c) => c.command);

    activate(context());

    for (const id of MODELHOST_IDS) {
      expect(host.commands.has(id)).toBe(true);
      expect(contributed).toContain(id);
      expect(manifest.activationEvents).toContain(`onCommand:${id}`);
    }
    expect(contributed).toEqual([INSTALL_COMMAND, ...MODELHOST_IDS]);
  });

  it("posts the modelhost.up job and shows the worker text", async () => {
    const fetchMock = modelhostFetch(true, "model is up");
    vi.stubGlobal("fetch", fetchMock);
    activate(context());

    await host.commands.get("kata.modelhostUp")?.();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${SERVER}/jobs`);
    expect(JSON.parse(String(init.body))).toEqual({ kind: "modelhost.up", payload: "{}" });
    expect(host.messages).toEqual(["Kata: modelhost.up ok: model is up"]);
  });

  it("asks for the engine on modelhost.use and posts it", async () => {
    const fetchMock = modelhostFetch(true, "engine set");
    vi.stubGlobal("fetch", fetchMock);
    host.quickPickAnswer = "strata";
    activate(context());

    await host.commands.get("kata.modelhostUse")?.();

    expect(host.quickPickItems).toEqual([["ollama", "strata", "none"]]);
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init.body))).toEqual({ kind: "modelhost.use", payload: '{"engine":"strata"}' });
    expect(host.messages).toEqual(["Kata: modelhost.use ok: engine set"]);
  });

  it("queues nothing when the engine pick is cancelled", async () => {
    const fetchMock = modelhostFetch(true, "unused");
    vi.stubGlobal("fetch", fetchMock);
    host.quickPickAnswer = undefined;
    activate(context());

    await host.commands.get("kata.modelhostUse")?.();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(host.messages).toEqual([]);
  });

  it("posts one editor.save event when a document is saved", async () => {
    const fetchMock = vi.fn((_input: string, _init: RequestInit) =>
      Promise.resolve(jsonResponse({ messages: [] })),
    );
    vi.stubGlobal("fetch", fetchMock);
    activate(context());

    await host.saveListeners[0](document("const a = 1;"));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${SERVER}/v1/events`);
    const sent = JSON.parse(String(init.body)) as { events: { type: string; payload: unknown }[] };
    expect(sent.events).toHaveLength(1);
    expect(sent.events[0].type).toBe("editor.save");
    expect(sent.events[0].payload).toEqual({ language: "typescript" });
  });

  it("posts nothing when the saved text matches a stop pattern", async () => {
    const fetchMock = vi.fn((_input: string, _init: RequestInit) =>
      Promise.resolve(jsonResponse({ messages: [] })),
    );
    vi.stubGlobal("fetch", fetchMock);
    activate(context());

    await host.saveListeners[0](document("const token = 'secret';"));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sets the quiet-mark diagnostic when the save answer carries a quiet_mark message", async () => {
    const message = {
      id: 1,
      kind: "quiet_mark",
      body: { at: "2026-11-21T10:00:00Z", detail: {} },
      created_at: "2026-11-21T10:00:01Z",
    };
    vi.stubGlobal("fetch", () => Promise.resolve(jsonResponse({ messages: [message] })));
    activate(context());

    await host.saveListeners[0](document("const a = 1;"));

    expect(host.diagnosticCalls).toHaveLength(1);
    expect(host.diagnosticCalls[0].op).toBe("set");
    const diagnostics = host.diagnosticCalls[0].diagnostics ?? [];
    expect(diagnostics).toHaveLength(1);
    expect((diagnostics[0] as { message: string }).message).toBe(QUIET_MARK_MESSAGE);
  });
});

describe("deactivate", () => {
  it("runs without throwing", () => {
    expect(() => deactivate()).not.toThrow();
  });
});
