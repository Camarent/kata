import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { execSync } from "node:child_process";
import { beforeAll, afterEach, describe, expect, it, vi } from "vitest";
import { PANEL_CSS } from "../src/ui/panelCss";
import { bootPanel, mountPanelStyle, type OriginsRequest, type PanelChromeLike } from "../src/sidepanelBoot";
import type { PanelMessage, PanelReply } from "../src/messages";
import type { PanelHandlers, PanelState } from "../src/sidepanel";
import type { StorageArea } from "../src/tokenStore";
import { ERROR_TEXT } from "../src/ui/panel/statusText";
import { TEXT_COURSES_TAB, TEXT_EXAM_RESULT_ENTRY, TEXT_SCAN_RESULTS } from "../src/ui/strings";

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

describe("mountPanelStyle", () => {
  it("appends one style element with the panel CSS to the document head", () => {
    const before = document.head.querySelectorAll("style").length;
    const style = mountPanelStyle(document);
    try {
      expect(document.head.querySelectorAll("style")).toHaveLength(before + 1);
      expect(style.parentElement).toBe(document.head);
      expect(PANEL_CSS.length).toBeGreaterThan(0);
      expect(style.textContent).toBe(PANEL_CSS);
    } finally {
      style.remove();
    }
  });
});

describe("sidepanel.html", () => {
  it("has no inline script: every script element has a src", () => {
    const scripts = Array.from(parsedPage().querySelectorAll("script"));
    expect(scripts.length).toBeGreaterThan(0);
    for (const script of scripts) {
      expect(script.getAttribute("src")).toMatch(/^[\w.-]+\.js$/);
      expect(script.textContent?.trim()).toBe("");
    }
  });

  it("has no inline style: panel CSS comes from panelCss.ts via the boot script", () => {
    expect(parsedPage().querySelectorAll("style")).toHaveLength(0);
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
    expect(root.querySelector(".empty")?.textContent).toBe(TEXT_SCAN_RESULTS[27]);
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

  /** Clicks the tab button of `tab` in the tab bar. */
  const openTab = (tab: string): void => {
    root.querySelector<HTMLButtonElement>(`nav.tabs button.tab-${tab}`)!.click();
  };

  describe("tab bar", () => {
    // Lists is a section of the Courses tab (design note D10), so the bar has five tabs.
    it.each([
      ["review", "li.review-row"],
      ["courses", "section.courses-tab"],
      ["tracks", "section.tracks-tab"],
      ["settings", "section.settings-home"],
      ["scan", "section.scan-results"],
    ])("a click on the %s tab draws its registry screen (%s)", async (tab, selector) => {
      const { api } = fakeChrome({ ok: true, data: reviewRows }, signedIn);
      await bootPanel(mountPoint(), api);
      // Start from another tab, so the click has to leave it.
      openTab(tab === "scan" ? "settings" : "scan");
      await vi.waitFor(() => expect(root.querySelector("nav.tabs")).not.toBeNull());
      openTab(tab);
      await vi.waitFor(() => expect(root.querySelector(selector)).not.toBeNull());
      expect(root.querySelector("nav.tabs button[aria-current]")?.classList.contains(`tab-${tab}`)).toBe(true);
    });

    it("draws the five tab buttons of the bar in order", async () => {
      const { api } = fakeChrome({ ok: true }, signedIn);
      await bootPanel(mountPoint(), api);
      expect([...root.querySelectorAll("nav.tabs button")].map((b) => b.className.split(" ")[1])).toEqual([
        "tab-scan",
        "tab-review",
        "tab-courses",
        "tab-tracks",
        "tab-settings",
      ]);
    });
  });

  describe("Scan page", () => {
    const connected = { baseUrl: "http://localhost:8000", token: "t" };
    const scanRows = [
      { blockId: "b1", topic: { id: 1, category: "ser", label: "serial" }, known: true },
      { blockId: "b2", topic: { id: 2, category: "ser", label: "queue" }, known: false },
    ];

    it("shows the Scan page button when connected and no button on the sign-in form", async () => {
      const { api } = fakeChrome({ ok: true }, connected);
      await bootPanel(mountPoint(), api);
      expect(root.querySelector("button.scan-page")?.textContent).toBe(TEXT_SCAN_RESULTS[1]);
      root.remove();
      const signedOut = fakeChrome();
      await bootPanel(mountPoint(), signedOut.api);
      expect(root.querySelector("form.signin")).not.toBeNull();
      expect(root.querySelector("button.scan-page")).toBeNull();
    });

    it("sends no panel:scan at boot", async () => {
      const { api, sendMessage } = fakeChrome({ ok: true }, connected);
      await bootPanel(mountPoint(), api);
      expect(sendMessage.mock.calls.some(([message]) => message.type === "panel:scan")).toBe(false);
    });

    it("click sends panel:scan once and draws the rows with their known badge and button", async () => {
      const { api, sendMessage } = fakeChrome({ ok: true, data: scanRows }, connected);
      await bootPanel(mountPoint(), api);
      root.querySelector<HTMLButtonElement>("button.scan-page")!.click();
      await vi.waitFor(() => expect(root.querySelector("li.row")).not.toBeNull());
      expect(sendMessage).toHaveBeenCalledWith({ type: "panel:scan" });
      expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:scan")).toHaveLength(1);
      expect(Array.from(root.querySelectorAll("li.row span.badge"), (badge) => badge.textContent)).toEqual(["known", "new"]);
      expect(Array.from(root.querySelectorAll<HTMLButtonElement>("li.row button"), (button) => button.hidden)).toEqual([
        true,
        false,
      ]);
      expect(root.querySelector("p.status")?.textContent).toBe("");
    });

    it("a refused scan shows the failed text", async () => {
      const { api } = fakeChrome({ ok: false, error: "core down" }, connected);
      await bootPanel(mountPoint(), api);
      root.querySelector<HTMLButtonElement>("button.scan-page")!.click();
      await vi.waitFor(() => expect(root.querySelector("p.status")?.textContent).toBe(ERROR_TEXT.failed));
      expect(root.querySelector("li.row")).toBeNull();
    });

    it("a refused scan with HTTP 401 shows the sign-in text", async () => {
      const { api } = fakeChrome({ ok: false, error: "expired", status: 401 }, connected);
      await bootPanel(mountPoint(), api);
      root.querySelector<HTMLButtonElement>("button.scan-page")!.click();
      await vi.waitFor(() => expect(root.querySelector("p.status")?.textContent).toBe(ERROR_TEXT.auth));
    });

    it("a second click while the scan is in flight sends one message", async () => {
      const { api, sendMessage } = fakeChrome({ ok: true }, connected);
      sendMessage.mockImplementation(async (message: PanelMessage): Promise<PanelReply> => {
        if (message.type === "panel:scan") return new Promise<PanelReply>(() => {});
        return { ok: true };
      });
      await bootPanel(mountPoint(), api);
      const scan = root.querySelector<HTMLButtonElement>("button.scan-page")!;
      scan.dispatchEvent(new MouseEvent("click"));
      scan.dispatchEvent(new MouseEvent("click"));
      await vi.waitFor(() => expect(root.querySelector("p.status")?.textContent).toBe("scanning"));
      expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:scan")).toHaveLength(1);
    });
  });

  it("the Review tab sends panel:review and draws the returned rows", async () => {
    const { api, sendMessage } = fakeChrome({ ok: true, data: reviewRows }, signedIn);
    await bootPanel(mountPoint(), api);
    openTab("review");
    await vi.waitFor(() => expect(root.querySelector("li.review-row")).not.toBeNull());
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:review" });
    expect(root.querySelector("span.label")?.textContent).toBe("ser");
    expect(root.querySelector("button.scan-page")).toBeNull();
  });

  it("a refused review sets the error status and stays on the scan tab", async () => {
    const { api } = fakeChrome({ ok: false, error: "core down" }, signedIn);
    await bootPanel(mountPoint(), api);
    openTab("review");
    await vi.waitFor(() => expect(root.querySelector("p.status")?.textContent).toBe(ERROR_TEXT.failed));
    expect(root.querySelector("li.review-row")).toBeNull();
    expect(root.querySelector("button.scan-page")).not.toBeNull();
  });

  it("a state button sends panel:setConcept with the concept id and state", async () => {
    const { api, sendMessage } = fakeChrome({ ok: true, data: reviewRows }, signedIn);
    await bootPanel(mountPoint(), api);
    openTab("review");
    await vi.waitFor(() => expect(root.querySelector("li.review-row")).not.toBeNull());
    const known = [...root.querySelectorAll<HTMLButtonElement>("button.state-button")].find(
      (b) => b.textContent === "Known",
    )!;
    known.click();
    await vi.waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith({ type: "panel:setConcept", conceptId: 5, state: "known" }),
    );
  });

  it("the Scan tab leaves the Review tab", async () => {
    const { api } = fakeChrome({ ok: true, data: reviewRows }, signedIn);
    await bootPanel(mountPoint(), api);
    openTab("review");
    await vi.waitFor(() => expect(root.querySelector("li.review-row")).not.toBeNull());
    openTab("scan");
    expect(root.querySelector("li.review-row")).toBeNull();
    expect(root.querySelector("button.scan-page")).not.toBeNull();
  });

  const courses = [{ id: 4, title: "Algebra" }];
  const courseList = { items: courses, limit: 5, total: 1 };

  it("loads the ready courses at boot and draws one Open course button on the Courses tab", async () => {
    const { api, sendMessage } = fakeChrome({ ok: true, data: courseList }, signedIn);
    await bootPanel(mountPoint(), api);
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:courses" });
    openTab("courses");
    expect(root.querySelector("section.courses-tab li span")?.textContent).toBe("Algebra");
    expect(root.querySelector("section.courses-tab li button")?.textContent).toBe(TEXT_COURSES_TAB[5]);
  });

  it("a refused course list shows the could-not-load text on the Courses tab", async () => {
    const { api } = fakeChrome({ ok: false, error: "core down" }, signedIn);
    await bootPanel(mountPoint(), api);
    openTab("courses");
    expect(root.querySelector("section.courses-tab p.error")?.textContent).toBe(TEXT_COURSES_TAB[23]);
  });

  it("signed out at boot sends no courses request and draws no tab bar", async () => {
    const { api, sendMessage } = fakeChrome({ ok: true, data: courseList });
    await bootPanel(mountPoint(), api);
    expect(sendMessage).not.toHaveBeenCalled();
    expect(root.querySelector("nav.tabs")).toBeNull();
  });

  /** A chrome whose course list follows `listed` and whose other messages answer `other`. */
  function courseChrome(other: (message: PanelMessage) => PanelReply, listed: () => unknown = () => courseList) {
    const sendMessage = vi.fn(async (message: PanelMessage): Promise<PanelReply> =>
      message.type === "panel:courses" ? { ok: true, data: listed() } : other(message),
    );
    const api: PanelChromeLike = {
      runtime: { sendMessage },
      storage: { local: memoryArea({ "kata.session": signedIn }) },
      permissions: fakePermissions(),
    };
    return { api, sendMessage };
  }

  it("Open course sends panel:openCourse with the course id", async () => {
    const { api, sendMessage } = courseChrome(() => ({ ok: true }));
    await bootPanel(mountPoint(), api);
    openTab("courses");
    root.querySelector<HTMLButtonElement>("section.courses-tab li button")!.click();
    await vi.waitFor(() => expect(sendMessage).toHaveBeenCalledWith({ type: "panel:openCourse", courseId: 4 }));
  });

  it("a refused open shows the error text on the Courses tab and turns the button on again", async () => {
    const { api } = courseChrome(() => ({ ok: false, error: "open refused" }));
    await bootPanel(mountPoint(), api);
    openTab("courses");
    const open = root.querySelector<HTMLButtonElement>("section.courses-tab li button")!;
    open.click();
    await vi.waitFor(() => expect(root.querySelector("section.courses-tab p.error")?.textContent).toBe("open refused"));
    expect(open.disabled).toBe(false);
  });

  it("the Courses tab shows n of limit from the course list", async () => {
    const { api } = courseChrome(() => ({ ok: true }));
    await bootPanel(mountPoint(), api);
    openTab("courses");
    expect(root.querySelector("section.courses-tab p.course-limit")?.textContent).toBe("1 of 5");
  });

  it("confirmed delete sends panel:deleteCourse, reloads the list and drops the course", async () => {
    let listed: unknown = courseList;
    const { api, sendMessage } = courseChrome(
      (message) => {
        if (message.type === "panel:deleteCourse") listed = { items: [], limit: 5, total: 0 };
        return { ok: true };
      },
      () => listed,
    );
    await bootPanel(mountPoint(), api);
    openTab("courses");
    const remove = [...root.querySelectorAll<HTMLButtonElement>("section.courses-tab li button")].find(
      (b) => b.textContent === TEXT_COURSES_TAB[25],
    )!;
    remove.click();
    root.querySelector<HTMLButtonElement>("button.confirm-yes")!.click();
    await vi.waitFor(() => expect(root.querySelector("section.courses-tab li")).toBeNull());
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:deleteCourse", courseId: 4 });
    expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:courses")).toHaveLength(2);
  });

  it("a refused delete keeps the course listed and shows the delete-failed text", async () => {
    const { api, sendMessage } = courseChrome(() => ({ ok: false, error: "delete refused" }));
    await bootPanel(mountPoint(), api);
    openTab("courses");
    const remove = [...root.querySelectorAll<HTMLButtonElement>("section.courses-tab li button")].find(
      (b) => b.textContent === TEXT_COURSES_TAB[25],
    )!;
    remove.click();
    root.querySelector<HTMLButtonElement>("button.confirm-yes")!.click();
    await vi.waitFor(() =>
      expect(root.querySelector("section.courses-tab p.error")?.textContent).toBe(TEXT_COURSES_TAB[28]),
    );
    expect(root.querySelector("section.courses-tab li span")?.textContent).toBe("Algebra");
    expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:courses")).toHaveLength(1);
  });

  it("onCreateCourse sends panel:createCourse with the title and reloads the list", async () => {
    let listed: unknown = courseList;
    const { api, sendMessage } = courseChrome(
      (message) => {
        if (message.type === "panel:createCourse") {
          listed = { items: [...courseList.items, { id: 6, title: "Rust basics" }], limit: 5, total: 2 };
        }
        return { ok: true };
      },
      () => listed,
    );
    await bootPanel(mountPoint(), api);
    openTab("courses");
    await captured.handlers!.onCreateCourse("Rust basics");
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:createCourse", title: "Rust basics" });
    expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:courses")).toHaveLength(2);
    expect(root.querySelectorAll("section.courses-tab li")).toHaveLength(2);
  });

  it("onRegenerateCourse sends panel:regenerateCourse with the course id and reloads the list", async () => {
    const { api, sendMessage } = courseChrome(() => ({ ok: true }));
    await bootPanel(mountPoint(), api);
    await captured.handlers!.onRegenerateCourse(7);
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:regenerateCourse", courseId: 7 });
    expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:courses")).toHaveLength(2);
  });

  it("a refused create rejects with the core status and code and does not reload the list", async () => {
    const { api, sendMessage } = courseChrome(() => ({
      ok: false,
      error: "course limit of 3 reached",
      status: 409,
      code: "course_limit",
    }));
    await bootPanel(mountPoint(), api);
    await expect(captured.handlers!.onCreateCourse("Rust basics")).rejects.toMatchObject({
      status: 409,
      code: "course_limit",
    });
    expect(sendMessage.mock.calls.filter(([message]) => message.type === "panel:courses")).toHaveLength(1);
  });
});

describe("bootPanel tracks, exam and ignored handlers", () => {
  const cases: Array<[string, (h: PanelHandlers) => Promise<unknown> | undefined, PanelMessage]> = [
    ["onLoadTracks", (h) => h.onLoadTracks!({ limit: 5, beforeId: 9 }), { type: "panel:tracks", limit: 5, beforeId: 9 }],
    ["onGetTrack", (h) => h.onGetTrack!(3), { type: "panel:getTrack", trackId: 3 }],
    ["onDeleteTrack", (h) => h.onDeleteTrack!(3), { type: "panel:deleteTrack", trackId: 3 }],
    ["onAddQuizSource", (h) => h.onAddQuizSource!("https://q.example/x"), { type: "panel:addQuizSource", url: "https://q.example/x" }],
    ["onImportExamResult", (h) => h.onImportExamResult!("{}"), { type: "panel:importExamResult", payload: "{}" }],
    ["onConfirmExamResult", (h) => h.onConfirmExamResult!(4, [1, 2]), { type: "panel:confirmExamResult", resultId: 4, conceptIds: [1, 2] }],
    ["onDismissExamResult", (h) => h.onDismissExamResult!(4), { type: "panel:dismissExamResult", resultId: 4 }],
    ["onLoadIgnored", (h) => h.onLoadIgnored!(), { type: "panel:ignored" }],
    ["onIgnoreConcept", (h) => h.onIgnoreConcept!(8), { type: "panel:ignoreConcept", conceptId: 8 }],
    ["onUnignoreConcept", (h) => h.onUnignoreConcept!(8), { type: "panel:unignoreConcept", conceptId: 8 }],
    ["onListConceptAliases", (h) => h.onListConceptAliases!(3), { type: "panel:listConceptAliases", conceptId: 3 }],
    ["onAddConceptAlias", (h) => h.onAddConceptAlias!(3, "parts"), { type: "panel:addConceptAlias", conceptId: 3, alias: "parts" }],
    ["onMarkConceptViewed", (h) => h.onMarkConceptViewed!(3), { type: "panel:markConceptViewed", conceptId: 3 }],
    ["onRequestSummary", (h) => h.onRequestSummary!("https://p", "page"), { type: "panel:requestSummary", url: "https://p", text: "page" }],
    ["onCachedSummary", (h) => h.onCachedSummary!("https://p", "abc"), { type: "panel:cachedSummary", url: "https://p", textSha256: "abc" }],
    ["onNextJoke", (h) => h.onNextJoke!(), { type: "panel:nextJoke" }],
    ["onListJokeSources", (h) => h.onListJokeSources!(), { type: "panel:listJokeSources" }],
  ];

  it.each(cases)("%s sends its panel message and returns the reply data", async (_name, call, message) => {
    const { api, sendMessage } = fakeChrome({ ok: true, data: { marker: 1 } });
    await bootPanel(document.createElement("div"), api);
    await expect(call(captured.handlers!)).resolves.toEqual({ marker: 1 });
    expect(sendMessage).toHaveBeenCalledWith(message);
  });

  it("the ignored list Restore and Undo send the unignore and ignore panel messages", async () => {
    const { api, sendMessage } = fakeChrome({ ok: true, data: [] });
    await bootPanel(document.createElement("div"), api);
    // Restore sends unignore first (then reloads the list); Undo sends ignore as its first call.
    const beforeRestore = sendMessage.mock.calls.length;
    await captured.handlers!.ignoredList!.onRestore(8);
    expect(sendMessage.mock.calls[beforeRestore]).toEqual([{ type: "panel:unignoreConcept", conceptId: 8 }]);
    const beforeUndo = sendMessage.mock.calls.length;
    await captured.handlers!.ignoredList!.onUndo(8);
    expect(sendMessage.mock.calls[beforeUndo]).toEqual([{ type: "panel:ignoreConcept", conceptId: 8 }]);
  });

  it("a refused call rejects with the core status and code", async () => {
    const { api } = fakeChrome({ ok: false, error: "gone", status: 404, code: "not_found" });
    await bootPanel(document.createElement("div"), api);
    await expect(captured.handlers!.onGetTrack!(3)).rejects.toMatchObject({ status: 404, code: "not_found" });
  });
});

describe("bootPanel Tracks tab and settings home", () => {
  const session = { baseUrl: "http://localhost:8000", token: "t" };
  let root: HTMLElement;

  afterEach(() => {
    root?.remove();
  });

  /** Fake chrome that answers each panel message type from `replies`; other types get a bare ok reply. */
  function chromeWith(replies: Record<string, PanelReply>) {
    const sendMessage = vi.fn(async (message: PanelMessage) => replies[message.type] ?? { ok: true });
    const api: PanelChromeLike = {
      runtime: { sendMessage },
      storage: { local: memoryArea({ "kata.session": session }) },
      permissions: fakePermissions(),
    };
    return { api, sendMessage };
  }

  /** Clicks the tab button of `tab` in the tab bar. */
  const openTab = (tab: string): void => {
    root.querySelector<HTMLButtonElement>(`nav.tabs button.tab-${tab}`)!.click();
  };

  /** A track as the core sends it (`TrackOut`), with the fields the tab reads. */
  const track = (id: number, name: string, status = "active") => ({
    id,
    name,
    deadline: "2026-12-31",
    priority: 1,
    status,
    items: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  });

  it("the Tracks tab draws the rows of the panel:tracks reply, sorted by name", async () => {
    root = document.createElement("main");
    document.body.append(root);
    const { api, sendMessage } = chromeWith({
      "panel:tracks": { ok: true, data: { items: [track(1, "Zeta"), track(2, "Alpha")], next_before_id: null } },
    });
    await bootPanel(root, api);
    openTab("tracks");
    await vi.waitFor(() => expect(root.querySelector("section.tracks-tab")?.textContent).toContain("Alpha"));
    const text = root.querySelector("section.tracks-tab")!.textContent!;
    expect(text.indexOf("Alpha")).toBeLessThan(text.indexOf("Zeta"));
    expect(root.querySelector("section.tracks-tab")?.getAttribute("data-state")).toBe("ready");
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:tracks" });
  });

  it("the Tracks tab shows its could-not-load state when the panel:tracks reply is refused", async () => {
    root = document.createElement("main");
    document.body.append(root);
    const { api } = chromeWith({ "panel:tracks": { ok: false, error: "gone" } });
    await bootPanel(root, api);
    openTab("tracks");
    await vi.waitFor(() => expect(root.querySelector("section.tracks-tab")?.getAttribute("data-state")).toBe("error"));
  });

  it("the settings home opens the ignored list page, and its Back returns to the home", async () => {
    root = document.createElement("main");
    document.body.append(root);
    const { api, sendMessage } = chromeWith({
      "panel:ignored": { ok: true, data: [{ concept_id: 8, label: "serial" }] },
    });
    await bootPanel(root, api);
    openTab("settings");
    await vi.waitFor(() => expect(root.querySelector("section.settings-home")).not.toBeNull());
    root.querySelector<HTMLButtonElement>("button.open-ignored")!.click();
    await vi.waitFor(() => expect(root.querySelector("section.ignored-list")?.textContent).toContain("serial"));
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:ignored" });
    root.querySelector<HTMLButtonElement>("section.ignored-list button.back")!.click();
    await vi.waitFor(() => expect(root.querySelector("section.settings-home")).not.toBeNull());
    expect(root.querySelector("section.ignored-list")).toBeNull();
  });

  it("the settings tab opens the exam entry, saving imports the result and draws the result screen with its score", async () => {
    root = document.createElement("main");
    document.body.append(root);
    const stored = {
      id: 5,
      origin: "page",
      taken_at: "2026-01-01T00:00:00Z",
      passed: true,
      score: 0.85,
      status: "pending",
      concepts: [],
    };
    const { api, sendMessage } = chromeWith({ "panel:importExamResult": { ok: true, data: stored } });
    await bootPanel(root, api);
    openTab("settings");
    root.querySelector<HTMLButtonElement>("button.open-exam-entry")!.click();
    const entry = root.querySelector("section.exam-entry")!;
    entry.querySelector<HTMLInputElement>('input[name="date"]')!.value = "2026-01-01";
    entry.querySelector<HTMLInputElement>('input[name="score"]')!.value = "85";
    entry.querySelector<HTMLButtonElement>("button.save-result")!.click();
    await vi.waitFor(() => expect(root.querySelector("section.exam-result")).not.toBeNull());
    expect(root.querySelector("p.exam-score")?.textContent).toContain("85%");
    const sent = sendMessage.mock.calls.map((c) => c[0]).find((m) => m.type === "panel:importExamResult") as {
      payload: string;
    };
    expect(JSON.parse(sent.payload)).toMatchObject({ score: 0.85, taken_at: "2026-01-01T00:00:00Z" });
    root.querySelector<HTMLButtonElement>("button.exam-done")!.click();
    await vi.waitFor(() => expect(root.querySelector("section.settings-home")).not.toBeNull());
    expect(sendMessage).toHaveBeenCalledWith({ type: "panel:confirmExamResult", resultId: 5, conceptIds: [] });
  });

  /** Opens the exam entry on the settings tab and fills the date; the caller sets the score and saves. */
  const openFilledEntry = async (replies: Record<string, PanelReply>) => {
    root = document.createElement("main");
    document.body.append(root);
    const chrome = chromeWith(replies);
    await bootPanel(root, chrome.api);
    openTab("settings");
    root.querySelector<HTMLButtonElement>("button.open-exam-entry")!.click();
    const entry = root.querySelector("section.exam-entry")!;
    entry.querySelector<HTMLInputElement>('input[name="date"]')!.value = "2026-01-01";
    return { entry, sendMessage: chrome.sendMessage };
  };

  it("a blank or out-of-range score is refused: no import is sent and the form shows its error", async () => {
    for (const score of ["", "   ", "101", "-1", "abc"]) {
      const { entry, sendMessage } = await openFilledEntry({ "panel:importExamResult": { ok: true, data: {} } });
      entry.querySelector<HTMLInputElement>('input[name="score"]')!.value = score;
      entry.querySelector<HTMLButtonElement>("button.save-result")!.click();
      await vi.waitFor(() => expect(entry.querySelector("p.error")?.textContent).toBe(TEXT_EXAM_RESULT_ENTRY[9]));
      expect(sendMessage.mock.calls.some((c) => c[0].type === "panel:importExamResult")).toBe(false);
      expect(root.querySelector("section.exam-entry")).not.toBeNull();
    }
  });

  it("the score field is a percentage: 1 is sent as 0.01 and 0.5 as 0.005", async () => {
    for (const [typed, sent] of [
      ["1", 0.01],
      ["0.5", 0.005],
    ] as const) {
      const { entry, sendMessage } = await openFilledEntry({
        "panel:importExamResult": { ok: true, data: { id: 6, score: sent, concepts: [] } },
      });
      entry.querySelector<HTMLInputElement>('input[name="score"]')!.value = typed;
      entry.querySelector<HTMLButtonElement>("button.save-result")!.click();
      await vi.waitFor(() => expect(root.querySelector("section.exam-result")).not.toBeNull());
      const imported = sendMessage.mock.calls.map((c) => c[0]).find((m) => m.type === "panel:importExamResult") as {
        payload: string;
      };
      expect(JSON.parse(imported.payload)).toMatchObject({ score: sent });
    }
  });

  it("a refused Done keeps the result screen with its error line, and Done can be pressed again", async () => {
    const stored = { id: 7, origin: "page", taken_at: "2026-01-01T00:00:00Z", passed: true, score: 0.9, status: "pending", concepts: [] };
    const { entry, sendMessage } = await openFilledEntry({
      "panel:importExamResult": { ok: true, data: stored },
      "panel:confirmExamResult": { ok: false, error: "gone" },
    });
    entry.querySelector<HTMLInputElement>('input[name="score"]')!.value = "90";
    entry.querySelector<HTMLButtonElement>("button.save-result")!.click();
    await vi.waitFor(() => expect(root.querySelector("section.exam-result")).not.toBeNull());
    root.querySelector<HTMLButtonElement>("button.exam-done")!.click();
    await vi.waitFor(() => expect(root.querySelector("p.exam-confirm-error")?.textContent).toBe("Could not confirm the result. Press Done to try again."));
    expect(root.querySelector("section.exam-result")).not.toBeNull();
    expect(root.querySelector("section.settings-home")).toBeNull();
    root.querySelector<HTMLButtonElement>("button.exam-done")!.click();
    await vi.waitFor(() =>
      expect(sendMessage.mock.calls.filter((c) => c[0].type === "panel:confirmExamResult")).toHaveLength(2),
    );
  });

  it("the result screen with a wrong concept draws no Open course items button until it is wired", async () => {
    const stored = {
      id: 8,
      origin: "page",
      taken_at: "2026-01-01T00:00:00Z",
      passed: false,
      score: 0.4,
      status: "pending",
      concepts: [{ concept_id: 3, correct: false, confirmed: false }],
    };
    const { entry } = await openFilledEntry({ "panel:importExamResult": { ok: true, data: stored } });
    entry.querySelector<HTMLInputElement>('input[name="score"]')!.value = "40";
    entry.querySelector<HTMLButtonElement>("button.save-result")!.click();
    await vi.waitFor(() => expect(root.querySelector("section.exam-result")).not.toBeNull());
    expect(root.querySelector(".exam-needs")).not.toBeNull();
    expect(root.querySelector("button.exam-open-items")).toBeNull();
  });

  it("a refused panel:ignored keeps the settings home drawn", async () => {
    root = document.createElement("main");
    document.body.append(root);
    const { api } = chromeWith({ "panel:ignored": { ok: false, error: "gone" } });
    await bootPanel(root, api);
    openTab("settings");
    await vi.waitFor(() => expect(root.querySelector("section.settings-home")).not.toBeNull());
    root.querySelector<HTMLButtonElement>("button.open-ignored")!.click();
    // Let the refused reply settle; the page must not open and nothing may reject unhandled.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(root.querySelector("section.ignored-list")).toBeNull();
    expect(root.querySelector("section.settings-home")).not.toBeNull();
  });

  it("the Tracks tab Open and New buttons call the boot track handlers", async () => {
    root = document.createElement("main");
    document.body.append(root);
    const { api } = chromeWith({
      "panel:tracks": { ok: true, data: { items: [track(1, "Alpha")], next_before_id: null } },
    });
    await bootPanel(root, api);
    const onOpenTrack = vi.spyOn(captured.handlers!, "onOpenTrack");
    const onNewTrack = vi.spyOn(captured.handlers!, "onNewTrack");
    openTab("tracks");
    await vi.waitFor(() => expect(root.querySelector("button.open-track")).not.toBeNull());
    root.querySelector<HTMLButtonElement>("button.open-track")!.click();
    expect(onOpenTrack).toHaveBeenCalledWith(1);
    root.querySelector<HTMLButtonElement>("section.track-detail button.back")!.click();
    await vi.waitFor(() => expect(root.querySelector("button.new-track")).not.toBeNull());
    root.querySelector<HTMLButtonElement>("button.new-track")!.click();
    expect(onNewTrack).toHaveBeenCalledTimes(1);
  });

  it("a track row click draws the track detail, and New track draws the create form", async () => {
    root = document.createElement("main");
    document.body.append(root);
    const { api } = chromeWith({
      "panel:tracks": { ok: true, data: { items: [track(1, "Alpha")], next_before_id: null } },
    });
    await bootPanel(root, api);
    openTab("tracks");
    await vi.waitFor(() => expect(root.querySelector("button.open-track")).not.toBeNull());
    root.querySelector<HTMLButtonElement>("button.open-track")!.click();
    expect(root.querySelector("section.track-detail")).not.toBeNull();
    expect(root.querySelector("section.tracks-tab")).toBeNull();
    root.querySelector<HTMLButtonElement>("section.track-detail button.back")!.click();
    await vi.waitFor(() => expect(root.querySelector("button.new-track")).not.toBeNull());
    root.querySelector<HTMLButtonElement>("button.new-track")!.click();
    expect(root.querySelector("form.track-create")).not.toBeNull();
  });
});
