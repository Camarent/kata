import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CoreOfflineError } from "../src/coreClient";
import { renderPanel, type PanelHandlers, type PanelState } from "../src/sidepanel";
import { routeScreen } from "../src/ui/panel/router";
import { TEXT_CONN_DETAIL, TEXT_OFFLINE_QUEUE, TEXT_SIGNED_OUT, TEXT_SIGNIN } from "../src/ui/strings";

const session = { baseUrl: "http://localhost:8000", token: "t" };

function handlers(overrides: Partial<PanelHandlers> = {}): PanelHandlers {
  return {
    onSignIn: vi.fn(),
    onDisconnect: vi.fn(),
    onChangeServer: vi.fn(),
    onCancelChange: vi.fn(),
    onKnown: vi.fn(async () => "saved" as const),
    onScan: vi.fn(async () => {}),
    onReview: vi.fn(async () => {}),
    onSetConcept: vi.fn(async () => {}),
    onCloseReview: vi.fn(),
    onOpenCourse: vi.fn(async () => {}),
    onDeleteCourse: vi.fn(async () => {}),
    onCreateCourse: vi.fn(async () => {}),
    onModelhost: vi.fn(async () => ({ ok: true, text: "done" })),
    onRetry: vi.fn(async () => {}),
    onShowQueue: vi.fn(),
    onCloseQueue: vi.fn(),
    ...overrides,
  };
}

/** Button with the given visible text inside root; fails the test when there is none. */
function buttonNamed(root: HTMLElement, text: string): HTMLButtonElement {
  const found = [...root.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === text);
  if (found === undefined) throw new Error(`no button "${text}"`);
  return found;
}

/** Text of every element of root matching the selector, in document order. */
function textsOf(root: HTMLElement, selector: string): (string | null)[] {
  return [...root.querySelectorAll(selector)].map((node) => node.textContent);
}

describe("panel shell screens, one test per inventory state", () => {
  let root: HTMLElement;

  beforeEach(() => {
    root = document.createElement("main");
    document.body.append(root);
  });

  afterEach(() => {
    root.remove();
  });

  describe("sign-in (loading, error, offline)", () => {
    it("loading: shows Signing in... and disables the submit while onSignIn runs", async () => {
      let finish: () => void = () => {};
      const pending = new Promise<void>((resolve) => {
        finish = resolve;
      });
      const h = handlers({ onSignIn: vi.fn(() => pending) });
      renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, h);
      root.querySelector<HTMLInputElement>('input[name="baseUrl"]')!.value = "https://kata.example.org";
      root.querySelector<HTMLInputElement>('input[name="code"]')!.value = "1234";
      root.querySelector<HTMLInputElement>('input[name="deviceLabel"]')!.value = "laptop";
      root.querySelector("form")!.dispatchEvent(new Event("submit", { cancelable: true }));
      const submit = root.querySelector<HTMLButtonElement>("button[type='submit']")!;
      expect(root.querySelector("p.error")?.textContent).toBe(TEXT_SIGNIN[6]);
      expect(submit.disabled).toBe(true);
      finish();
      await pending;
      await Promise.resolve();
      expect(submit.disabled).toBe(false);
      expect(root.querySelector("p.error")?.textContent).toBe("");
    });

    it("error: a rejected sign-in shows the could-not-sign-in text", async () => {
      const h = handlers({ onSignIn: vi.fn(async () => Promise.reject(new Error("bad code"))) });
      renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, h);
      root.querySelector<HTMLInputElement>('input[name="baseUrl"]')!.value = "https://kata.example.org";
      root.querySelector<HTMLInputElement>('input[name="code"]')!.value = "1234";
      root.querySelector<HTMLInputElement>('input[name="deviceLabel"]')!.value = "laptop";
      root.querySelector("form")!.dispatchEvent(new Event("submit", { cancelable: true }));
      await vi.waitFor(() => expect(root.querySelector("p.error")?.textContent).toBe(TEXT_SIGNIN[7]));
    });

    it("offline: a core that does not answer shows Server not reachable.", async () => {
      const h = handlers({ onSignIn: vi.fn(async () => Promise.reject(new CoreOfflineError())) });
      renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, h);
      root.querySelector<HTMLInputElement>('input[name="baseUrl"]')!.value = "https://kata.example.org";
      root.querySelector<HTMLInputElement>('input[name="code"]')!.value = "1234";
      root.querySelector<HTMLInputElement>('input[name="deviceLabel"]')!.value = "laptop";
      root.querySelector("form")!.dispatchEvent(new Event("submit", { cancelable: true }));
      await vi.waitFor(() => expect(root.querySelector("p.error")?.textContent).toBe(TEXT_SIGNIN[8]));
    });

    it("shows the heading and the field labels of the inventory", () => {
      renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, handlers());
      expect(root.querySelector("form.signin h2")?.textContent).toBe(TEXT_SIGNIN[0]);
      expect(textsOf(root, "form.signin label")).toEqual([TEXT_SIGNIN[1], TEXT_SIGNIN[2], TEXT_SIGNIN[3]]);
    });
  });

  describe("signed-out (error)", () => {
    it("shows the notice, the status line and a Sign in button that opens the form", () => {
      const state: PanelState = { session: null, rows: [], status: { kind: "error", reason: "auth" } };
      renderPanel(root, state, handlers());
      expect(root.querySelector("div.signed-out p")?.textContent).toBe(TEXT_SIGNED_OUT[0]);
      expect(root.querySelector("p.status")?.textContent).toBe("Sign-in failed or expired");
      expect(root.querySelector("form.signin")).toBeNull();
      buttonNamed(root, TEXT_SIGNED_OUT[1]).click();
      expect(root.querySelector("form.signin")).not.toBeNull();
      expect(root.querySelector("div.signed-out")).toBeNull();
    });
  });

  describe("connection detail (connected, offline, error)", () => {
    const connected = (link: { serverUp: boolean; unsynced: number }): PanelState => ({
      session,
      rows: [],
      status: { kind: "idle" },
      link,
    });

    it("connected: shows Connected with no retry button", () => {
      renderPanel(root, connected({ serverUp: true, unsynced: 0 }), handlers());
      expect(root.querySelector("div.conn-detail p.conn-state")?.textContent).toBe(TEXT_CONN_DETAIL[0]);
      expect(root.querySelector("button.retry-now")).toBeNull();
    });

    it("offline: shows Server down with the unsynced count, the scan note, Retry now and Show unsynced marks", () => {
      const h = handlers();
      renderPanel(root, connected({ serverUp: false, unsynced: 3 }), h);
      expect(root.querySelector("div.conn-detail p.conn-state")?.textContent).toBe(TEXT_CONN_DETAIL[1]);
      expect(root.querySelector("div.conn-detail p.conn-note")?.textContent).toBe(TEXT_CONN_DETAIL[6]);
      buttonNamed(root, TEXT_CONN_DETAIL[3]).click();
      expect(h.onRetry).toHaveBeenCalledTimes(1);
      buttonNamed(root, TEXT_CONN_DETAIL[4]).click();
      expect(h.onShowQueue).toHaveBeenCalledTimes(1);
    });

    it("error: shows plain Server down when no marks wait", () => {
      renderPanel(root, connected({ serverUp: false, unsynced: 0 }), handlers());
      expect(root.querySelector("div.conn-detail p.conn-state")?.textContent).toBe(TEXT_CONN_DETAIL[2]);
      expect(root.querySelector("button.show-queue")).toBeNull();
    });
  });

  describe("offline queue (empty, offline)", () => {
    it("empty: shows the title, Nothing waiting to sync. and Back, which calls onCloseQueue", () => {
      const h = handlers();
      renderPanel(root, { session, rows: [], status: { kind: "idle" }, queue: [] }, h);
      expect(root.querySelector("section.offline-queue h2")?.textContent).toBe(TEXT_OFFLINE_QUEUE[0]);
      expect(root.querySelector("p.empty")?.textContent).toBe(TEXT_OFFLINE_QUEUE[1]);
      expect(root.querySelector("ul")).toBeNull();
      buttonNamed(root, TEXT_OFFLINE_QUEUE[7]).click();
      expect(h.onCloseQueue).toHaveBeenCalledTimes(1);
    });

    it("offline: lists each mark with its Not synced or Synced badge in send order", () => {
      const queue = [
        { label: "pan", state: "known" as const, time: "09:00", synced: false },
        { label: "queso", state: "learning" as const, time: "09:01", synced: true },
      ];
      const h = handlers();
      renderPanel(root, { session, rows: [], status: { kind: "idle" }, queue }, h);
      expect(textsOf(root, "li.queued-mark span.label")).toEqual(["pan", "queso"]);
      expect(textsOf(root, "li.queued-mark span.badge")).toEqual([TEXT_OFFLINE_QUEUE[2], TEXT_OFFLINE_QUEUE[3]]);
      expect(textsOf(root, "section.offline-queue p.note")).toEqual([TEXT_OFFLINE_QUEUE[4], TEXT_OFFLINE_QUEUE[5]]);
      buttonNamed(root, TEXT_OFFLINE_QUEUE[6]).click();
      expect(h.onRetry).toHaveBeenCalledTimes(1);
    });
  });

  it("routeScreen draws the screen named by its id", () => {
    const screen = routeScreen("conn-detail", { serverUp: true, unsynced: 0 }, handlers());
    expect(screen.className).toBe("conn-detail");
  });
});
