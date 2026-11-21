import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { activate, deactivate, INSTALL_COMMAND } from "../src/extension";
import { INFO_VIEW_ID } from "../src/infoView";
import { QUIET_MARK_MESSAGE } from "../src/diagnostics";
import { host, resetHost } from "./mocks/vscode";

const SERVER = "http://kata.test";
const uri = { toString: () => "file:///doc.ts", fsPath: "/doc.ts" };

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

    expect([...host.commands.keys()]).toEqual([INSTALL_COMMAND]);
    expect([...host.webviewProviders.keys()]).toEqual([INFO_VIEW_ID]);
    expect(host.diagnosticCollections).toEqual(["kata"]);
    expect(host.saveListeners).toHaveLength(1);
    expect(ctx.subscriptions).toHaveLength(4);
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
