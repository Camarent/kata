import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { execSync } from "node:child_process";
import { beforeAll, afterEach, describe, expect, it, vi } from "vitest";
import { bootPanel, type OriginsRequest, type PanelChromeLike } from "../src/sidepanelBoot";
import type { PanelMessage, PanelReply } from "../src/background";
import type { PanelHandlers, PanelState } from "../src/sidepanel";
import type { StorageArea } from "../src/tokenStore";

/** The handlers bootPanel hands to renderPanel; the courses regenerate action has no other DOM entry point yet. */
const captured = vi.hoisted(() => ({ handlers: undefined as PanelHandlers | undefined }));
vi.mock("../src/sidepanel", async (importOriginal) => {
  const original = await importOriginal<typeof import("../src/sidepanel")>();
  return {
    ...original,
    renderPanel: (root: HTMLElement, state: PanelState, handlers: PanelHandlers) => {
      captured.handlers = handlers;
      original.renderPanel(root, state, handlers);
    },
  };
});

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

/** Fake origin permissions: request answers `granted`, remove records calls, `fire` runs onRemoved listeners. */
function fakePermissions(granted = true) {
  const request = vi.fn(async (_request: OriginsRequest) => granted);
  const remove = vi.fn(async (_request: OriginsRequest) => true);
  const listeners: Array<(removed: { origins?: string[] }) => void> = [];
  const onRemoved = { addListener: (listener: (removed: { origins?: string[] }) => void) => void listeners.push(listener) };
  const fire = (origins: string[]) => listeners.forEach((listener) => listener({ origins }));
  return { request, remove, onRemoved, fire };
}

/** Fake chrome for the side panel page: storage with the given session, a stubbed message reply and fake permissions. */
function fakeChrome(
  reply: PanelReply = { ok: true },
  session: unknown = null,
  permissions = fakePermissions(),
) {
  const sendMessage = vi.fn(async (_message: PanelMessage) => reply);
  const api: PanelChromeLike = {
    runtime: { sendMessage },
    storage: { local: memoryArea(session ? { "kata.session": session } : {}) },
    permissions,
  };
  return { api, sendMessage, permissions };
}

/** Fills and submits the first-run form (or the change form) with the given values. */
function submitSignIn(panel: HTMLElement, baseUrl: string, code: string, deviceLabel: string): void {
  const form = panel.querySelector("form.signin") as HTMLFormElement;
  (form.querySelector('input[name="baseUrl"]') as HTMLInputElement).value = baseUrl;
  (form.querySelector('input[name="code"]') as HTMLInputElement).value = code;
  (form.querySelector('input[name="deviceLabel"]') as HTMLInputElement).value = deviceLabel;
  form.dispatchEvent(new Event("submit", { cancelable: true }));
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
    expect(script?.getAttribute("src")).toBe("sidepanelBoot.js");
  });
});

describe("built side panel boot script", () => {
  beforeAll(() => {
    execSync("npm run build", { cwd: EXTENSION_DIR, stdio: "pipe" });
  }, BUILD_TIMEOUT_MS);

  it("the file referenced by sidepanel.html exists after build", () => {
    const src = parsedPage().querySelector("script[src]")?.getAttribute("src") ?? "";
    for (const browser of ["firefox", "chrome"]) {
      expect(existsSync(join(EXTENSION_DIR, "dist", browser, src))).toBe(true);
    }
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

  it("requests the server origin, then sends the typed sign-in values to the background", async () => {
    const { api, sendMessage, permissions } = fakeChrome({ ok: true });
    await bootPanel(mountPoint(), api);
    submitSignIn(root, "https://kata.example.org/", " 123456 ", "laptop");
    await vi.waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith({
        type: "panel:signIn",
        input: { baseUrl: "https://kata.example.org", code: "123456", deviceLabel: "laptop" },
      }),
    );
    expect(permissions.request).toHaveBeenCalledWith({ origins: ["https://kata.example.org/*"] });
    expect(permissions.request.mock.invocationCallOrder[0]).toBeLessThan(sendMessage.mock.invocationCallOrder[0]);
  });

  it("a refused permission shows the denied text, stores nothing and sends no sign-in", async () => {
    const { api, sendMessage, permissions } = fakeChrome({ ok: true }, null, fakePermissions(false));
    await bootPanel(mountPoint(), api);
    submitSignIn(root, "https://kata.example.org", "123456", "laptop");
    await vi.waitFor(() => expect(root.querySelector("p.status")?.textContent).toMatch(/not granted/));
    expect(permissions.request).toHaveBeenCalledTimes(1);
    expect(sendMessage).not.toHaveBeenCalled();
    expect(root.querySelector("form.signin")).not.toBeNull();
  });

  it("an invalid URL shows its reason and asks for no permission", async () => {
    const { api, sendMessage, permissions } = fakeChrome();
    await bootPanel(mountPoint(), api);
    submitSignIn(root, "not a url", "123456", "laptop");
    await vi.waitFor(() => expect(root.querySelector("p.status")?.textContent).toBe("server URL is not a valid URL"));
    expect(permissions.request).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("shows the background error text when sign-in is refused and releases the new origin", async () => {
    const { api, permissions } = fakeChrome({ ok: false, error: "core rejected the credentials" });
    await bootPanel(mountPoint(), api);
    submitSignIn(root, "https://kata.example.org", "000000", "laptop");
    await vi.waitFor(() => expect(root.querySelector("p.status")?.textContent).toBe("core rejected the credentials"));
    expect(root.querySelector("form.signin")).not.toBeNull();
    expect(permissions.remove).toHaveBeenCalledWith({ origins: ["https://kata.example.org/*"] });
  });

  it("shows each server error text the background sends (unreachable, not kata)", async () => {
    for (const error of ["core is unreachable", "address does not answer as a kata core"]) {
      const { api } = fakeChrome({ ok: false, error });
      await bootPanel(mountPoint(), api);
      submitSignIn(root, "https://kata.example.org", "123456", "laptop");
      await vi.waitFor(() => expect(root.querySelector("p.status")?.textContent).toBe(error));
      root.remove();
    }
  });

  it("Disconnect removes the session origin, sends panel:disconnect and draws first-run", async () => {
    const { api, sendMessage, permissions } = fakeChrome({ ok: true }, signedIn);
    await bootPanel(mountPoint(), api);
    root.querySelector<HTMLButtonElement>("button.disconnect")!.click();
    await vi.waitFor(() => expect(root.querySelector("form.signin")).not.toBeNull());
    expect(permissions.remove).toHaveBeenCalledWith({ origins: ["http://localhost:8000/*"] });
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:disconnect" });
    expect(root.querySelector<HTMLInputElement>('input[name="baseUrl"]')!.value).toBe("");
  });

  it("Change server asks for the new origin, signs in, then removes the old origin", async () => {
    const { api, sendMessage, permissions } = fakeChrome({ ok: true }, signedIn);
    await bootPanel(mountPoint(), api);
    root.querySelector<HTMLButtonElement>("button.change-server")!.click();
    expect(root.querySelector<HTMLInputElement>('input[name="baseUrl"]')!.value).toBe("http://localhost:8000");
    submitSignIn(root, "https://kata.example.org", "123456", "laptop");
    await vi.waitFor(() => expect(permissions.remove).toHaveBeenCalledTimes(1));
    expect(permissions.request).toHaveBeenCalledWith({ origins: ["https://kata.example.org/*"] });
    expect(sendMessage).toHaveBeenCalledWith({
      type: "panel:signIn",
      input: { baseUrl: "https://kata.example.org", code: "123456", deviceLabel: "laptop" },
    });
    expect(permissions.remove).toHaveBeenCalledWith({ origins: ["http://localhost:8000/*"] });
    expect(permissions.request.mock.invocationCallOrder[0]).toBeLessThan(permissions.remove.mock.invocationCallOrder[0]);
  });

  it("Cancel in change mode returns to the connected view without touching permissions", async () => {
    const { api, permissions } = fakeChrome({ ok: true }, signedIn);
    await bootPanel(mountPoint(), api);
    root.querySelector<HTMLButtonElement>("button.change-server")!.click();
    const cancel = [...root.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Cancel")!;
    cancel.click();
    expect(root.querySelector("p.origin")?.textContent).toBe("http://localhost:8000");
    expect(permissions.request).not.toHaveBeenCalled();
    expect(permissions.remove).not.toHaveBeenCalled();
  });

  it("removing the session origin in the browser falls back to first-run", async () => {
    const permissions = fakePermissions();
    const { api } = fakeChrome({ ok: true }, signedIn, permissions);
    await bootPanel(mountPoint(), api);
    permissions.fire(["https://other.example.org/*"]);
    expect(root.querySelector("form.signin")).toBeNull();
    permissions.fire(["http://localhost:8000/*"]);
    expect(root.querySelector("form.signin")).not.toBeNull();
    expect(root.querySelector("p.origin")).toBeNull();
  });

  const reviewRows = [{ conceptId: 5, label: "ser", state: null, evidence: "" }];
  const signedIn = { baseUrl: "http://localhost:8000", token: "t" };

  describe("Scan this page", () => {
    const connected = { baseUrl: "http://localhost:8000", token: "t" };
    const scanRows = [
      { blockId: "b1", topic: { id: 1, category: "ser", label: "serial" }, known: true },
      { blockId: "b2", topic: { id: 2, category: "ser", label: "queue" }, known: false },
    ];

    it("shows the Scan this page button when connected and no button on the sign-in form", async () => {
      const { api } = fakeChrome({ ok: true }, connected);
      await bootPanel(mountPoint(), api);
      expect(root.querySelector("button.scan")?.textContent).toBe("Scan this page");
      root.remove();
      const signedOut = fakeChrome();
      await bootPanel(mountPoint(), signedOut.api);
      expect(root.querySelector("form.signin")).not.toBeNull();
      expect(root.querySelector("button.scan")).toBeNull();
    });

    it("sends no panel:scan at boot", async () => {
      const { api, sendMessage } = fakeChrome({ ok: true }, connected);
      await bootPanel(mountPoint(), api);
      expect(sendMessage.mock.calls.some(([message]) => message.type === "panel:scan")).toBe(false);
    });

    it("click sends panel:scan once and draws the rows with their known badge and button", async () => {
      const { api, sendMessage } = fakeChrome({ ok: true, data: scanRows }, connected);
      await bootPanel(mountPoint(), api);
      root.querySelector<HTMLButtonElement>("button.scan")!.click();
      await vi.waitFor(() => expect(root.querySelector("li.row")).not.toBeNull());
      expect(sendMessage).toHaveBeenCalledWith({ type: "panel:scan" });
      expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:scan")).toHaveLength(1);
      expect(Array.from(root.querySelectorAll("span.badge"), (badge) => badge.textContent)).toEqual(["known", "new"]);
      expect(Array.from(root.querySelectorAll<HTMLButtonElement>("li.row button"), (button) => button.hidden)).toEqual([
        true,
        false,
      ]);
      expect(root.querySelector("p.status")?.textContent).toBe("");
    });

    it("a refused scan shows the failed text", async () => {
      const { api } = fakeChrome({ ok: false, error: "core down" }, connected);
      await bootPanel(mountPoint(), api);
      root.querySelector<HTMLButtonElement>("button.scan")!.click();
      await vi.waitFor(() => expect(root.querySelector("p.status")?.textContent).toBe("Something went wrong"));
      expect(root.querySelector("li.row")).toBeNull();
    });

    it("a refused scan with HTTP 401 shows the sign-in text", async () => {
      const { api } = fakeChrome({ ok: false, error: "expired", status: 401 }, connected);
      await bootPanel(mountPoint(), api);
      root.querySelector<HTMLButtonElement>("button.scan")!.click();
      await vi.waitFor(() => expect(root.querySelector("p.status")?.textContent).toBe("Sign-in failed or expired"));
    });

    it("a second click while the scan is in flight sends one message", async () => {
      const { api, sendMessage } = fakeChrome({ ok: true }, connected);
      sendMessage.mockImplementation(async (message: PanelMessage): Promise<PanelReply> => {
        if (message.type === "panel:scan") return new Promise<PanelReply>(() => {});
        return { ok: true };
      });
      await bootPanel(mountPoint(), api);
      const scan = root.querySelector<HTMLButtonElement>("button.scan")!;
      scan.dispatchEvent(new MouseEvent("click"));
      scan.dispatchEvent(new MouseEvent("click"));
      await vi.waitFor(() => expect(root.querySelector("p.status")?.textContent).toBe("scanning"));
      expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:scan")).toHaveLength(1);
    });
  });

  it("Review concepts sends panel:review and draws the returned rows", async () => {
    const { api, sendMessage } = fakeChrome({ ok: true, data: reviewRows }, signedIn);
    await bootPanel(mountPoint(), api);
    root.querySelector<HTMLButtonElement>("button.review-open")!.click();
    await vi.waitFor(() => expect(root.querySelector("li.review-row")).not.toBeNull());
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:review" });
    expect(root.querySelector("span.label")?.textContent).toBe("ser");
    expect(root.querySelector("button.review-open")).toBeNull();
  });

  it("a refused review sets the error status and stays on the scan view", async () => {
    const { api } = fakeChrome({ ok: false, error: "core down" }, signedIn);
    await bootPanel(mountPoint(), api);
    root.querySelector<HTMLButtonElement>("button.review-open")!.click();
    await vi.waitFor(() => expect(root.querySelector("p.status")?.textContent).toBe("Something went wrong"));
    expect(root.querySelector("li.review-row")).toBeNull();
    expect(root.querySelector("button.review-open")).not.toBeNull();
  });

  it("a state button sends panel:setConcept with the concept id and state", async () => {
    const { api, sendMessage } = fakeChrome({ ok: true, data: reviewRows }, signedIn);
    await bootPanel(mountPoint(), api);
    root.querySelector<HTMLButtonElement>("button.review-open")!.click();
    await vi.waitFor(() => expect(root.querySelector("li.review-row")).not.toBeNull());
    const known = [...root.querySelectorAll<HTMLButtonElement>("button.state-button")].find(
      (b) => b.textContent === "Known",
    )!;
    known.click();
    await vi.waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith({ type: "panel:setConcept", conceptId: 5, state: "known" }),
    );
  });

  it("Back returns to the scan view", async () => {
    const { api } = fakeChrome({ ok: true, data: reviewRows }, signedIn);
    await bootPanel(mountPoint(), api);
    root.querySelector<HTMLButtonElement>("button.review-open")!.click();
    await vi.waitFor(() => expect(root.querySelector("button.back")).not.toBeNull());
    root.querySelector<HTMLButtonElement>("button.back")!.click();
    expect(root.querySelector("li.review-row")).toBeNull();
    expect(root.querySelector("button.review-open")).not.toBeNull();
  });

  const courses = [{ id: 4, title: "Algebra" }];
  const courseList = { items: courses, limit: 5, total: 1 };

  it("loads the ready courses at boot and draws one Open course button each", async () => {
    const { api, sendMessage } = fakeChrome({ ok: true, data: courseList }, signedIn);
    await bootPanel(mountPoint(), api);
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:courses" });
    expect(root.querySelector("section.courses .course-title")?.textContent).toBe("Algebra");
    expect(root.querySelector("section.courses button")?.textContent).toBe("Open course");
    expect(root.querySelector("section.courses p.course-limit")?.textContent).toBe("1 of 5");
  });

  it("signed out at boot sends no courses request and draws no Courses section", async () => {
    const { api, sendMessage } = fakeChrome({ ok: true, data: courseList });
    await bootPanel(mountPoint(), api);
    expect(sendMessage).not.toHaveBeenCalled();
    expect(root.querySelector("section.courses")).toBeNull();
  });

  it("Open course sends panel:openCourse with the course id", async () => {
    const { api, sendMessage } = fakeChrome({ ok: true, data: courseList }, signedIn);
    await bootPanel(mountPoint(), api);
    root.querySelector<HTMLButtonElement>("section.courses button")!.click();
    await vi.waitFor(() => expect(sendMessage).toHaveBeenCalledWith({ type: "panel:openCourse", courseId: 4 }));
  });

  it("a refused open shows the background error text next to the course", async () => {
    const sendMessage = vi.fn(async (message: PanelMessage): Promise<PanelReply> =>
      message.type === "panel:courses"
        ? { ok: true, data: courseList }
        : { ok: false, error: "course link is outside the core" },
    );
    const api: PanelChromeLike = {
      runtime: { sendMessage },
      storage: { local: memoryArea({ "kata.session": signedIn }) },
      permissions: fakePermissions(),
    };
    await bootPanel(mountPoint(), api);
    root.querySelector<HTMLButtonElement>("section.courses button")!.click();
    await vi.waitFor(() =>
      expect(root.querySelector("section.courses span.note")?.textContent).toBe("course link is outside the core"),
    );
    expect(root.querySelector<HTMLButtonElement>("section.courses button")!.disabled).toBe(false);
  });

  it("confirmed delete sends panel:deleteCourse, reloads the list and drops the course", async () => {
    let listed = courseList;
    const sendMessage = vi.fn(async (message: PanelMessage): Promise<PanelReply> => {
      if (message.type === "panel:courses") return { ok: true, data: listed };
      if (message.type === "panel:deleteCourse") {
        listed = { items: [], limit: 5, total: 0 };
        return { ok: true };
      }
      return { ok: true };
    });
    const api: PanelChromeLike = {
      runtime: { sendMessage },
      storage: { local: memoryArea({ "kata.session": signedIn }) },
      permissions: fakePermissions(),
    };
    await bootPanel(mountPoint(), api);
    root.querySelector<HTMLButtonElement>('section.courses button[aria-label="Delete Algebra"]')!.click();
    root.querySelector<HTMLButtonElement>('section.courses button[aria-label="Confirm delete of Algebra"]')!.click();
    await vi.waitFor(() => expect(root.querySelector("section.courses .course-title")).toBeNull());
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:deleteCourse", courseId: 4 });
    expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:courses")).toHaveLength(2);
    expect(root.querySelector("section.courses p.course-limit")?.textContent).toBe("0 of 5");
  });

  it("a refused delete keeps the course listed and shows the error next to it", async () => {
    const sendMessage = vi.fn(async (message: PanelMessage): Promise<PanelReply> =>
      message.type === "panel:courses"
        ? { ok: true, data: courseList }
        : { ok: false, error: "delete refused" },
    );
    const api: PanelChromeLike = {
      runtime: { sendMessage },
      storage: { local: memoryArea({ "kata.session": signedIn }) },
      permissions: fakePermissions(),
    };
    await bootPanel(mountPoint(), api);
    root.querySelector<HTMLButtonElement>('section.courses button[aria-label="Delete Algebra"]')!.click();
    root.querySelector<HTMLButtonElement>('section.courses button[aria-label="Confirm delete of Algebra"]')!.click();
    await vi.waitFor(() =>
      expect(root.querySelector("section.courses span.note")?.textContent).toBe("delete refused"),
    );
    expect(root.querySelector("section.courses .course-title")?.textContent).toBe("Algebra");
    expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:courses")).toHaveLength(1);
  });

  /** Types a title into the create-course form and submits it. */
  function submitCreate(title: string) {
    const form = root.querySelector<HTMLFormElement>("section.courses form.create-course")!;
    form.querySelector<HTMLInputElement>('input[name="courseTitle"]')!.value = title;
    form.dispatchEvent(new Event("submit", { cancelable: true }));
  }

  it("a successful create sends panel:createCourse with the title and reloads the list", async () => {
    let listed = courseList;
    const sendMessage = vi.fn(async (message: PanelMessage): Promise<PanelReply> => {
      if (message.type === "panel:courses") return { ok: true, data: listed };
      if (message.type === "panel:createCourse") {
        listed = { items: [...courseList.items, { id: 6, title: "Rust basics" }], limit: 5, total: 2 };
        return { ok: true };
      }
      return { ok: true };
    });
    const api: PanelChromeLike = {
      runtime: { sendMessage },
      storage: { local: memoryArea({ "kata.session": signedIn }) },
      permissions: fakePermissions(),
    };
    await bootPanel(mountPoint(), api);
    submitCreate("Rust basics");
    await vi.waitFor(() => expect(root.querySelectorAll("section.courses .course-title")).toHaveLength(2));
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:createCourse", title: "Rust basics" });
    expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:courses")).toHaveLength(2);
    expect(root.querySelector("section.courses p.course-note")?.textContent).toBe("");
  });

  it("onRegenerateCourse sends panel:regenerateCourse with the course id and reloads the list", async () => {
    const sendMessage = vi.fn(async (message: PanelMessage): Promise<PanelReply> =>
      message.type === "panel:courses" ? { ok: true, data: courseList } : { ok: true },
    );
    const api: PanelChromeLike = {
      runtime: { sendMessage },
      storage: { local: memoryArea({ "kata.session": signedIn }) },
      permissions: fakePermissions(),
    };
    await bootPanel(mountPoint(), api);
    await captured.handlers!.onRegenerateCourse(7);
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:regenerateCourse", courseId: 7 });
    expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:courses")).toHaveLength(2);
  });

  it("a refused create shows the course error text and does not reload the list", async () => {
    const sendMessage = vi.fn(async (message: PanelMessage): Promise<PanelReply> =>
      message.type === "panel:courses"
        ? { ok: true, data: courseList }
        : { ok: false, error: "course limit of 3 reached", status: 409, code: "course_limit" },
    );
    const api: PanelChromeLike = {
      runtime: { sendMessage },
      storage: { local: memoryArea({ "kata.session": signedIn }) },
      permissions: fakePermissions(),
    };
    await bootPanel(mountPoint(), api);
    submitCreate("Rust basics");
    await vi.waitFor(() =>
      expect(root.querySelector("section.courses p.course-note")?.textContent).toBe(
        "You have reached your course limit. Delete a course to add another.",
      ),
    );
    expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:courses")).toHaveLength(1);
  });
});
