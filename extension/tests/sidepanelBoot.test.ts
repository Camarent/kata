import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { execSync } from "node:child_process";
import { beforeAll, afterEach, describe, expect, it, vi } from "vitest";
import { bootPanel, type PanelChromeLike } from "../src/sidepanelBoot";
import type { PanelReply } from "../src/background";
import type { StorageArea } from "../src/tokenStore";

/** `npm --prefix extension test` runs with the extension folder as cwd. */
const EXTENSION_DIR = process.cwd();
/** The build runs tsc and esbuild; allow it a generous window on a cold cache. */
const BUILD_TIMEOUT_MS = 120_000;
const PAGE = "sidepanel.html";

/** Reads sidepanel.html and parses it; scripts are read from the parsed document. */
function parsedPage(): Document {
  const html = readFileSync(join(EXTENSION_DIR, PAGE), "utf8");
  return new DOMParser().parseFromString(html, "text/html");
}

/** In-memory storage area with the StorageArea shape. */
function memoryArea(initial: Record<string, unknown> = {}): StorageArea {
  const items = new Map<string, unknown>(Object.entries(initial));
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

/** Fake chrome for the side panel page: storage with the given session, and a stubbed message reply. */
function fakeChrome(reply: PanelReply = { ok: true }, session: unknown = null) {
  const sendMessage = vi.fn(async () => reply);
  const api: PanelChromeLike = {
    runtime: { sendMessage },
    storage: { local: memoryArea(session ? { "kata.session": session } : {}) },
  };
  return { api, sendMessage };
}

describe("sidepanel.html", () => {
  it("has no inline script: every script element has a src", () => {
    const scripts = Array.from(parsedPage().querySelectorAll("script"));
    expect(scripts.length).toBeGreaterThan(0);
    for (const script of scripts) {
      expect(script.getAttribute("src")).toBeTruthy();
      expect(script.textContent?.trim()).toBe("");
    }
  });

  it("loads the boot script as an external module", () => {
    const script = parsedPage().querySelector("script[src]");
    expect(script?.getAttribute("type")).toBe("module");
    expect(script?.getAttribute("src")).toBe("dist/sidepanelBoot.js");
  });
});

describe("built side panel boot script", () => {
  beforeAll(() => {
    execSync("npm run build", { cwd: EXTENSION_DIR, stdio: "pipe" });
  }, BUILD_TIMEOUT_MS);

  it("the file referenced by sidepanel.html exists after build", () => {
    const src = parsedPage().querySelector("script[src]")?.getAttribute("src") ?? "";
    expect(existsSync(join(EXTENSION_DIR, src))).toBe(true);
  });
});

describe("bootPanel", () => {
  let root: HTMLElement;

  afterEach(() => {
    root?.remove();
  });

  function mountPoint(): HTMLElement {
    root = document.createElement("main");
    root.id = "panel";
    document.body.append(root);
    return root;
  }

  it("shows the sign-in form when there is no stored session", async () => {
    const { api } = fakeChrome();
    await bootPanel(mountPoint(), api);
    expect(root.querySelector("form.signin")).not.toBeNull();
  });

  it("shows the status and empty state when a session is stored", async () => {
    const { api } = fakeChrome({ ok: true }, { baseUrl: "http://localhost:8000", token: "t" });
    await bootPanel(mountPoint(), api);
    expect(root.querySelector("form.signin")).toBeNull();
    expect(root.querySelector(".empty")?.textContent).toBe("Nothing scanned yet");
  });

  it("sends the typed sign-in values to the background as a panel message", async () => {
    const { api, sendMessage } = fakeChrome({ ok: true });
    await bootPanel(mountPoint(), api);
    const form = root.querySelector("form.signin") as HTMLFormElement;
    (form.querySelector('input[name="code"]') as HTMLInputElement).value = " 123456 ";
    (form.querySelector('input[name="deviceLabel"]') as HTMLInputElement).value = "laptop";
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1));
    expect(sendMessage).toHaveBeenCalledWith({
      type: "panel:signIn",
      input: { code: "123456", deviceLabel: "laptop" },
    });
  });

  it("shows the background error when sign-in is refused", async () => {
    const { api } = fakeChrome({ ok: false, error: "bad code" });
    await bootPanel(mountPoint(), api);
    const form = root.querySelector("form.signin") as HTMLFormElement;
    (form.querySelector('input[name="code"]') as HTMLInputElement).value = "000000";
    (form.querySelector('input[name="deviceLabel"]') as HTMLInputElement).value = "laptop";
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() => expect(root.querySelector(".status")).not.toBeNull());
    expect(root.querySelector("form.signin")).not.toBeNull();
  });
});
