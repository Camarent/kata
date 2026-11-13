import { describe, expect, it } from "vitest";
import { TokenStore, type StorageArea } from "../src/tokenStore";

/** In-memory stand-in for chrome.storage.local. */
function fakeArea(initial: Record<string, unknown> = {}): StorageArea & { data: Record<string, unknown> } {
  const data: Record<string, unknown> = { ...initial };
  return {
    data,
    async get(key: string) {
      return key in data ? { [key]: data[key] } : {};
    },
    async set(items: Record<string, unknown>) {
      Object.assign(data, items);
    },
    async remove(key: string) {
      delete data[key];
    },
  };
}

const session = { baseUrl: "http://127.0.0.1:8765", token: "secret-token" };

describe("TokenStore", () => {
  it("round-trips a saved session", async () => {
    const area = fakeArea();
    const store = new TokenStore(area);
    await store.saveSession(session);
    expect(await store.loadSession()).toEqual(session);
    expect(Object.keys(area.data)).toEqual(["kata.session"]);
  });

  it("returns null after clear", async () => {
    const store = new TokenStore(fakeArea());
    await store.saveSession(session);
    await store.clearSession();
    expect(await store.loadSession()).toBeNull();
  });

  it("returns null when nothing is stored", async () => {
    const store = new TokenStore(fakeArea());
    expect(await store.loadSession()).toBeNull();
  });

  it("loads a corrupt value as null", async () => {
    const store = new TokenStore(fakeArea({ "kata.session": { baseUrl: 42, token: "t" } }));
    expect(await store.loadSession()).toBeNull();
  });

  it("loads a non-object value as null", async () => {
    const store = new TokenStore(fakeArea({ "kata.session": "oops" }));
    expect(await store.loadSession()).toBeNull();
  });
});
