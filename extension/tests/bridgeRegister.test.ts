import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BRIDGE_SCRIPT_ID,
  bridgeMatchPatterns,
  registerBridge,
  wireBridgeRegistration,
  type RegisteredScript,
  type ScriptingLike,
} from "../src/bridgeRegister";
import { CORE_ORIGIN } from "../src/config";

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

  it("defaults to the configured core origin", () => {
    expect(bridgeMatchPatterns()).toEqual(bridgeMatchPatterns(CORE_ORIGIN));
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

describe("wireBridgeRegistration", () => {
  it("registers on install and again on browser start", async () => {
    const listeners: Array<() => void> = [];
    const hook = { addListener: (listener: () => void) => listeners.push(listener) };
    const { scripting, registered } = fakeScripting();
    wireBridgeRegistration({ onInstalled: hook, onStartup: hook }, scripting, "http://127.0.0.1:8080");
    expect(listeners).toHaveLength(2);
    for (const fire of listeners) fire();
    await vi.waitFor(() => expect(registered).toHaveLength(2));
  });

  it("logs a failed registration instead of throwing", async () => {
    const listeners: Array<() => void> = [];
    const hook = { addListener: (listener: () => void) => listeners.push(listener) };
    const scripting: ScriptingLike = {
      registerContentScripts: async () => {
        throw new Error("boom");
      },
      unregisterContentScripts: async () => undefined,
    };
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    wireBridgeRegistration({ onInstalled: hook, onStartup: hook }, scripting, "http://127.0.0.1:8080");
    listeners[0]();
    await vi.waitFor(() => expect(log).toHaveBeenCalledTimes(1));
  });
});
