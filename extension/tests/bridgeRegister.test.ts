import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BRIDGE_SCRIPT_ID,
  bridgeMatchPatterns,
  registerBridge,
  syncBridge,
  wireBridgeRegistration,
  type RegisteredScript,
  type ScriptingLike,
} from "../src/bridgeRegister";
import { TokenStore, type StorageArea } from "../src/tokenStore";

/** Fake `chrome.scripting` that records each call in order. */
function fakeScripting(unregisterError?: Error) {
  const calls: string[] = [];
  const registered: RegisteredScript[][] = [];
  const scripting: ScriptingLike = {
    async registerContentScripts(scripts) {
      calls.push("register");
      registered.push(scripts);
    },
    async unregisterContentScripts() {
      calls.push("unregister");
      if (unregisterError) throw unregisterError;
    },
  };
  return { scripting, calls, registered };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("bridgeMatchPatterns", () => {
  it("uses a wildcard host on the origin's scheme, so a non-default port still matches", () => {
    expect(bridgeMatchPatterns("http://127.0.0.1:8080")).toEqual(["http://*/c/*"]);
    expect(bridgeMatchPatterns("https://core.example.test:9443")).toEqual(["https://*/c/*"]);
  });

  it("follows the origin it is given, never a build-time default", () => {
    expect(bridgeMatchPatterns("https://kata.example.test")).toEqual(["https://*/c/*"]);
  });
});

/** In-memory storage area with the StorageArea shape. */
function memoryArea(): StorageArea {
  const items = new Map<string, unknown>();
  return {
    async get(key) {
      return items.has(key) ? { [key]: items.get(key) } : {};
    },
    async set(values) {
      for (const [key, value] of Object.entries(values)) items.set(key, value);
    },
    async remove(key) {
      items.delete(key);
    },
  };
}

/** A token store holding the session, or no session when `baseUrl` is undefined. */
async function storeWith(baseUrl: string | undefined): Promise<TokenStore> {
  const tokens = new TokenStore(memoryArea());
  if (baseUrl !== undefined) await tokens.saveSession({ baseUrl, token: "T" });
  return tokens;
}

/** Fake `chrome.runtime` and `chrome.permissions` that keep the listeners and fire them on demand. */
function fakeEvents() {
  const lifecycle: Array<() => void> = [];
  const removed: Array<(info: { origins?: string[] }) => void> = [];
  const hook = { addListener: (listener: () => void) => lifecycle.push(listener) };
  return {
    runtime: { onInstalled: hook, onStartup: hook },
    permissions: {
      onRemoved: { addListener: (listener: (info: { origins?: string[] }) => void) => removed.push(listener) },
    },
    lifecycle,
    removed,
  };
}

describe("syncBridge", () => {
  it("registers the bridge for the saved session's origin", async () => {
    const { scripting, registered } = fakeScripting();
    await syncBridge(scripting, await storeWith("http://127.0.0.1:8080/some/base"));
    expect(registered).toEqual([
      [expect.objectContaining({ id: BRIDGE_SCRIPT_ID, matches: ["http://*/c/*"] })],
    ]);
  });

  it("removes the bridge when no session is saved", async () => {
    const { scripting, calls, registered } = fakeScripting();
    await syncBridge(scripting, await storeWith(undefined));
    expect(calls).toEqual(["unregister"]);
    expect(registered).toEqual([]);
  });

  it("removes the bridge when the saved base URL is invalid", async () => {
    const { scripting, calls } = fakeScripting();
    await syncBridge(scripting, await storeWith("not a url"));
    expect(calls).toEqual(["unregister"]);
  });
});

describe("wireBridgeRegistration with the session", () => {
  it("syncs at wiring time, on install and on browser start, from the saved session", async () => {
    const events = fakeEvents();
    const { scripting, registered } = fakeScripting();
    const tokens = await storeWith("https://kata.example.test");
    wireBridgeRegistration(events.runtime, scripting, events.permissions, tokens);
    await vi.waitFor(() => expect(registered).toHaveLength(1));
    expect(events.lifecycle).toHaveLength(2);
    for (const fire of events.lifecycle) fire();
    await vi.waitFor(() => expect(registered).toHaveLength(3));
    expect(registered[2][0].matches).toEqual(["https://*/c/*"]);
  });

  it("still syncs on wiring when chrome.permissions is absent", async () => {
    const events = fakeEvents();
    const { scripting, calls } = fakeScripting();
    const tokens = await storeWith("http://127.0.0.1:8080");
    expect(() => wireBridgeRegistration(events.runtime, scripting, undefined, tokens)).not.toThrow();
    await vi.waitFor(() => expect(calls).toEqual(["unregister", "register"]));
    expect(events.removed).toHaveLength(0);
  });

  it("removes the bridge when the permission for the session's origin is removed", async () => {
    const events = fakeEvents();
    const { scripting, calls } = fakeScripting();
    const tokens = await storeWith("http://127.0.0.1:8080");
    wireBridgeRegistration(events.runtime, scripting, events.permissions, tokens);
    await vi.waitFor(() => expect(calls).toEqual(["unregister", "register"]));
    for (const fire of events.removed) fire({ origins: ["http://127.0.0.1:8080/*"] });
    await vi.waitFor(() => expect(calls).toEqual(["unregister", "register", "unregister"]));
  });

  it("keeps the bridge when the removed permission names another origin", async () => {
    const events = fakeEvents();
    const { scripting, calls } = fakeScripting();
    const tokens = await storeWith("http://127.0.0.1:8080");
    wireBridgeRegistration(events.runtime, scripting, events.permissions, tokens);
    await vi.waitFor(() => expect(calls).toEqual(["unregister", "register"]));
    for (const fire of events.removed) fire({ origins: ["https://other.test/*"] });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(calls).toEqual(["unregister", "register"]);
  });
});

describe("registerBridge", () => {
  it("unregisters the old bridge, then registers bridge.js on the course pages at document_start", async () => {
    const { scripting, calls, registered } = fakeScripting();
    await registerBridge(scripting, "http://127.0.0.1:8080");
    expect(calls).toEqual(["unregister", "register"]);
    expect(registered).toEqual([
      [
        {
          id: BRIDGE_SCRIPT_ID,
          matches: ["http://*/c/*"],
          js: ["bridge.js"],
          runAt: "document_start",
          persistAcrossSessions: true,
        },
      ],
    ]);
  });

  it("a missing earlier registration is not an error", async () => {
    const { scripting, registered } = fakeScripting(new Error("No script with id"));
    await registerBridge(scripting, "http://127.0.0.1:8080");
    expect(registered).toHaveLength(1);
  });

  it("a failed register rejects", async () => {
    const scripting: ScriptingLike = {
      registerContentScripts: async () => {
        throw new Error("Invalid match pattern");
      },
      unregisterContentScripts: async () => undefined,
    };
    await expect(registerBridge(scripting, "http://127.0.0.1:8080")).rejects.toThrow("Invalid match pattern");
  });
});

describe("wireBridgeRegistration failures", () => {
  it("logs a failed registration instead of throwing", async () => {
    const events = fakeEvents();
    const scripting: ScriptingLike = {
      registerContentScripts: async () => {
        throw new Error("boom");
      },
      unregisterContentScripts: async () => undefined,
    };
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    wireBridgeRegistration(events.runtime, scripting, events.permissions, await storeWith("http://127.0.0.1:8080"));
    await vi.waitFor(() => expect(log).toHaveBeenCalledTimes(1));
  });
});
